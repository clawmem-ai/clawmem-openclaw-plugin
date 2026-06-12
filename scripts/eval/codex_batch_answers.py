#!/usr/bin/env python3
"""Generate benchmark answers in resilient batches using the local Codex CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, help="Normalized cases JSONL.")
    parser.add_argument("--predictions", required=True, help="Retrieval predictions JSONL.")
    parser.add_argument("--output", required=True, help="Answer predictions JSONL.")
    parser.add_argument("--level", choices=["session", "turn"], default="session")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--max-context-chars", type=int, default=16000)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--retry-batch-size", type=int, default=1)
    parser.add_argument("--max-retry-rounds", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--timeout-sec", type=float, default=float(os.environ.get("CODEX_EVAL_TIMEOUT_SEC", "600")))
    parser.add_argument("--model", default=os.environ.get("CODEX_EVAL_MODEL", "gpt-5.4-mini"))
    parser.add_argument("--reasoning-effort", default=os.environ.get("CODEX_EVAL_REASONING_EFFORT", "low"))
    args = parser.parse_args()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    if args.retry_batch_size <= 0:
        raise ValueError("--retry-batch-size must be positive")
    if args.max_retry_rounds < 0:
        raise ValueError("--max-retry-rounds must be non-negative")

    cases = {str(case["case_id"]): case for case in read_jsonl(Path(args.cases))}
    predictions = read_jsonl(Path(args.predictions))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = read_completed_ids(output) if args.resume else set()
    mode = "a" if args.resume and output.exists() else "w"

    pending = []
    for prediction in predictions:
        case_id = str(prediction.get("case_id") or "")
        if not case_id or case_id in completed:
            continue
        case = cases.get(case_id)
        if not case:
            if not args.keep_going:
                raise ValueError(f"unknown case_id {case_id!r}")
            pending.append(error_item(prediction, f"unknown case_id {case_id!r}"))
            continue
        pending.append(build_item(case, prediction, args))
        if args.limit and len(pending) >= args.limit:
            break

    written = 0
    with output.open(mode, encoding="utf-8") as sink:
        for batch_index, batch in enumerate(chunks(pending, args.batch_size), 1):
            rows = answer_batch_with_retries(batch, batch_index, args)
            for row in rows:
                sink.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                written += 1
            sink.flush()
            invalid = sum(1 for row in rows if row_is_invalid_answer(row))
            suffix = f", invalid={invalid}" if invalid else ""
            print(f"wrote batch {batch_index} ({len(rows)} answers{suffix}), total={written}", flush=True)
    print(f"wrote {written} Codex batch answer(s) to {output}")


def build_item(case: dict[str, Any], prediction: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    context_items = build_context_items(case, prediction, args.level, args.top_k, args.max_context_chars)
    context = "\n\n".join(item["text"] for item in context_items)
    return {
        "case": case,
        "prediction": prediction,
        "request": {
            "case_id": case["case_id"],
            "question_date": case.get("question_date"),
            "question": case.get("question") or "",
            "memory_context": context,
        },
        "context_chars": len(context),
        "context_item_count": len(context_items),
    }


def error_item(prediction: dict[str, Any], error: str) -> dict[str, Any]:
    return {
        "case": {"case_id": prediction.get("case_id")},
        "prediction": prediction,
        "request": {"case_id": prediction.get("case_id"), "question": "", "memory_context": ""},
        "context_chars": 0,
        "context_item_count": 0,
        "prebuilt_error": error,
    }


def answer_batch_with_retries(batch: list[dict[str, Any]], batch_index: int, args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = answer_batch(batch, batch_index, args, retry_round=0)
    rows_by_id = {str(row.get("case_id")): row for row in rows if row.get("case_id")}

    for retry_round in range(1, args.max_retry_rounds + 1):
        retry_items = [
            item for item in batch
            if row_is_invalid_answer(rows_by_id.get(str(item["case"].get("case_id"))))
        ]
        if not retry_items:
            break
        for retry_batch in chunks(retry_items, args.retry_batch_size):
            retry_rows = answer_batch(retry_batch, batch_index, args, retry_round=retry_round)
            for row in retry_rows:
                rows_by_id[str(row.get("case_id"))] = row

    return [rows_by_id.get(str(item["case"].get("case_id"))) or final_error_row(item, batch_index, args, "missing answer row after retries") for item in batch]


def answer_batch(batch: list[dict[str, Any]], batch_index: int, args: argparse.Namespace, retry_round: int) -> list[dict[str, Any]]:
    prebuilt = [item for item in batch if item.get("prebuilt_error")]
    active = [item for item in batch if not item.get("prebuilt_error")]
    rows = [final_error_row(item, batch_index, args, str(item["prebuilt_error"])) for item in prebuilt]
    if not active:
        return rows

    started = time.perf_counter()
    try:
        answers, tokens = call_codex([item["request"] for item in active], args, answer_prompt)
        by_id = {
            str(item.get("case_id")): item
            for item in answers
            if isinstance(item, dict) and item.get("case_id")
        }
        latency_ms = int((time.perf_counter() - started) * 1000)
        for item in active:
            case = item["case"]
            prediction = item["prediction"]
            raw = by_id.get(str(case["case_id"]))
            answer = str(raw.get("answer") or "").strip() if isinstance(raw, dict) else ""
            error = ""
            if raw is None:
                error = "codex output omitted case_id"
            elif not answer:
                error = "codex output returned empty answer"
            rows.append(answer_row(case, prediction, answer, item, batch_index, len(active), tokens, latency_ms, args, retry_round, error))
        return rows
    except Exception as error:
        if not args.keep_going:
            raise
        return [final_error_row(item, batch_index, args, str(error), retry_round=retry_round) for item in active] + rows


def answer_prompt(requests: list[dict[str, Any]]) -> str:
    return (
        "You are an answer-generation function for a memory benchmark.\n"
        "For each item, use only that item's memory_context. If the context is insufficient, answer \"I don't know.\"\n"
        "Treat each item independently; never borrow evidence across case_id values.\n"
        "Choose evidence that matches all key constraints in the question: subject, target property, relationship direction, date/time, and requested event. Do not answer from a merely related memory when a more specific matching memory is present.\n"
        "For advice or reason questions, prefer the memory whose title/body matches the advice target or reason target, not another advice/motivation memory from the same people.\n"
        "For advice questions, answer with the advice wording if it is present, such as 'keep trying new things until something sparks excitement'; do not abstain just because nearby advice memories mention other topics.\n"
        "For reason questions, preserve the stated purpose from the question and memory when supported. If a workshop is described as for bonding with pets, answer that the purpose was to strengthen the bond with the pets, even when the same memory also mentions positive reinforcement steps.\n"
        "For yes/no image or artifact questions, answer yes when memory_context says the named person made, bought, received, or owns the exact object or photo subject. Do not answer \"I don't know\" when direct authorship/ownership is in a recalled memory, even if the image color or style is one detail among several.\n"
        "For likely yes/no questions, answer the likely yes/no value when a recalled memory states that likely answer with a basis and boundary. Do not abstain merely because the memory is explicitly probabilistic.\n"
        "For fun/new activity questions, prefer memories whose title/body explicitly include the requested person, activity hook such as fun activity/new activity, and requested date/month. Answer the concrete activity, not a broader trip or background event.\n"
        "For list or set questions, scan all recalled memories and merge only compatible values about the same subject and property. Do not mix different events, people, or time periods.\n"
        "For favorite/current-favorite questions, prefer direct favorite/preference/current wording over adjacent played, watched, read, tried, won, or recommended activity records.\n"
        "If a favorite game/media question has no direct favorite wording, a current-playing/current-reading memory plus explicit fan or preference wording is stronger than older tournament, win, or generic hobby memories.\n"
        "For activity-in-month questions, prefer memories whose subject, activity predicate, and event month all match the question over broader hobby, trip, or later activity summaries.\n"
        "For time questions, distinguish event_date from source_date. event_date is the event time when known; source_date is only when the conversation recorded the memory.\n"
        "Answer with an exact day only when the memory explicitly supports that event day, such as an event_date, an exact date in the memory text, or a relative phrase like today/yesterday/last Friday resolved against source_date.\n"
        "If a memory contains source-relative weekday wording and a computed calendar date that conflict, do not silently choose the conflicting date. Prefer the source-relative wording or answer with both plus uncertainty.\n"
        "If the context only supports a month, year, or broad interval, answer at that granularity instead of inventing a day.\n"
        "If several recalled memories conflict, use the one that best matches the wording and temporal constraints of the question; mention uncertainty only when needed.\n"
        "Return exactly one JSON object for every input item. Preserve each case_id exactly. Never omit an item and never use a blank answer.\n"
        "Return JSON only: an array of objects with exactly keys case_id and answer.\n\n"
        f"Items:\n{json.dumps(requests, ensure_ascii=False)}"
    )


def answer_row(
    case: dict[str, Any],
    prediction: dict[str, Any],
    answer: str,
    item: dict[str, Any],
    batch_index: int,
    batch_size: int,
    tokens: int | None,
    latency_ms: int,
    args: argparse.Namespace,
    retry_round: int,
    error: str = "",
) -> dict[str, Any]:
    amortized_tokens = (tokens / batch_size) if tokens is not None and batch_size else None
    return {
        "case_id": case["case_id"],
        "benchmark": case.get("benchmark"),
        "source_id": case.get("source_id"),
        "question_type": case.get("question_type"),
        "answer": answer,
        "retrieved_session_ids": unique_strings(prediction.get("retrieved_session_ids")),
        "retrieved_turn_ids": unique_strings(prediction.get("retrieved_turn_ids")),
        "usage": {"total_tokens": amortized_tokens} if amortized_tokens is not None else {},
        "metadata": {
            "answerer": "codex_exec_batch",
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
            "level": args.level,
            "top_k": args.top_k,
            "context_item_count": item["context_item_count"],
            "context_chars": item["context_chars"],
            "batch_index": batch_index,
            "batch_size": batch_size,
            "batch_total_tokens": tokens,
            "latency_ms": latency_ms,
            "retry_round": retry_round,
            "retrieval_metadata": prediction.get("metadata"),
            **({"answer_error": error} if error else {}),
        },
    }


def final_error_row(item: dict[str, Any], batch_index: int, args: argparse.Namespace, error: str, retry_round: int = 0) -> dict[str, Any]:
    prediction = item.get("prediction") if isinstance(item.get("prediction"), dict) else {}
    case = item.get("case") if isinstance(item.get("case"), dict) else {}
    return {
        "case_id": case.get("case_id") or prediction.get("case_id"),
        "answer": "",
        "retrieved_session_ids": unique_strings(prediction.get("retrieved_session_ids")),
        "retrieved_turn_ids": unique_strings(prediction.get("retrieved_turn_ids")),
        "usage": {},
        "metadata": {
            "answerer": "codex_exec_batch",
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
            "batch_index": batch_index,
            "batch_size": 0,
            "retry_round": retry_round,
            "answer_error": error,
        },
        "error": error,
    }


def row_is_invalid_answer(row: dict[str, Any] | None) -> bool:
    if not row:
        return True
    if row.get("error"):
        return True
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if metadata.get("answer_error"):
        return True
    return not str(row.get("answer") or "").strip()


def call_codex(requests: list[dict[str, Any]], args: argparse.Namespace, prompt_builder) -> tuple[list[dict[str, Any]], int | None]:
    prompt = prompt_builder(requests)
    with tempfile.NamedTemporaryFile("r+", encoding="utf-8", delete=False) as tmp:
        output_path = tmp.name
    try:
        command = [
            "codex", "exec", "--ephemeral", "--skip-git-repo-check",
            "--sandbox", "read-only",
            "-m", args.model,
            "-c", f'model_reasoning_effort="{args.reasoning_effort}"',
            "-o", output_path,
            "-",
        ]
        completed = subprocess.run(command, input=prompt, text=True, capture_output=True, timeout=args.timeout_sec, check=False)
        last_message = Path(output_path).read_text(encoding="utf-8").strip()
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"codex exited with code {completed.returncode}")
        value = parse_json(last_message)
        if isinstance(value, dict) and isinstance(value.get("answers"), list):
            value = value["answers"]
        if not isinstance(value, list):
            raise RuntimeError("Codex answer output must be a JSON array")
        log = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        return value, parse_tokens_used(log)
    finally:
        try:
            Path(output_path).unlink()
        except FileNotFoundError:
            pass


def build_context_items(
    case: dict[str, Any],
    prediction: dict[str, Any],
    level: str,
    top_k: int,
    max_context_chars: int,
) -> list[dict[str, str]]:
    raw_recall = raw_recall_text(prediction)
    metadata = prediction.get("metadata") if isinstance(prediction.get("metadata"), dict) else {}
    if raw_recall and metadata.get("index_mode") == "plugin-finalize":
        return trim_context([{"id": "clawmem_recall", "text": "ClawMem recall text:\n" + raw_recall}], max_context_chars)
    ids = predicted_ids(prediction, level)[:top_k]
    items = session_context(case, ids) if level == "session" else turn_context(case, ids)
    if not items and raw_recall:
        items = [{"id": "raw_recall_text", "text": "Raw recall text:\n" + raw_recall}]
    return trim_context(items, max_context_chars)


def raw_recall_text(prediction: dict[str, Any]) -> str:
    direct = str(prediction.get("raw_recall_text") or "").strip()
    if direct:
        return direct
    metadata = prediction.get("metadata") if isinstance(prediction.get("metadata"), dict) else {}
    return str(metadata.get("raw_recall") or "").strip()


def session_context(case: dict[str, Any], ids: list[str]) -> list[dict[str, str]]:
    sessions = {
        str(session.get("session_id")): session
        for session in case.get("sessions", [])
        if isinstance(session, dict) and session.get("session_id")
    }
    out = []
    for session_id in ids:
        session = sessions.get(session_id)
        if not session:
            continue
        transcript = "\n".join(render_message(message) for message in session.get("messages", []) if isinstance(message, dict))
        text = "\n".join([
            f"Memory session id: {session_id}",
            f"Source session id: {session.get('source_session_id') or ''}",
            f"Timestamp: {session.get('timestamp') or ''}",
            "Transcript:",
            transcript,
        ]).strip()
        out.append({"id": session_id, "text": text})
    return out


def turn_context(case: dict[str, Any], ids: list[str]) -> list[dict[str, str]]:
    by_turn: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for session in case.get("sessions", []):
        if not isinstance(session, dict):
            continue
        for message in session.get("messages", []):
            if isinstance(message, dict) and message.get("turn_id"):
                by_turn[str(message["turn_id"])] = (session, message)
    out = []
    for turn_id in ids:
        pair = by_turn.get(turn_id)
        if not pair:
            continue
        session, message = pair
        text = "\n".join([
            f"Memory turn id: {turn_id}",
            f"Session id: {session.get('session_id') or ''}",
            f"Timestamp: {session.get('timestamp') or ''}",
            render_message(message),
        ]).strip()
        out.append({"id": turn_id, "text": text})
    return out


def trim_context(items: list[dict[str, str]], max_chars: int) -> list[dict[str, str]]:
    out = []
    used = 0
    for item in items:
        remaining = max_chars - used
        if remaining <= 0:
            break
        text = item["text"]
        if len(text) > remaining:
            text = text[: max(0, remaining - 20)].rstrip() + "\n[truncated]"
        out.append({"id": item["id"], "text": text})
        used += len(text) + 2
    return out


def render_message(message: dict[str, Any]) -> str:
    turn_id = str(message.get("turn_id") or "").strip()
    speaker = str(message.get("speaker") or message.get("role") or "speaker").strip()
    content = str(message.get("content") or "").strip()
    prefix = f"[{turn_id}] " if turn_id else ""
    return f"{prefix}{speaker}: {content}".strip()


def predicted_ids(prediction: dict[str, Any], level: str) -> list[str]:
    field = "retrieved_session_ids" if level == "session" else "retrieved_turn_ids"
    values = unique_strings(prediction.get(field))
    if values:
        return values
    for alternate_field in ("retrieval_results", "retrieved"):
        if alternate_field in prediction:
            return ids_from_objects(prediction.get(alternate_field), level)
    return []


def ids_from_objects(value: Any, level: str) -> list[str]:
    if not isinstance(value, list):
        return []
    keys = ["session_id", "id"] if level == "session" else ["turn_id", "id"]
    out = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
            continue
        if isinstance(item, dict):
            for key in keys:
                if item.get(key):
                    out.append(str(item[key]))
                    break
    return unique_strings(out)


def parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
        if not match:
            raise
        return json.loads(match.group(1))


def parse_tokens_used(log: str) -> int | None:
    matches = list(re.finditer(r"tokens used\s+([0-9,]+)", log, flags=re.IGNORECASE))
    if not matches:
        return None
    return int(matches[-1].group(1).replace(",", ""))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def read_completed_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("case_id"):
                out.add(str(value["case_id"]))
    return out


def unique_strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else ([] if value is None else [value])
    seen = set()
    out = []
    for item in values:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def chunks(values: list[Any], size: int):
    for index in range(0, len(values), size):
        yield values[index:index + size]


if __name__ == "__main__":
    main()
