#!/usr/bin/env python3
"""Turn LoCoMo failure audits into a deterministic ClawMem repair queue."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


STAGE_ACTIONS = {
    "retention_miss": "repair retention: add or update answer-complete memory text",
    "recall_miss": "repair recall: improve title, first sentence, query hooks, or focused canonical issue",
    "answer_miss": "repair answer prompt/guidance: memory was recalled but answerer chose the wrong value",
    "candidate_not_returned": "repair recall: backend did not return answer-bearing issue in candidate debug",
    "ranked_below_top_k": "repair recall ranking: answer-bearing issue exists but ranked below context cutoff",
    "context_missing_value": "repair context rendering: retrieved issue did not render the answer-bearing value",
    "missing_prediction": "repair harness: prediction row missing",
}


def main() -> int:
    args = build_arg_parser().parse_args()
    rows = load_rows(args.audit)
    rows = [row for row in rows if stage_of(row) not in {"correct", ""}]
    if args.stage:
        allowed = set(args.stage)
        rows = [row for row in rows if stage_of(row) in allowed]
    if args.question_type:
        allowed_qt = set(args.question_type)
        rows = [row for row in rows if str(row.get("question_type") or "") in allowed_qt]

    rows.sort(key=repair_sort_key)
    queue = [repair_item(row) for row in rows]
    summary = summarize(queue)
    payload = {"summary": summary, "items": queue[: args.limit] if args.limit else queue}

    if args.output:
        target = Path(os.path.expanduser(args.output))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if queue or not args.fail_on_empty else 1


def load_rows(paths: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        text = Path(os.path.expanduser(path)).read_text(encoding="utf-8")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("cases"), list):
            rows.extend(row for row in parsed["cases"] if isinstance(row, dict))
            continue
        if isinstance(parsed, list):
            rows.extend(row for row in parsed if isinstance(row, dict))
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected object")
            rows.append(value)
    return rows


def stage_of(row: dict[str, Any]) -> str:
    return str(row.get("bucket") or row.get("stage") or "").strip()


def repair_sort_key(row: dict[str, Any]) -> tuple[int, str, str]:
    priority = {
        "retention_miss": 0,
        "candidate_not_returned": 1,
        "recall_miss": 1,
        "ranked_below_top_k": 2,
        "context_missing_value": 2,
        "answer_miss": 3,
        "missing_prediction": 4,
    }.get(stage_of(row), 9)
    return (priority, str(row.get("source_id") or ""), str(row.get("case_id") or ""))


def repair_item(row: dict[str, Any]) -> dict[str, Any]:
    stage = stage_of(row)
    missing = list_strings(row.get("corpus_missing_values") or row.get("recall_missing_values"))
    references = list_strings(row.get("references"))
    target_values = missing or references
    retrieved = list_strings(row.get("retrieved_memory_ids"))
    matching = list_strings(row.get("matching_issue_ids"))
    action = STAGE_ACTIONS.get(stage, "inspect failure")
    hints = repair_hints(stage, row, target_values)
    return {
        "case_id": row.get("case_id"),
        "source_id": row.get("source_id"),
        "question_type": row.get("question_type") or "",
        "stage": stage,
        "action": action,
        "question": row.get("question") or "",
        "target_values": target_values,
        "current_answer": row.get("answer") or "",
        "retrieved_memory_ids": retrieved[:10],
        "matching_issue_ids": matching[:10],
        "recall_query": row.get("recall_query") or row.get("recall_query_text") or "",
        "hints": hints,
    }


def repair_hints(stage: str, row: dict[str, Any], values: list[str]) -> list[str]:
    question = str(row.get("question") or "")
    hints: list[str] = []
    if stage == "retention_miss":
        hints.append("write the missing answer value into visible ## Memory text, not only metadata or source refs")
        if "category:3" == str(row.get("question_type") or ""):
            hints.append("category:3 usually needs a supported inference/counterfactual/suitability memory with basis and uncertainty boundary")
        if any(word in question.lower() for word in ("would", "likely", "wouldn't", "could")):
            hints.append("include likely yes/no or would/would-not wording plus the basis")
    elif stage in {"recall_miss", "candidate_not_returned", "ranked_below_top_k"}:
        hints.append("frontload subject, property, and exact value in the title or first sentence")
        hints.append("add a short Query hooks sentence for likely future wording")
    elif stage == "answer_miss":
        hints.append("tighten answer guidance for conflict resolution, date granularity, or predicate matching")
        if "favorite" in question.lower():
            hints.append("prefer direct favorite/current-favorite wording over adjacent activity or gameplay memories")
            hints.append("if the right value is recalled but buried below an adjacent gameplay/tournament memory, add or retitle a focused favorite/preference query-hook memory")
        if any(value.lower().startswith(("the sunday", "the monday", "the tuesday", "the wednesday", "the thursday", "the friday", "the saturday")) for value in values):
            hints.append("if source-relative weekday wording is not visible in memory text, repair retention; source_date alone must not count as coverage")
    return hints


def summarize(queue: list[dict[str, Any]]) -> dict[str, Any]:
    by_stage = Counter(str(item["stage"]) for item in queue)
    by_question_type: dict[str, Counter[str]] = defaultdict(Counter)
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for item in queue:
        by_question_type[str(item.get("question_type") or "unknown")][str(item["stage"])] += 1
        by_source[str(item.get("source_id") or "unknown")][str(item["stage"])] += 1
    return {
        "item_count": len(queue),
        "by_stage": dict(sorted(by_stage.items())),
        "by_question_type": {key: dict(sorted(value.items())) for key, value in sorted(by_question_type.items())},
        "by_source": {key: dict(sorted(value.items())) for key, value in sorted(by_source.items())},
    }


def list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", action="append", required=True, help="Failure audit JSON or JSONL.")
    parser.add_argument("--stage", action="append", default=[], help="Limit to a failure stage/bucket.")
    parser.add_argument("--question-type", action="append", default=[], help="Limit to a question_type such as category:3.")
    parser.add_argument("--limit", type=int, default=0, help="Limit emitted repair items.")
    parser.add_argument("--output", help="Write JSON repair queue.")
    parser.add_argument("--fail-on-empty", action="store_true", help="Exit 1 when no repair items remain.")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
