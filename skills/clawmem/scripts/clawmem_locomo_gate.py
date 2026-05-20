#!/usr/bin/env python3
"""Audit Locomo memory extraction for answer-bearing value coverage.

This helper is deterministic. It compares Locomo QA reference values with the
memory text produced for each source conversation/repo. It is meant for eval
runners and retention harnesses, not for deciding whether a live user turn
deserves memory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from typing import Any


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from clawmem_memory_lint import (  # noqa: E402
    MEMORY_SECTION_RE,
    extract_section,
    missing_values,
    relative_only_time_anchors,
)


MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
MONTH_NAMES_BY_NUMBER = {
    1: ("jan", "january"),
    2: ("feb", "february"),
    3: ("mar", "march"),
    4: ("apr", "april"),
    5: ("may",),
    6: ("jun", "june"),
    7: ("jul", "july"),
    8: ("aug", "august"),
    9: ("sep", "sept", "september"),
    10: ("oct", "october"),
    11: ("nov", "november"),
    12: ("dec", "december"),
}


def read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(os.path.expanduser(path), "r", encoding="utf-8") as handle:
        return handle.read()


def iter_jsonl(paths: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for line in read_text(path).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}: invalid JSONL line: {exc}") from exc
            if isinstance(row, dict):
                rows.append(row)
    return rows


def source_id_for(row: dict[str, Any], fallback: str = "unknown") -> str:
    for key in ("source_id", "conversation_id", "conv_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    repo = str(row.get("repo") or row.get("repository") or "").strip()
    return repo or fallback


def memory_text(row: dict[str, Any]) -> str:
    title = str(row.get("title") or "")
    if row.get("memory") is not None:
        body = str(row.get("memory") or "")
    else:
        body = extract_section(MEMORY_SECTION_RE, str(row.get("body") or ""))
    return "\n".join(part for part in (title, body) if part)


def load_memory_groups(paths: list[str], source_filter: set[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for row in iter_jsonl(paths):
        if isinstance(row.get("memories"), list):
            parent_source = source_id_for(row)
            for item in row["memories"]:
                if not isinstance(item, dict):
                    continue
                source_id = source_id_for(item, parent_source)
                if source_filter and source_id not in source_filter:
                    continue
                text = memory_text(item)
                if text:
                    groups[source_id].append(text)
            continue

        source_id = source_id_for(row)
        if source_filter and source_id not in source_filter:
            continue
        text = memory_text(row)
        if text:
            groups[source_id].append(text)
    return groups


def reference_values(row: dict[str, Any]) -> list[str]:
    for key in ("references", "answers", "gold_answer", "expected", "target", "answer", "value"):
        value = row.get(key)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def load_qa_cases(paths: list[str], source_filter: set[str]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in iter_jsonl(paths):
        source_id = source_id_for(row)
        if source_filter and source_id not in source_filter:
            continue
        values = reference_values(row)
        if not values:
            continue
        groups[source_id].append(
            {
                "case_id": row.get("case_id"),
                "question_type": row.get("question_type"),
                "values": values,
            }
        )
    return groups


def date_aliases(value: str) -> list[str]:
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value.strip(), flags=re.I)
    aliases: list[str] = []

    for match in re.finditer(
        r"\b(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})\b",
        text,
        flags=re.I,
    ):
        day = int(match.group(1))
        month = MONTHS.get(match.group(2).lower())
        year = int(match.group(3))
        if month:
            aliases.append(f"{year:04d}-{month:02d}-{day:02d}")

    for match in re.finditer(
        r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b",
        text,
        flags=re.I,
    ):
        month = MONTHS.get(match.group(1).lower())
        day = int(match.group(2))
        year = int(match.group(3))
        if month:
            aliases.append(f"{year:04d}-{month:02d}-{day:02d}")

    for match in re.finditer(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b", text):
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        aliases.append(f"{year:04d}-{month:02d}-{day:02d}")

    for match in re.finditer(r"\b([A-Za-z]+),?\s+(\d{4})\b", text, flags=re.I):
        month = MONTHS.get(match.group(1).lower())
        year = int(match.group(2))
        if month:
            aliases.append(f"{year:04d}-{month:02d}")

    return list(dict.fromkeys(aliases))


def relative_weekday_date_aliases(value: str) -> list[str]:
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value.strip(), flags=re.I)
    match = re.search(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+"
        r"(before|after)\s+(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})\b",
        text,
        flags=re.I,
    )
    if not match:
        return []
    weekday = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }[match.group(1).lower()]
    direction = match.group(2).lower()
    day = int(match.group(3))
    month = MONTHS.get(match.group(4).lower())
    year = int(match.group(5))
    if not month:
        return []
    anchor = date(year, month, day)
    if direction == "before":
        delta = (anchor.weekday() - weekday) % 7 or 7
        target = anchor - timedelta(days=delta)
    else:
        delta = (weekday - anchor.weekday()) % 7 or 7
        target = anchor + timedelta(days=delta)
    return [
        target.isoformat(),
        f"{match.group(1)} {direction} {anchor.isoformat()}",
        f"{match.group(1)} {direction} {day} {match.group(4)} {year}",
    ]


def month_year_reference(value: str) -> str:
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value.strip(), flags=re.I)
    text = text.strip(" .\"'`()[]{}")
    text = re.sub(r"^(?:in|during|around|about)\s+", "", text, flags=re.I)
    if re.search(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", text):
        return ""
    if re.search(r"\b\d{1,2}\s+[A-Za-z]+,?\s+\d{4}\b", text, flags=re.I):
        return ""
    if re.search(r"\b[A-Za-z]+\s+\d{1,2},?\s+\d{4}\b", text, flags=re.I):
        return ""

    match = re.fullmatch(r"([A-Za-z]+),?\s+(\d{4})", text, flags=re.I)
    if match:
        month = MONTHS.get(match.group(1).lower())
        if month:
            return f"{int(match.group(2)):04d}-{month:02d}"

    match = re.fullmatch(r"(\d{4})[/-](\d{1,2})", text)
    if match:
        month = int(match.group(2))
        if 1 <= month <= 12:
            return f"{int(match.group(1)):04d}-{month:02d}"

    return ""


def has_visible_month_year(corpus: str, canonical_month: str) -> bool:
    year, month_text = canonical_month.split("-", 1)
    month = int(month_text)
    if re.search(rf"(?<!\d){re.escape(canonical_month)}(?!-\d)(?!\d)", corpus):
        return True
    for name in MONTH_NAMES_BY_NUMBER.get(month, ()):
        if re.search(rf"\b{re.escape(name)}\s*,?\s+{year}\b", corpus, flags=re.I):
            return True
    return False


def exact_dates_for_month(corpus: str, canonical_month: str) -> list[str]:
    return list(dict.fromkeys(re.findall(rf"(?<!\d){re.escape(canonical_month)}-\d{{2}}(?!\d)", corpus)))


def date_granularity_mismatch(corpus: str, value: str) -> dict[str, Any] | None:
    canonical_month = month_year_reference(value)
    if not canonical_month or has_visible_month_year(corpus, canonical_month):
        return None
    exact_dates = exact_dates_for_month(corpus, canonical_month)
    if not exact_dates:
        return None
    return {
        "value": value,
        "expected_granularity": canonical_month,
        "over_specific_dates": exact_dates[:5],
    }


def split_list_value(value: str) -> list[str]:
    if not re.search(r"[,;]|\s+(?:and|or)\s+", value, flags=re.I):
        return []
    expanded = re.sub(r"\s+(?:and|or)\s+", ",", value, flags=re.I)
    parts = []
    for raw in re.split(r"[,;]", expanded):
        part = raw.strip(" .\"'`()[]{}")
        part = re.sub(r"^(?:and|or|the|a|an|both)\s+", "", part, flags=re.I)
        if len(part) >= 3:
            parts.append(part)
    return parts if len(parts) >= 2 else []


def value_is_covered(corpus: str, value: str, allow_split: bool = True) -> bool:
    relative_aliases = relative_weekday_date_aliases(value)
    if relative_aliases:
        return any(not missing_values(corpus, [candidate]) for candidate in relative_aliases)

    for candidate in [value, *date_aliases(value)]:
        if not missing_values(corpus, [candidate]):
            return True

    if allow_split:
        parts = split_list_value(value)
        if parts and all(value_is_covered(corpus, part, allow_split=False) for part in parts):
            return True

    return False


def source_report(
    source_id: str,
    memories: list[str],
    cases: list[dict[str, Any]],
    max_missing: int,
) -> dict[str, Any]:
    corpus = "\n\n".join(memories)
    missing: list[dict[str, Any]] = []
    granularity_mismatches: list[dict[str, Any]] = []
    granularity_mismatch_count = 0
    relative_only_samples: list[dict[str, Any]] = []
    relative_only_count = 0
    value_count = 0
    covered_values = 0
    covered_cases = 0
    by_question_type: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "case_count": 0,
            "covered_cases": 0,
            "missing_cases": 0,
            "value_count": 0,
            "covered_values": 0,
            "missing_values": 0,
        }
    )

    for case in cases:
        values = [value for value in case["values"] if value]
        value_count += len(values)
        case_covered = True
        question_type = str(case.get("question_type") or "unknown")
        by_question_type[question_type]["case_count"] += 1
        by_question_type[question_type]["value_count"] += len(values)

        for value in values:
            covered = value_is_covered(corpus, value)
            if covered:
                covered_values += 1
                by_question_type[question_type]["covered_values"] += 1
            else:
                case_covered = False
                by_question_type[question_type]["missing_values"] += 1
                if len(missing) < max_missing:
                    missing.append(
                        {
                            "case_id": case.get("case_id"),
                            "question_type": case.get("question_type"),
                            "value": value,
                        }
                    )
            mismatch = date_granularity_mismatch(corpus, value)
            if mismatch:
                granularity_mismatch_count += 1
                if len(granularity_mismatches) < max_missing:
                    granularity_mismatches.append(
                        {
                            "case_id": case.get("case_id"),
                            "question_type": case.get("question_type"),
                            **mismatch,
                        }
                    )

        if case_covered:
            covered_cases += 1
            by_question_type[question_type]["covered_cases"] += 1
        else:
            by_question_type[question_type]["missing_cases"] += 1

    for stats in by_question_type.values():
        stats["value_coverage"] = ratio(stats["covered_values"], stats["value_count"])
        stats["case_coverage"] = ratio(stats["covered_cases"], stats["case_count"])

    for memory_index, memory in enumerate(memories, 1):
        for anchor in relative_only_time_anchors(memory):
            relative_only_count += 1
            if len(relative_only_samples) < max_missing:
                relative_only_samples.append({
                    "memory_index": memory_index,
                    **anchor,
                })

    return {
        "source_id": source_id,
        "memory_count": len(memories),
        "case_count": len(cases),
        "covered_cases": covered_cases,
        "missing_cases": len(cases) - covered_cases,
        "case_coverage": ratio(covered_cases, len(cases)),
        "value_count": value_count,
        "covered_values": covered_values,
        "missing_values": value_count - covered_values,
        "value_coverage": ratio(covered_values, value_count),
        "missing_values_sample": missing,
        "date_granularity_mismatch_count": granularity_mismatch_count,
        "date_granularity_mismatch_sample": granularity_mismatches,
        "relative_only_time_anchor_count": relative_only_count,
        "relative_only_time_anchor_sample": relative_only_samples,
        "by_question_type": dict(sorted(by_question_type.items())),
    }


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(numerator / denominator, 4)


def aggregate_question_types(reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "case_count": 0,
            "covered_cases": 0,
            "missing_cases": 0,
            "value_count": 0,
            "covered_values": 0,
            "missing_values": 0,
        }
    )
    for report in reports:
        by_question_type = report.get("by_question_type")
        if not isinstance(by_question_type, dict):
            continue
        for question_type, stats in by_question_type.items():
            if not isinstance(stats, dict):
                continue
            target = merged[str(question_type)]
            for key in ("case_count", "covered_cases", "missing_cases", "value_count", "covered_values", "missing_values"):
                target[key] += int(stats.get(key) or 0)

    out: dict[str, dict[str, Any]] = {}
    for question_type, stats in sorted(merged.items()):
        out[question_type] = {
            **stats,
            "case_coverage": ratio(stats["covered_cases"], stats["case_count"]),
            "value_coverage": ratio(stats["covered_values"], stats["value_count"]),
        }
    return out


def parse_question_type_thresholds(values: list[str]) -> dict[str, float]:
    thresholds: dict[str, float] = {}
    for raw in values:
        value = raw.strip()
        if not value:
            continue
        if "=" not in value:
            raise SystemExit(f"invalid --min-question-type-value-coverage {raw!r}; expected question_type=0.75")
        question_type, threshold_text = value.split("=", 1)
        question_type = question_type.strip()
        if not question_type:
            raise SystemExit(f"invalid --min-question-type-value-coverage {raw!r}; missing question type")
        try:
            threshold = float(threshold_text.strip())
        except ValueError as exc:
            raise SystemExit(f"invalid --min-question-type-value-coverage {raw!r}; threshold must be a number") from exc
        if threshold < 0 or threshold > 1:
            raise SystemExit(f"invalid --min-question-type-value-coverage {raw!r}; threshold must be between 0 and 1")
        thresholds[question_type] = threshold
    return thresholds


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Locomo QA value coverage in ClawMem memories.")
    parser.add_argument(
        "--memories-jsonl",
        action="append",
        required=True,
        help="Locomo memory JSONL: grouped rows with memories[] or flat memory rows.",
    )
    parser.add_argument(
        "--qa-jsonl",
        action="append",
        required=True,
        help="Locomo QA/per-case JSONL with source_id and references.",
    )
    parser.add_argument("--source-id", action="append", default=[], help="Limit the audit to one source_id.")
    parser.add_argument("--min-value-coverage", type=float, default=0.0, help="Fail below this value coverage.")
    parser.add_argument("--min-case-coverage", type=float, default=0.0, help="Fail below this case coverage.")
    parser.add_argument(
        "--min-question-type-value-coverage",
        action="append",
        default=[],
        metavar="TYPE=FLOAT",
        help="Fail when a global question type's value coverage is below the threshold, for example category:2=0.70.",
    )
    parser.add_argument(
        "--min-question-type-case-coverage",
        action="append",
        default=[],
        metavar="TYPE=FLOAT",
        help="Fail when a global question type's case coverage is below the threshold, for example category:3=0.50.",
    )
    parser.add_argument("--max-missing-per-source", type=int, default=20, help="Missing value samples to report.")
    parser.add_argument(
        "--fail-on-date-granularity-mismatch",
        action="store_true",
        help="Fail when a month/year reference is covered only by an over-specific YYYY-MM-DD memory value.",
    )
    parser.add_argument(
        "--fail-on-relative-only-time",
        action="store_true",
        help="Fail when memory text keeps relative time phrases without a computed calendar date/month/year nearby.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    source_filter = {source_id.strip() for source_id in args.source_id if source_id.strip()}
    memory_groups = load_memory_groups(args.memories_jsonl, source_filter)
    qa_groups = load_qa_cases(args.qa_jsonl, source_filter)

    source_ids = sorted(set(memory_groups) | set(qa_groups))
    reports = [
        source_report(
            source_id,
            memory_groups.get(source_id, []),
            qa_groups.get(source_id, []),
            args.max_missing_per_source,
        )
        for source_id in source_ids
    ]

    global_case_count = sum(report["case_count"] for report in reports)
    global_covered_cases = sum(report["covered_cases"] for report in reports)
    global_missing_cases = sum(report["missing_cases"] for report in reports)
    global_value_count = sum(report["value_count"] for report in reports)
    global_covered_values = sum(report["covered_values"] for report in reports)
    global_missing_values = sum(report["missing_values"] for report in reports)
    global_date_granularity_mismatches = sum(report["date_granularity_mismatch_count"] for report in reports)
    global_relative_only_time_anchors = sum(report["relative_only_time_anchor_count"] for report in reports)
    global_by_question_type = aggregate_question_types(reports)
    global_report = {
        "source_count": len(source_ids),
        "memory_count": sum(report["memory_count"] for report in reports),
        "case_count": global_case_count,
        "covered_cases": global_covered_cases,
        "missing_cases": global_missing_cases,
        "case_coverage": ratio(global_covered_cases, global_case_count),
        "value_count": global_value_count,
        "covered_values": global_covered_values,
        "missing_values": global_missing_values,
        "value_coverage": ratio(global_covered_values, global_value_count),
        "date_granularity_mismatch_count": global_date_granularity_mismatches,
        "relative_only_time_anchor_count": global_relative_only_time_anchors,
        "by_question_type": global_by_question_type,
    }

    errors: list[str] = []
    if not source_ids:
        errors.append("no matching source_id records found")
    if global_case_count == 0:
        errors.append("no QA cases found")
    if args.fail_on_date_granularity_mismatch and global_date_granularity_mismatches:
        errors.append(
            f"{global_date_granularity_mismatches} date granularity mismatch(es): "
            "month/year references were covered only by over-specific exact dates"
        )
    if args.fail_on_relative_only_time and global_relative_only_time_anchors:
        errors.append(
            f"{global_relative_only_time_anchors} relative-only time anchor(s): "
            "relative phrases need computed calendar dates/months/years nearby"
        )
    question_type_thresholds = parse_question_type_thresholds(args.min_question_type_value_coverage)
    question_type_case_thresholds = parse_question_type_thresholds(args.min_question_type_case_coverage)
    for question_type, threshold in sorted(question_type_thresholds.items()):
        coverage = global_by_question_type.get(question_type, {}).get("value_coverage")
        if coverage is None:
            errors.append(f"question type {question_type!r} not found")
        elif coverage < threshold:
            errors.append(
                f"question type {question_type!r} value coverage {coverage:.4f} below {threshold:.4f}"
            )
    for question_type, threshold in sorted(question_type_case_thresholds.items()):
        coverage = global_by_question_type.get(question_type, {}).get("case_coverage")
        if coverage is None:
            errors.append(f"question type {question_type!r} not found")
        elif coverage < threshold:
            errors.append(
                f"question type {question_type!r} case coverage {coverage:.4f} below {threshold:.4f}"
            )

    ok = (
        not errors
        and global_report["value_coverage"] >= args.min_value_coverage
        and global_report["case_coverage"] >= args.min_case_coverage
    )
    payload = {
        "ok": ok,
        "errors": errors,
        "min_value_coverage": args.min_value_coverage,
        "min_case_coverage": args.min_case_coverage,
        "min_question_type_value_coverage": question_type_thresholds,
        "min_question_type_case_coverage": question_type_case_thresholds,
        "fail_on_date_granularity_mismatch": args.fail_on_date_granularity_mismatch,
        "fail_on_relative_only_time": args.fail_on_relative_only_time,
        "global": global_report,
        "sources": reports,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
