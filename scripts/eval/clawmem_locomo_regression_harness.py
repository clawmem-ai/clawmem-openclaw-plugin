#!/usr/bin/env python3
"""Evaluate a fixed high-signal LoCoMo regression slice.

This harness keeps a small, stable set of cases that exercise the failure modes
we have been fixing in ClawMem: answer-complete retention, query hooks, date
granularity, profile/list consolidation, counterfactuals, and artifact facts.
It reads judged answer JSONL or per-case answer metrics JSONL and optionally
compares them with a baseline run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_CASE_IDS = [
    # conv-26: dates, profiles, lists, counterfactuals, image/artifact facts.
    "locomo:conv-26:q0000",
    "locomo:conv-26:q0005",
    "locomo:conv-26:q0010",
    "locomo:conv-26:q0014",
    "locomo:conv-26:q0015",
    "locomo:conv-26:q0022",
    "locomo:conv-26:q0030",
    "locomo:conv-26:q0042",
    "locomo:conv-26:q0050",
    "locomo:conv-26:q0101",
    "locomo:conv-26:q0103",
    # conv-30: favorites, business/project attribute sets, shared arcs.
    "locomo:conv-30:q0039",
    "locomo:conv-30:q0041",
    "locomo:conv-30:q0023",
    "locomo:conv-30:q0025",
    # conv-41: new activities, community work, advice, photo effects.
    "locomo:conv-41:q0054",
    "locomo:conv-41:q0067",
    "locomo:conv-41:q0077",
    "locomo:conv-41:q0107",
    "locomo:conv-41:q0138",
    "locomo:conv-41:q0144",
    # conv-42: exact favorites, media sets, allergy inference, screenplay timing.
    "locomo:conv-42:q0004",
    "locomo:conv-42:q0022",
    "locomo:conv-42:q0042",
    "locomo:conv-42:q0051",
    "locomo:conv-42:q0075",
    "locomo:conv-42:q0095",
    # conv-43: inferred company, new activity, images, signed artifacts.
    "locomo:conv-43:q0008",
    "locomo:conv-43:q0067",
    "locomo:conv-43:q0093",
    "locomo:conv-43:q0095",
    "locomo:conv-43:q0119",
    "locomo:conv-43:q0157",
    # conv-44: pet activity/inference and workshop motivation.
    "locomo:conv-44:q0019",
    "locomo:conv-44:q0054",
    "locomo:conv-44:q0068",
    # conv-47/48/50: exact class/reason/photo/project details.
    "locomo:conv-47:q0124",
    "locomo:conv-48:q0034",
    "locomo:conv-48:q0070",
    "locomo:conv-50:q0156",
    # conv-49: known query-hook and routing sentinels.
    "locomo:conv-49:q0014",
    "locomo:conv-49:q0059",
    "locomo:conv-49:q0060",
    "locomo:conv-49:q0086",
    "locomo:conv-49:q0109",
    "locomo:conv-49:q0114",
    "locomo:conv-49:q0147",
    "locomo:conv-49:q0153",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, help="Normalized LoCoMo cases JSONL.")
    parser.add_argument("--answers", required=True, help="Candidate judged answers or per-case metrics JSONL.")
    parser.add_argument("--baseline-answers", default="", help="Optional baseline judged answers or per-case metrics JSONL.")
    parser.add_argument("--case-id", action="append", default=[], help="Additional case_id to include.")
    parser.add_argument("--case-id-file", action="append", default=[], help="Text/JSON/JSONL case id file.")
    parser.add_argument("--no-default-cases", action="store_true", help="Use only explicit --case-id/--case-id-file values.")
    parser.add_argument("--subset-output", default="", help="Write selected cases JSONL for answer/recall subset runs.")
    parser.add_argument("--output", default="", help="Write JSON report.")
    args = parser.parse_args()

    cases = load_jsonl_by_id(args.cases)
    candidate = load_jsonl_by_id(args.answers)
    baseline = load_jsonl_by_id(args.baseline_answers) if args.baseline_answers else {}

    selected_ids = []
    if not args.no_default_cases:
        selected_ids.extend(DEFAULT_CASE_IDS)
    selected_ids.extend(args.case_id)
    for path in args.case_id_file:
        selected_ids.extend(load_case_ids(path))
    selected_ids = unique_nonempty(selected_ids)

    selected_cases = [cases[case_id] for case_id in selected_ids if case_id in cases]
    missing_cases = [case_id for case_id in selected_ids if case_id not in cases]
    rows = [
        compare_case(case, candidate.get(str(case.get("case_id")), {}), baseline.get(str(case.get("case_id")), {}))
        for case in selected_cases
    ]

    report = {
        "case_count": len(selected_cases),
        "missing_case_ids": missing_cases,
        "candidate": aggregate(rows, "candidate"),
        **({"baseline": aggregate(rows, "baseline")} if baseline else {}),
        **({"transition_counts": dict(transition_counts(rows))} if baseline else {}),
        "by_source_id": aggregate_by(rows, "source_id"),
        "by_question_type": aggregate_by(rows, "question_type"),
        "improved_case_ids": [row["case_id"] for row in rows if row.get("transition") == "wrong->right"],
        "regressed_case_ids": [row["case_id"] for row in rows if row.get("transition") == "right->wrong"],
        "rows": rows,
    }

    if args.subset_output:
        write_jsonl(args.subset_output, selected_cases)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report_summary(report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def compare_case(case: dict[str, Any], candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    candidate_correct = answer_correct(candidate)
    baseline_correct = answer_correct(baseline) if baseline else None
    row = {
        "case_id": case.get("case_id"),
        "source_id": case.get("source_id"),
        "question_type": case.get("question_type"),
        "question": case.get("question"),
        "references": case.get("answers") or case.get("references") or [],
        "candidate_answer": answer_text(candidate),
        "candidate_correct": candidate_correct,
        "candidate_score": answer_score(candidate),
    }
    if baseline:
        row.update({
            "baseline_answer": answer_text(baseline),
            "baseline_correct": baseline_correct,
            "baseline_score": answer_score(baseline),
            "transition": transition_name(baseline_correct, candidate_correct),
        })
    return row


def aggregate(rows: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    values = [row.get(f"{prefix}_correct") for row in rows if row.get(f"{prefix}_correct") is not None]
    scores = [row.get(f"{prefix}_score") for row in rows if isinstance(row.get(f"{prefix}_score"), (int, float))]
    correct = sum(1 for value in values if value is True)
    return {
        "evaluated": len(values),
        "correct": correct,
        "accuracy": round(correct / len(values), 4) if values else None,
        "avg_score": round(sum(float(score) for score in scores) / len(scores), 4) if scores else None,
    }


def aggregate_by(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "")].append(row)
    return {
        group_key: {
            "case_count": len(group_rows),
            "candidate": aggregate(group_rows, "candidate"),
            **({"transitions": dict(transition_counts(group_rows))} if any("transition" in row for row in group_rows) else {}),
        }
        for group_key, group_rows in sorted(grouped.items())
    }


def transition_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        transition = row.get("transition")
        if transition:
            counts[str(transition)] += 1
    return counts


def transition_name(before: bool | None, after: bool | None) -> str:
    if before is None or after is None:
        return "unknown"
    return ("right" if before else "wrong") + "->" + ("right" if after else "wrong")


def answer_correct(row: dict[str, Any]) -> bool | None:
    if not row:
        return None
    judge = row.get("judge") if isinstance(row.get("judge"), dict) else {}
    if isinstance(judge.get("correct"), bool):
        return bool(judge["correct"])
    for key in ("judge_correct", "correct"):
        if isinstance(row.get(key), bool):
            return bool(row[key])
    score = answer_score(row)
    return score >= 0.5 if score is not None else None


def answer_score(row: dict[str, Any]) -> float | None:
    if not row:
        return None
    judge = row.get("judge") if isinstance(row.get("judge"), dict) else {}
    for value in (judge.get("score"), row.get("judge_score"), row.get("score")):
        if isinstance(value, (int, float)):
            return float(value)
    return None


def answer_text(row: dict[str, Any]) -> str:
    for key in ("answer", "predicted_answer", "model_answer", "prediction"):
        value = row.get(key) if isinstance(row, dict) else ""
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def report_summary(report: dict[str, Any]) -> dict[str, Any]:
    out = {
        "case_count": report["case_count"],
        "candidate": report["candidate"],
        "missing_case_ids": report["missing_case_ids"],
        "improved_case_ids": report["improved_case_ids"],
        "regressed_case_ids": report["regressed_case_ids"],
    }
    if "baseline" in report:
        out["baseline"] = report["baseline"]
        out["transition_counts"] = report["transition_counts"]
    return out


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


def load_case_ids(path: str) -> list[str]:
    text = Path(os.path.expanduser(path)).read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return [str(value).strip() for value in parsed if str(value).strip()]
    ids = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            ids.append(line)
            continue
        if isinstance(row, dict) and row.get("case_id"):
            ids.append(str(row["case_id"]))
        elif isinstance(row, str):
            ids.append(row)
    return ids


def unique_nonempty(values: list[str]) -> list[str]:
    out = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    target = Path(os.path.expanduser(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
