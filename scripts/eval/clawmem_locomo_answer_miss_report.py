#!/usr/bin/env python3
"""Build a compact repair queue for LoCoMo answer_miss cases.

answer_miss means the memory context likely contains enough evidence, but the
answering step chose the wrong value, merged incompatible facts, or abstained.
This report is meant to drive prompt and memory-phrasing repairs without mixing
them up with retention or recall failures.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PATTERNS = {
    "abstained": re.compile(r"^\s*(?:i\s+do\s+not\s+know|i\s+don't\s+know|unknown|not\s+enough)", re.I),
    "date": re.compile(r"\b(?:when|date|day|month|year|how long)\b", re.I),
    "list_or_set": re.compile(r"\b(?:what|which)\b.*\b(?:activities|hobbies|books|movies|games|pets|places|foods|events|ways|kinds|types)\b", re.I),
    "counterfactual_or_likely": re.compile(r"\b(?:would|likely|if|considering|based on)\b", re.I),
    "advice_or_reason": re.compile(r"\b(?:why|advice|suggest|recommend|reason|motivat)\b", re.I),
    "entity_mixup": re.compile(r"\b(?:sam|evan|caroline|melanie|john|maria|joanna|nate|tim|audrey|andrew|gina|jon|james|dave|calvin)\b", re.I),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, help="Normalized LoCoMo cases JSONL.")
    parser.add_argument("--answers", required=True, help="Per-case judged answer metrics JSONL.")
    parser.add_argument("--predictions", required=True, help="Recall predictions JSONL.")
    parser.add_argument("--failure-audit", default="", help="Optional failure audit per-case JSONL.")
    parser.add_argument("--output", required=True, help="JSON report output.")
    parser.add_argument("--max-samples", type=int, default=40)
    args = parser.parse_args()

    cases = load_jsonl_by_id(args.cases)
    answers = load_jsonl_by_id(args.answers)
    predictions = load_jsonl_by_id(args.predictions)
    audit = load_jsonl_by_id(args.failure_audit) if args.failure_audit else {}

    rows = []
    for case_id, case in sorted(cases.items()):
        if not (case.get("answers") or case.get("references")):
            continue
        if audit and case_id not in audit:
            continue
        answer = answers.get(case_id, {})
        if answer_correct(answer):
            continue
        audit_row = audit.get(case_id, {})
        bucket = str(audit_row.get("bucket") or "")
        if bucket and bucket != "answer_miss":
            continue
        prediction = predictions.get(case_id, {})
        if not bucket and not prediction.get("retrieved_memory_ids"):
            continue
        rows.append(build_row(case, answer, prediction, audit_row))

    summary = summarize(rows)
    report = {
        "summary": summary,
        "samples": sample_rows(rows, args.max_samples),
        "rows": rows,
    }
    target = Path(os.path.expanduser(args.output))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_row(case: dict[str, Any], answer: dict[str, Any], prediction: dict[str, Any], audit_row: dict[str, Any]) -> dict[str, Any]:
    question = str(case.get("question") or "")
    predicted = answer_text(answer)
    pattern_tags = classify_patterns(question, predicted)
    retrieved_debug = prediction.get("retrieved_search_debug") if isinstance(prediction.get("retrieved_search_debug"), list) else []
    return {
        "case_id": case.get("case_id"),
        "source_id": case.get("source_id"),
        "question_type": case.get("question_type"),
        "question": question,
        "references": case.get("answers") or case.get("references") or [],
        "answer": predicted,
        "judge": answer.get("judge"),
        "patterns": pattern_tags,
        "recall_route": metadata_value(prediction, "recall_route"),
        "recall_query_text": metadata_value(prediction, "recall_query_text"),
        "retrieved_memory_ids": prediction.get("retrieved_memory_ids") or [],
        "top_titles": [
            str(item.get("title") or "")
            for item in retrieved_debug[:5]
            if isinstance(item, dict)
        ],
        "top_search_paths": [
            str((item.get("debug") if isinstance(item.get("debug"), dict) else {}).get("search_path") or "")
            for item in retrieved_debug[:5]
            if isinstance(item, dict)
        ],
        "audit_retrieval_hit": audit_row.get("retrieval_hit"),
        "audit_recall_missing_values": audit_row.get("recall_missing_values", []),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_source = Counter(str(row.get("source_id") or "") for row in rows)
    by_type = Counter(str(row.get("question_type") or "") for row in rows)
    by_pattern: Counter[str] = Counter()
    by_route = Counter(str(row.get("recall_route") or "") for row in rows)
    for row in rows:
        for pattern in row.get("patterns") or []:
            by_pattern[str(pattern)] += 1
    return {
        "answer_miss_count": len(rows),
        "by_source_id": dict(by_source.most_common()),
        "by_question_type": dict(by_type.most_common()),
        "by_pattern": dict(by_pattern.most_common()),
        "by_recall_route": dict(by_route.most_common()),
    }


def sample_rows(rows: list[dict[str, Any]], max_samples: int) -> list[dict[str, Any]]:
    picked = []
    seen_patterns: set[str] = set()
    for row in rows:
        patterns = row.get("patterns") or ["unclassified"]
        if any(pattern not in seen_patterns for pattern in patterns):
            picked.append(row)
            seen_patterns.update(str(pattern) for pattern in patterns)
        if len(picked) >= max_samples:
            return picked
    for row in rows:
        if row in picked:
            continue
        picked.append(row)
        if len(picked) >= max_samples:
            break
    return picked


def classify_patterns(question: str, answer: str) -> list[str]:
    tags = []
    for name, pattern in PATTERNS.items():
        target = answer if name == "abstained" else question
        if pattern.search(target or ""):
            tags.append(name)
    return tags or ["unclassified"]


def answer_correct(row: dict[str, Any]) -> bool:
    judge = row.get("judge") if isinstance(row.get("judge"), dict) else {}
    if isinstance(judge.get("correct"), bool):
        return bool(judge["correct"])
    return False


def answer_text(row: dict[str, Any]) -> str:
    for key in ("answer", "predicted_answer", "model_answer", "prediction"):
        value = row.get(key) if isinstance(row, dict) else ""
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def metadata_value(row: dict[str, Any], key: str) -> Any:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return metadata.get(key)


def load_jsonl_by_id(path: str) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    out: dict[str, dict[str, Any]] = {}
    with open(os.path.expanduser(path), "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict) and row.get("case_id"):
                out[str(row["case_id"])] = row
    return out


if __name__ == "__main__":
    raise SystemExit(main())
