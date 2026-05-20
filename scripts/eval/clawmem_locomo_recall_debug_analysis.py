#!/usr/bin/env python3
"""Analyze ClawMem LoCoMo recall failures with backend search debug.

This script joins four things:

- benchmark cases and reference answers
- extracted memory JSONL
- memory issue map JSONL
- recall predictions with backend debug candidate payloads

It classifies recall failures by where the answer-bearing memory disappeared:
not retained, not returned by search, returned below top-k, or returned in
top-k but missing from the rendered recall context.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SKILL_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "skills" / "clawmem" / "scripts"
if str(SKILL_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPT_DIR))

from clawmem_locomo_gate import reference_values, source_id_for, value_is_covered  # noqa: E402


def main() -> int:
    args = build_arg_parser().parse_args()
    cases = {str(row.get("case_id")): row for row in read_jsonl(args.cases) if row.get("case_id")}
    predictions = {str(row.get("case_id")): row for row in read_jsonl(args.predictions) if row.get("case_id")}
    answers = {str(row.get("case_id")): row for row in read_jsonl(args.answer_metrics) if row.get("case_id")} if args.answer_metrics else {}
    memory_map = load_memory_map(args.memory_map_jsonl)
    memories = load_memories(args.memories_jsonl, memory_map)

    rows: list[dict[str, Any]] = []
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stage_counts: Counter[str] = Counter()
    by_question_type: dict[str, Counter[str]] = defaultdict(Counter)
    candidate_stage_paths: dict[str, Counter[str]] = defaultdict(Counter)
    candidate_stage_fields: dict[str, Counter[str]] = defaultdict(Counter)
    candidate_stage_ranks: dict[str, list[int]] = defaultdict(list)
    top_stage_paths: dict[str, Counter[str]] = defaultdict(Counter)

    for case_id, case in sorted(cases.items()):
        if args.only_predicted and case_id not in predictions:
            continue
        refs = reference_values(case)
        if not refs and not args.include_empty_gold:
            continue
        prediction = predictions.get(case_id, {})
        row = analyze_case(case, refs, prediction, answers.get(case_id, {}), memories)
        rows.append(row)

        stage = row["stage"]
        question_type = str(row.get("question_type") or "unknown")
        stage_counts[stage] += 1
        by_question_type[question_type][stage] += 1

        for item in row.get("matching_candidate_debug") or []:
            debug = item.get("debug") if isinstance(item.get("debug"), dict) else {}
            path = str(debug.get("search_path") or "")
            if path:
                candidate_stage_paths[stage][path] += 1
            for field in debug.get("matched_fields") if isinstance(debug.get("matched_fields"), list) else []:
                candidate_stage_fields[stage][str(field)] += 1
            if isinstance(item.get("rank"), int):
                candidate_stage_ranks[stage].append(item["rank"])

        for item in row.get("top_result_debug") or []:
            debug = item.get("debug") if isinstance(item.get("debug"), dict) else {}
            path = str(debug.get("search_path") or "")
            if path:
                top_stage_paths[stage][path] += 1

        if stage != "correct" and len(samples[stage]) < args.max_samples:
            samples[stage].append(sample_case(row))

    summary = {
        "case_count": len(rows),
        "stage_counts": dict(sorted(stage_counts.items())),
        "by_question_type": {key: dict(sorted(value.items())) for key, value in sorted(by_question_type.items())},
        "matching_candidate_debug": {
            stage: {
                "search_path_counts": dict(sorted(candidate_stage_paths[stage].items())),
                "matched_field_counts": dict(sorted(candidate_stage_fields[stage].items())),
                "min_rank": min(candidate_stage_ranks[stage]) if candidate_stage_ranks[stage] else None,
                "avg_rank": average(candidate_stage_ranks[stage]),
            }
            for stage in sorted(stage_counts)
        },
        "top_result_search_paths": {
            stage: dict(sorted(counter.items()))
            for stage, counter in sorted(top_stage_paths.items())
        },
        "samples": dict(samples),
    }
    payload = {"summary": summary, "cases": rows if args.include_cases else []}
    if args.output:
        write_json(Path(args.output), payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if args.per_case_output:
        write_jsonl(Path(args.per_case_output), rows)
    return 0


def analyze_case(
    case: dict[str, Any],
    refs: list[str],
    prediction: dict[str, Any],
    answer: dict[str, Any],
    memories: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    source_id = source_id_for(case)
    source_memories = memories.get(source_id, [])
    matching_memories = [
        memory
        for memory in source_memories
        if any(value_is_covered(memory["text"], ref) for ref in refs)
    ]
    matching_issue_ids = unique_strings(memory.get("issue_number") for memory in matching_memories)
    top_ids = unique_strings(prediction.get("retrieved_memory_ids"))
    candidate_debug = prediction.get("recall_candidate_debug") if isinstance(prediction.get("recall_candidate_debug"), list) else []
    candidate_by_issue = {str(item.get("issue_number")): item for item in candidate_debug if str(item.get("issue_number") or "").strip()}
    matching_top_ids = [issue for issue in matching_issue_ids if issue in set(top_ids)]
    matching_candidate_debug = [candidate_by_issue[issue] for issue in matching_issue_ids if issue in candidate_by_issue]
    recall_text = str(prediction.get("raw_recall_text") or "")
    recall_covers_all = all(value_is_covered(recall_text, ref) for ref in refs) if refs else True
    answer_correct = judge_correct(answer)

    if not prediction:
        stage = "missing_prediction"
    elif not matching_memories:
        stage = "retention_miss"
    elif not matching_candidate_debug:
        stage = "candidate_not_returned"
    elif not matching_top_ids:
        stage = "ranked_below_top_k"
    elif not recall_covers_all:
        stage = "context_missing_value"
    elif answer_correct:
        stage = "correct"
    else:
        stage = "answer_miss"

    return {
        "case_id": case.get("case_id"),
        "source_id": source_id,
        "question_type": case.get("question_type") or "",
        "question": case.get("question") or "",
        "references": refs,
        "stage": stage,
        "answer_correct": answer_correct,
        "answer": answer.get("answer") or "",
        "recall_query": nested(prediction, "metadata", "recall_query") or "",
        "recall_query_text": nested(prediction, "metadata", "recall_query_text") or "",
        "recall_query_mode": nested(prediction, "metadata", "recall_query_mode") or "",
        "matching_issue_ids": matching_issue_ids,
        "matching_titles": [str(memory.get("title") or "") for memory in matching_memories[:8]],
        "retrieved_memory_ids": top_ids,
        "matching_top_ids": matching_top_ids,
        "matching_candidate_ranks": [item.get("rank") for item in matching_candidate_debug if item.get("rank")],
        "matching_candidate_debug": matching_candidate_debug,
        "top_result_debug": candidate_debug[:10],
        "recall_covers_all_values": recall_covers_all,
    }


def load_memory_map(paths: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in paths:
        for row in read_jsonl(path):
            key = str(row.get("memory_key") or "").strip()
            if key:
                out[key] = row
    return out


def load_memories(paths: list[str], memory_map: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        for row in read_jsonl(path):
            if isinstance(row.get("memories"), list):
                parent_source = source_id_for(row)
                for item in row["memories"]:
                    if isinstance(item, dict):
                        append_memory(out, item, parent_source, memory_map)
                continue
            append_memory(out, row, source_id_for(row), memory_map)
    return out


def append_memory(
    out: dict[str, list[dict[str, Any]]],
    memory: dict[str, Any],
    fallback_source_id: str,
    memory_map: dict[str, dict[str, Any]],
) -> None:
    source_id = source_id_for(memory, fallback_source_id)
    key = str(memory.get("memory_key") or "").strip()
    mapped = memory_map.get(key, {})
    issue_number = str(memory.get("issue_number") or mapped.get("issue_number") or "").strip()
    title = str(memory.get("title") or mapped.get("title") or "")
    detail = str(memory.get("memory") or mapped.get("memory") or memory.get("body") or "")
    text = "\n".join(part for part in (title, detail) if part)
    if not source_id or not text:
        return
    out[source_id].append({
        "memory_key": key,
        "issue_number": issue_number,
        "title": title,
        "text": text,
    })


def judge_correct(answer: dict[str, Any]) -> bool:
    judge = answer.get("judge") if isinstance(answer.get("judge"), dict) else {}
    correct = judge.get("correct")
    if isinstance(correct, bool):
        return correct
    score = judge.get("score")
    return isinstance(score, (int, float)) and score >= 0.5


def sample_case(row: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "case_id",
        "source_id",
        "question_type",
        "stage",
        "question",
        "references",
        "answer",
        "recall_query_text",
        "matching_issue_ids",
        "matching_titles",
        "retrieved_memory_ids",
        "matching_candidate_ranks",
        "matching_candidate_debug",
    )
    return {key: row.get(key) for key in keep}


def nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def unique_strings(values: Any) -> list[str]:
    iterable = values if isinstance(values, list) else list(values or [])
    out: list[str] = []
    seen = set()
    for value in iterable:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def read_jsonl(path: str) -> list[dict[str, Any]]:
    rows = []
    with open(os.path.expanduser(path), "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected object")
            rows.append(value)
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def average(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze LoCoMo recall misses using backend search debug payloads.")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--memories-jsonl", action="append", required=True)
    parser.add_argument("--memory-map-jsonl", action="append", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--answer-metrics", help="Optional per-case judged answer metrics JSONL.")
    parser.add_argument("--output", help="Summary JSON output path.")
    parser.add_argument("--per-case-output", help="Per-case JSONL output path.")
    parser.add_argument("--only-predicted", action="store_true")
    parser.add_argument("--include-empty-gold", action="store_true")
    parser.add_argument("--include-cases", action="store_true")
    parser.add_argument("--max-samples", type=int, default=8)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
