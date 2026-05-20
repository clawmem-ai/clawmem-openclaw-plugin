#!/usr/bin/env python3
"""Judge benchmark answers in resilient batches using the local Codex CLI."""

from __future__ import annotations

import argparse
import json
import math
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
    parser.add_argument("--answers", required=True, help="Generated answers JSONL.")
    parser.add_argument("--output", required=True, help="Judged answers JSONL.")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--retry-batch-size", type=int, default=1)
    parser.add_argument("--max-retry-rounds", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--timeout-sec", type=float, default=float(os.environ.get("CODEX_EVAL_JUDGE_TIMEOUT_SEC", "600")))
    parser.add_argument("--model", default=os.environ.get("CODEX_EVAL_JUDGE_MODEL", os.environ.get("CODEX_EVAL_MODEL", "gpt-5.4-mini")))
    parser.add_argument("--reasoning-effort", default=os.environ.get("CODEX_EVAL_JUDGE_REASONING_EFFORT", os.environ.get("CODEX_EVAL_REASONING_EFFORT", "low")))
    args = parser.parse_args()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    if args.retry_batch_size <= 0:
        raise ValueError("--retry-batch-size must be positive")
    if args.max_retry_rounds < 0:
        raise ValueError("--max-retry-rounds must be non-negative")

    cases = {str(case["case_id"]): case for case in read_jsonl(Path(args.cases))}
    answers = read_jsonl(Path(args.answers))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = read_completed_ids(output) if args.resume else set()
    mode = "a" if args.resume and output.exists() else "w"

    pending = []
    for answer in answers:
        case_id = str(answer.get("case_id") or "")
        if not case_id or case_id in completed:
            continue
        case = cases.get(case_id)
        if not case:
            if not args.keep_going:
                raise ValueError(f"unknown case_id {case_id!r}")
            pending.append(error_item(answer, f"unknown case_id {case_id!r}"))
            continue
        pending.append(build_item(case, answer))
        if args.limit and len(pending) >= args.limit:
            break

    written = 0
    with output.open(mode, encoding="utf-8") as sink:
        for batch_index, batch in enumerate(chunks(pending, args.batch_size), 1):
            rows = judge_batch_with_retries(batch, batch_index, args)
            for row in rows:
                sink.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                written += 1
            sink.flush()
            invalid = sum(1 for row in rows if row_is_invalid_judgment(row))
            suffix = f", invalid={invalid}" if invalid else ""
            print(f"wrote judge batch {batch_index} ({len(rows)} answers{suffix}), total={written}", flush=True)
    print(f"wrote {written} Codex batch judged answer(s) to {output}")


def build_item(case: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    return {
        "case": case,
        "answer": answer,
        "request": {
            "case_id": case["case_id"],
            "question": case.get("question") or "",
            "references": unique_strings(case.get("answers")),
            "answer": str(answer.get("answer") or answer.get("predicted_answer") or answer.get("model_answer") or "").strip(),
        },
    }


def error_item(answer: dict[str, Any], error: str) -> dict[str, Any]:
    return {
        "case": {"case_id": answer.get("case_id")},
        "answer": answer,
        "request": {"case_id": answer.get("case_id"), "question": "", "references": [], "answer": ""},
        "prebuilt_error": error,
    }


def judge_batch_with_retries(batch: list[dict[str, Any]], batch_index: int, args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = judge_batch(batch, batch_index, args, retry_round=0)
    rows_by_id = {str(row.get("case_id")): row for row in rows if row.get("case_id")}

    for retry_round in range(1, args.max_retry_rounds + 1):
        retry_items = [
            item for item in batch
            if row_is_invalid_judgment(rows_by_id.get(str(item["case"].get("case_id"))))
        ]
        if not retry_items:
            break
        for retry_batch in chunks(retry_items, args.retry_batch_size):
            retry_rows = judge_batch(retry_batch, batch_index, args, retry_round=retry_round)
            for row in retry_rows:
                rows_by_id[str(row.get("case_id"))] = row

    return [rows_by_id.get(str(item["case"].get("case_id"))) or final_error_row(item, batch_index, args, "missing judgment row after retries") for item in batch]


def judge_batch(batch: list[dict[str, Any]], batch_index: int, args: argparse.Namespace, retry_round: int) -> list[dict[str, Any]]:
    prebuilt = [item for item in batch if item.get("prebuilt_error")]
    active = [item for item in batch if not item.get("prebuilt_error")]
    rows = [final_error_row(item, batch_index, args, str(item["prebuilt_error"]), retry_round=retry_round) for item in prebuilt]
    if not active:
        return rows

    started = time.perf_counter()
    try:
        judgments, tokens = call_codex([item["request"] for item in active], args)
        by_id = {
            str(item.get("case_id")): item
            for item in judgments
            if isinstance(item, dict) and item.get("case_id")
        }
        latency_ms = int((time.perf_counter() - started) * 1000)
        for item in active:
            prediction = item["answer"]
            raw = by_id.get(str(prediction.get("case_id")))
            error = ""
            if raw is None:
                error = "codex judge output omitted case_id"
                judge = {"correct": None, "score": None, "rationale": "", "model": args.model}
            else:
                judge = normalize_judge(raw, args.model)
                if judge.get("correct") is None and judge.get("score") is None:
                    error = "codex judge output omitted correctness and score"
            usage = {"total_tokens": tokens / len(active)} if tokens is not None and active else {}
            judged = attach_judge(prediction, judge, usage, latency_ms)
            metadata = judged.get("metadata") if isinstance(judged.get("metadata"), dict) else {}
            judged["metadata"] = {
                **metadata,
                "judge": "codex_exec_batch",
                "judge_batch_index": batch_index,
                "judge_batch_size": len(active),
                "judge_batch_total_tokens": tokens,
                "judge_retry_round": retry_round,
                **({"judge_error": error} if error else {}),
            }
            rows.append(judged)
        return rows
    except Exception as error:
        if not args.keep_going:
            raise
        return [final_error_row(item, batch_index, args, str(error), retry_round=retry_round) for item in active] + rows


def call_codex(requests: list[dict[str, Any]], args: argparse.Namespace) -> tuple[list[dict[str, Any]], int | None]:
    prompt = (
        "You are a strict but fair benchmark answer judge.\n"
        "For each item, grade whether answer correctly answers question compared with references.\n"
        "Allow paraphrases, equivalent dates, aliases, and concise partial phrasing when the meaning is the same.\n"
        "Do not penalize extra text unless it contradicts the reference.\n"
        "Return exactly one JSON object for every input item. Preserve each case_id exactly. Never omit an item.\n"
        "Return JSON only: an array of objects with exactly keys case_id, correct, score, rationale.\n\n"
        f"Items:\n{json.dumps(requests, ensure_ascii=False)}"
    )
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
        if isinstance(value, dict) and isinstance(value.get("judgments"), list):
            value = value["judgments"]
        if not isinstance(value, list):
            raise RuntimeError("Codex judge output must be a JSON array")
        log = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        return value, parse_tokens_used(log)
    finally:
        try:
            Path(output_path).unlink()
        except FileNotFoundError:
            pass


def normalize_judge(raw: dict[str, Any], model: str) -> dict[str, Any]:
    correct = raw.get("correct") if isinstance(raw.get("correct"), bool) else None
    score = number(raw.get("score"))
    if correct is None and score is not None:
        correct = score >= 0.5
    return {
        "correct": correct,
        "score": score,
        "rationale": str(raw.get("rationale") or "").strip(),
        "model": model,
    }


def attach_judge(prediction: dict[str, Any], judge: dict[str, Any], usage: dict[str, Any], latency_ms: int) -> dict[str, Any]:
    metadata = prediction.get("metadata") if isinstance(prediction.get("metadata"), dict) else {}
    return {
        **prediction,
        "judge": judge,
        "metadata": {
            **metadata,
            "judge_latency_ms": latency_ms,
            "judge_usage": usage,
        },
    }


def final_error_row(item: dict[str, Any], batch_index: int, args: argparse.Namespace, error: str, retry_round: int = 0) -> dict[str, Any]:
    answer = item.get("answer") if isinstance(item.get("answer"), dict) else {}
    judged = attach_judge(
        answer,
        {"score": 0.0, "correct": False, "rationale": error, "error": error, "model": args.model},
        {},
        0,
    )
    metadata = judged.get("metadata") if isinstance(judged.get("metadata"), dict) else {}
    judged["metadata"] = {
        **metadata,
        "judge": "codex_exec_batch",
        "judge_batch_index": batch_index,
        "judge_batch_size": 0,
        "judge_retry_round": retry_round,
        "judge_error": error,
    }
    judged["error"] = error
    return judged


def row_is_invalid_judgment(row: dict[str, Any] | None) -> bool:
    if not row:
        return True
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if row.get("error") or metadata.get("judge_error"):
        return True
    judge = row.get("judge") if isinstance(row.get("judge"), dict) else {}
    return judge.get("correct") is None and judge.get("score") is None


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


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def chunks(values: list[Any], size: int):
    for index in range(0, len(values), size):
        yield values[index:index + size]


if __name__ == "__main__":
    main()
