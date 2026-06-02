#!/usr/bin/env python3
"""Classify LoCoMo memory-only failures by pipeline stage.

The audit is intentionally approximate and deterministic. It asks:

- did retention put the reference values anywhere in source memories?
- did recall put those values in the answer context?
- did the answerer still fail despite having those values?

This keeps ClawMem optimization pointed at the failing stage instead of tuning
the whole pipeline by feel.
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

from clawmem_locomo_gate import (  # noqa: E402
    load_memory_groups,
    reference_values,
    source_id_for,
    value_is_covered,
)


def main() -> int:
    args = build_arg_parser().parse_args()
    cases = {str(row.get("case_id")): row for row in read_jsonl(args.cases) if row.get("case_id")}
    predictions = {str(row.get("case_id")): row for row in read_jsonl(args.predictions) if row.get("case_id")}
    answers = {str(row.get("case_id")): row for row in read_jsonl(args.answer_metrics) if row.get("case_id")}
    source_filter = {str(row.get("source_id") or "").strip() for row in cases.values() if row.get("source_id")}
    memories = load_memory_groups(args.memories_jsonl, source_filter)
    corpora = {source_id: "\n\n".join(items) for source_id, items in memories.items()}

    rows = []
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    bucket_counts: Counter[str] = Counter()
    question_type_counts: dict[str, Counter[str]] = defaultdict(Counter)
    bucket_search_paths: dict[str, Counter[str]] = defaultdict(Counter)
    bucket_matched_fields: dict[str, Counter[str]] = defaultdict(Counter)
    bucket_top_scores: dict[str, list[float]] = defaultdict(list)
    totals = Counter()

    for case_id, case in sorted(cases.items()):
        if args.only_predicted and case_id not in predictions:
            continue
        values = reference_values(case)
        if not values and not args.include_empty_gold:
            continue
        prediction = predictions.get(case_id, {})
        answer = answers.get(case_id, {})
        row = audit_case(case, prediction, answer, corpora, values)
        rows.append(row)

        bucket = row["bucket"]
        question_type = str(row.get("question_type") or "unknown")
        bucket_counts[bucket] += 1
        question_type_counts[question_type][bucket] += 1
        for path, count in dict(row.get("recall_search_path_counts") or {}).items():
            bucket_search_paths[bucket][str(path)] += int(count)
        for field, count in dict(row.get("recall_matched_field_counts") or {}).items():
            bucket_matched_fields[bucket][str(field)] += int(count)
        if isinstance(row.get("recall_top_score"), (int, float)):
            bucket_top_scores[bucket].append(float(row["recall_top_score"]))
        totals["reference_values"] += len(values)
        totals["corpus_covered_values"] += row["corpus_covered_value_count"]
        totals["recall_covered_values"] += row["recall_covered_value_count"]
        totals["retrieval_hit"] += 1 if row["retrieval_hit"] else 0
        totals["answer_correct"] += 1 if row["answer_correct"] else 0

        if bucket != "correct" and len(samples[bucket]) < args.max_samples:
            samples[bucket].append(sample_row(row))

    summary = {
        "case_count": len(rows),
        "memory_source_count": len(memories),
        "memory_count": sum(len(items) for items in memories.values()),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "by_question_type": {
            question_type: dict(sorted(counter.items()))
            for question_type, counter in sorted(question_type_counts.items())
        },
        "by_bucket_search_debug": {
            bucket: {
                "search_path_counts": dict(sorted(bucket_search_paths[bucket].items())),
                "matched_field_counts": dict(sorted(bucket_matched_fields[bucket].items())),
                "avg_top_score": average(bucket_top_scores[bucket]),
            }
            for bucket in sorted(bucket_counts)
        },
        "rates": {
            "answer_accuracy": ratio(totals["answer_correct"], len(rows)),
            "retrieval_hit": ratio(totals["retrieval_hit"], len(rows)),
            "corpus_value_coverage": ratio(totals["corpus_covered_values"], totals["reference_values"]),
            "recall_value_coverage": ratio(totals["recall_covered_values"], totals["reference_values"]),
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


def audit_case(
    case: dict[str, Any],
    prediction: dict[str, Any],
    answer: dict[str, Any],
    corpora: dict[str, str],
    values: list[str],
) -> dict[str, Any]:
    source_id = source_id_for(case)
    corpus = corpora.get(source_id, "")
    recall_text = str(prediction.get("raw_recall_text") or "")
    corpus_missing = missing_values(corpus, values)
    recall_missing = missing_values(recall_text, values)
    answer_correct = judge_correct(answer)
    retrieved_sessions = list_strings(prediction.get("retrieved_session_ids"))
    gold_sessions = list_strings(case.get("gold_session_ids"))
    retrieval_hit = bool(set(retrieved_sessions).intersection(gold_sessions)) if gold_sessions else False
    has_prediction = bool(prediction)

    if not has_prediction:
        bucket = "missing_prediction"
    elif answer_correct:
        bucket = "correct"
    elif corpus_missing:
        bucket = "retention_miss"
    elif recall_missing:
        bucket = "recall_miss"
    else:
        bucket = "answer_miss"

    return {
        "case_id": case.get("case_id"),
        "source_id": source_id,
        "question_type": case.get("question_type") or "",
        "question": case.get("question") or "",
        "references": values,
        "answer": answer.get("answer") or "",
        "bucket": bucket,
        "answer_correct": answer_correct,
        "retrieval_hit": retrieval_hit,
        "retrieved_session_ids": retrieved_sessions,
        "gold_session_ids": gold_sessions,
        "retrieved_memory_ids": list_strings(prediction.get("retrieved_memory_ids")),
        "recall_route": nested(prediction, "metadata", "recall_route") or "",
        "recall_query": nested(prediction, "metadata", "recall_query") or "",
        "recall_search_path_counts": dict(nested(prediction, "metadata", "recall_search_path_counts") or {}),
        "recall_matched_field_counts": dict(nested(prediction, "metadata", "recall_matched_field_counts") or {}),
        "recall_lexical_hit_count": nested(prediction, "metadata", "recall_lexical_hit_count") or 0,
        "recall_semantic_hit_count": nested(prediction, "metadata", "recall_semantic_hit_count") or 0,
        "recall_top_score": nested(prediction, "metadata", "recall_top_score"),
        "recall_top_lexical_rank": nested(prediction, "metadata", "recall_top_lexical_rank") or 0,
        "recall_top_semantic_rank": nested(prediction, "metadata", "recall_top_semantic_rank") or 0,
        "retrieved_search_debug": prediction.get("retrieved_search_debug") if isinstance(prediction.get("retrieved_search_debug"), list) else [],
        "corpus_covered_value_count": len(values) - len(corpus_missing),
        "recall_covered_value_count": len(values) - len(recall_missing),
        "corpus_missing_values": corpus_missing,
        "recall_missing_values": recall_missing,
        "raw_recall_chars": len(recall_text),
    }


def missing_values(text: str, values: list[str]) -> list[str]:
    return [value for value in values if not value_is_covered(text, value)]


def judge_correct(answer: dict[str, Any]) -> bool:
    judge = answer.get("judge") if isinstance(answer.get("judge"), dict) else {}
    correct = judge.get("correct")
    if isinstance(correct, bool):
        return correct
    score = judge.get("score")
    return isinstance(score, (int, float)) and score >= 0.5


def sample_row(row: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "case_id",
        "source_id",
        "question_type",
        "bucket",
        "recall_route",
        "recall_query",
        "question",
        "references",
        "answer",
        "retrieval_hit",
        "corpus_missing_values",
        "recall_missing_values",
        "retrieved_memory_ids",
        "recall_search_path_counts",
        "recall_matched_field_counts",
        "recall_top_score",
        "retrieved_search_debug",
    )
    return {key: row.get(key) for key in keep}


def nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    seen = set()
    for item in value:
        text = str(item).strip()
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


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify ClawMem LoCoMo failures by stage.")
    parser.add_argument("--cases", required=True, help="Normalized LoCoMo cases JSONL.")
    parser.add_argument("--memories-jsonl", action="append", required=True, help="Grouped or flat ClawMem memory JSONL.")
    parser.add_argument("--predictions", required=True, help="Memory-only recall predictions JSONL.")
    parser.add_argument("--answer-metrics", required=True, help="Per-case judged answer metrics JSONL.")
    parser.add_argument("--output", help="Summary JSON output path.")
    parser.add_argument("--per-case-output", help="Per-case audit JSONL output path.")
    parser.add_argument("--max-samples", type=int, default=10, help="Samples per non-correct bucket.")
    parser.add_argument("--include-cases", action="store_true", help="Embed full per-case audit rows in summary JSON.")
    parser.add_argument("--include-empty-gold", action="store_true", help="Include cases with no reference answers.")
    parser.add_argument("--only-predicted", action="store_true", help="Audit only cases present in --predictions.")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
