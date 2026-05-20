#!/usr/bin/env python3
"""Lint ClawMem memory issue bodies for answer-complete retention.

This helper is intentionally deterministic. It does not decide whether a turn
deserves memory; it checks drafted or existing memory records for schema and
coverage mistakes that hurt recall/evaluation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from typing import Any


FORBIDDEN_META = {"memory_id", "confidence", "author_agent"}
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
YEAR_MONTH_RE = re.compile(r"\b(?:19|20)\d{2}-\d{2}\b")
MONTH_YEAR_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s*,?\s+(?:19|20)\d{2}\b",
    re.I,
)
DAY_MONTH_YEAR_RE = re.compile(
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s*,?\s+(?:19|20)\d{2}\b",
    re.I,
)
MONTH_DAY_YEAR_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+(?:19|20)\d{2}\b",
    re.I,
)
DURATION_RE = re.compile(
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a few|couple of|several)\s+"
    r"(?:day|days|week|weeks|month|months|year|years)\b",
    re.I,
)
WEEKDAY_RE = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend)\b",
    re.I,
)
RELATIVE_TIME_RE = re.compile(
    r"\b(?:yesterday|today|tomorrow|"
    r"(?:last|next|previous|following)\s+(?:day|week|month|year|weekend|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend)\s+"
    r"(?:before|after)|"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a few|couple of|several)\s+"
    r"(?:day|days|week|weeks|month|months|year|years)\s+(?:ago|before|after|earlier|later))\b",
    re.I,
)
MEMORY_SECTION_RE = re.compile(r"(?ms)^##\s+Memory\s*\n+(.+?)(?=\n##\s+|\n<!--\s*clawmem|\Z)")
RELATIONS_SECTION_RE = re.compile(r"(?ms)^##\s+Relations\s*\n+(.+?)(?=\n##\s+|\n<!--\s*clawmem|\Z)")
HIDDEN_META_RE = re.compile(r"(?ms)<!--\s*clawmem(?:-meta)?\s*\n(.+?)\n-->\s*$")
ISSUE_REF_RE = re.compile(r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#\d+")
LOSSY_PHRASE_RE = re.compile(
    r"\b(?:home country|recently|sometime|somewhere|various|several|many|"
    r"multiple|a few|some|a couple of|one of (?:the )?(?:them|those|these))\b",
    re.I,
)
SOURCE_ANCHOR_HINT_RE = re.compile(
    r"\b(?:source(?:\s+(?:date|timestamp|wording|conversation))?|sourced|"
    r"conversation|valid_from|valid_to|validity)\b",
    re.I,
)
ACTIVITY_HOOK_RE = re.compile(
    r"\b(?:kayak(?:ing)?|paint(?:ing)?|yoga|cook(?:ing)?\s+class|hiking?|"
    r"running|ski(?:ing)?|snowboarding|ice\s+skating|gym|workout|exercise|"
    r"dance|camp(?:ing)?|road\s+trip|walking|swimming|class)\b",
    re.I,
)
NEW_ACTIVITY_SIGNAL_RE = re.compile(
    r"\b(?:about\s+to\s+try|going\s+to\s+try|thinking\s+about\s+trying|"
    r"started|start(?:ing)?|took\s+up|take\s+up|new\s+(?:activity|hobby|class|sport)|"
    r"first\s+time)\b",
    re.I,
)
ACTIVITY_EVENT_SIGNAL_RE = re.compile(
    r"\b(?:about\s+to\s+try|going\s+to\s+try|thinking\s+about\s+trying|"
    r"started|start(?:ing)?|took\s+up|take\s+up|new\s+(?:activity|hobby|class|sport)|"
    r"first\s+time|went|gone|go(?:ing)?|tried|try(?:ing)?|attend(?:ed|ing)?|"
    r"signed\s+up|visited|trip)\b",
    re.I,
)
FOOD_PREF_SIGNAL_RE = re.compile(r"\b(?:weakness|crav(?:e|es|ing)|favorite|diet\s+limit|limiting)\b", re.I)
FOOD_FAVORITE_SIGNAL_RE = re.compile(r"\b(?:weakness|crav(?:e|es|ing)|favorite)\b", re.I)
FOOD_DIET_SIGNAL_RE = re.compile(r"\b(?:diet\s+limit|limiting)\b", re.I)
FOOD_VALUE_RE = re.compile(
    r"\b(?:snack|food|drink|candy|soda|ginger\s+snaps?|lasagna|poutine|"
    r"popcorn|chocolate|seltzer|recipe|meal)\b",
    re.I,
)
SPECIFIC_FOOD_VALUE_RE = re.compile(
    r"\b(?:candy|soda|ginger\s+snaps?|lasagna|poutine|popcorn|chocolate|seltzer)\b",
    re.I,
)
ADVICE_HOOK_RE = re.compile(r"\b(?:suggest(?:ed|s)?|recommend(?:ed|s)?|advis(?:ed|e|es)|tip|tips)\b", re.I)
GENERIC_TITLE_RE = re.compile(r"\b(?:memory|session|conversation|update|summary|literal anchors?)\b", re.I)
INFERENCE_SIGNAL_RE = re.compile(
    r"\b(?:likely|probably|would|would\s+not|wouldn['’]?t|could|might|if\s+(?:he|she|they|it|[A-Z][A-Za-z]+)\s+(?:had|hadn['’]?t|were|weren['’]?t)|"
    r"considered|leaning|ally|member\s+of|no longer alive|deceased)\b",
    re.I,
)
INFERENCE_BOUNDARY_RE = re.compile(
    r"\b(?:because|since|based on|basis|supported by|source (?:says|states|does not say|does not state)|"
    r"likely yes|likely no|probably|boundary|uncertain|not explicit|not stated|would likely|would not likely)\b",
    re.I,
)
SUITABILITY_SIGNAL_RE = re.compile(
    r"\b(?:suitable|good\s+(?:hobby|activity|fit|option)|would\s+enjoy|would\s+not\s+cause|wouldn['’]?t\s+cause|"
    r"cause\s+(?:discomfort|allerg(?:y|ies|ic))|safe\s+for|works?\s+for)\b",
    re.I,
)
SUITABILITY_HOOK_RE = re.compile(
    r"\b(?:suitable|good\s+(?:hobby|activity|fit|option)|would\s+enjoy|would\s+not\s+cause|wouldn['’]?t\s+cause|"
    r"safe\s+for|recommended\s+(?:hobby|activity|option)|recommendation)\b",
    re.I,
)


def read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(os.path.expanduser(path), "r", encoding="utf-8") as handle:
        return handle.read()


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def compact_for_match(value: str) -> str:
    value = normalize_text(value)
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


def extract_section(pattern: re.Pattern[str], body: str) -> str:
    match = pattern.search(body or "")
    return (match.group(1).strip() if match else "")


def parse_hidden_meta(body: str) -> dict[str, str]:
    match = HIDDEN_META_RE.search(body or "")
    if not match:
        return {}
    meta: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta


def label_names(labels: Any) -> list[str]:
    if not isinstance(labels, list):
        return []
    out: list[str] = []
    for label in labels:
        if isinstance(label, str) and label.strip():
            out.append(label.strip())
        elif isinstance(label, dict) and str(label.get("name") or "").strip():
            out.append(str(label["name"]).strip())
    return out


def issue_records_from_json(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [x for x in data["items"] if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def load_issue_json(path: str) -> list[dict[str, Any]]:
    text = read_text(path)
    try:
        return issue_records_from_json(json.loads(text))
    except json.JSONDecodeError:
        records: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                records.append(obj)
        return records


def load_expected_values(paths: list[str], inline_values: list[str]) -> list[str]:
    values = [v.strip() for v in inline_values if v.strip()]
    for path in paths:
        text = read_text(path)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            values.extend(str(v).strip() for v in parsed if str(v).strip())
        else:
            values.extend(line.strip() for line in text.splitlines() if line.strip())
    return values


def values_from_qa_jsonl(path: str) -> list[str]:
    values: list[str] = []
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        for key in ("references", "answers", "answer", "gold_answer", "expected", "target", "value"):
            if key not in row:
                continue
            raw = row[key]
            if isinstance(raw, list):
                values.extend(str(v).strip() for v in raw if str(v).strip())
            elif str(raw).strip():
                values.append(str(raw).strip())
    return values


def missing_values(text: str, expected: list[str]) -> list[str]:
    normal = normalize_text(text)
    compact = compact_for_match(text)
    missing: list[str] = []
    for value in expected:
        value_normal = normalize_text(value)
        value_compact = compact_for_match(value)
        if not value_normal:
            continue
        if value_normal in normal:
            continue
        if value_compact and value_compact in compact:
            continue
        missing.append(value)
    return missing


def has_visible_temporal_anchor(text: str) -> bool:
    return bool(
        DATE_RE.search(text)
        or YEAR_MONTH_RE.search(text)
        or MONTH_YEAR_RE.search(text)
        or YEAR_RE.search(text)
        or DURATION_RE.search(text)
    )


def has_relative_time_phrase(text: str) -> bool:
    return bool(RELATIVE_TIME_RE.search(text))


def absolute_time_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []

    def add(pattern: re.Pattern[str], kind: str) -> None:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < existing_end and end > existing_start for existing_start, existing_end, _ in spans):
                continue
            spans.append((start, end, kind))

    for pattern, kind in (
        (DATE_RE, "date"),
        (YEAR_MONTH_RE, "year_month"),
        (DAY_MONTH_YEAR_RE, "day_month_year"),
        (MONTH_DAY_YEAR_RE, "month_day_year"),
        (MONTH_YEAR_RE, "month_year"),
        (YEAR_RE, "year"),
    ):
        add(pattern, kind)
    return sorted(spans)


def source_labeled_anchor(line: str, start: int) -> bool:
    prefix = line[max(0, start - 80):start]
    segment = re.split(r"[.;()\[\]]", prefix)[-1]
    matches = list(SOURCE_ANCHOR_HINT_RE.finditer(segment))
    if not matches:
        return False
    after_source_label = segment[matches[-1].end():]
    if re.search(r"\b(?:so|therefore|meaning|means|computed|calendar|event|trip|visit|was|were|is|on|in|falls?|fell|occurred|happened)\b", after_source_label, re.I):
        return False
    return True


def has_calendar_anchor_for_relative(line: str, match: re.Match[str]) -> bool:
    for start, end, _kind in absolute_time_spans(line):
        if source_labeled_anchor(line, start):
            continue
        if end <= match.start() and match.start() - end <= 160:
            return True
        if start >= match.end() and start - match.end() <= 160:
            return True
    return False


def relative_only_time_anchors(text: str) -> list[dict[str, str]]:
    anchors: list[dict[str, str]] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for match in RELATIVE_TIME_RE.finditer(line):
            if has_calendar_anchor_for_relative(line, match):
                continue
            anchors.append({
                "phrase": match.group(0),
                "line": line[:240],
            })
    return anchors


def query_hook_warnings(text: str) -> list[str]:
    warnings: list[str] = []
    lower = text.lower()
    food_hook = food_query_hook(text)
    if food_hook and not re.search(r"\b(?:favorite\s+(?:snack|food|drink)|diet\s+limit|food\s+restriction)\b", lower):
        warnings.append(f"food/snack signal lacks likely query hook such as {food_hook}")
    if paired_activity_signal_and_value(text) and not re.search(r"\b(?:new|fun)\s+activity\b", lower):
        warnings.append("activity signal lacks likely query hook such as 'new activity' or 'fun activity' with the activity value")
    if ADVICE_HOOK_RE.search(text) and not re.search(r"\b(?:advice|recommendation)\b", lower):
        warnings.append("suggestion/recommendation signal lacks advice/recommendation query wording")
    if SUITABILITY_SIGNAL_RE.search(text) and not SUITABILITY_HOOK_RE.search(text):
        warnings.append("suitability/recommendation signal lacks query wording such as suitable, good hobby/activity, would enjoy, or would not cause discomfort")
    if INFERENCE_SIGNAL_RE.search(text) and not INFERENCE_BOUNDARY_RE.search(text):
        warnings.append("likely/counterfactual/status inference lacks visible basis or uncertainty boundary")
    return warnings


def has_food_preference_signal(text: str) -> bool:
    return bool(food_query_hook(text))


def food_favorite_value_match(text: str) -> bool:
    pref_spans = [match.span() for match in FOOD_FAVORITE_SIGNAL_RE.finditer(text)]
    food_spans = [match.span() for match in SPECIFIC_FOOD_VALUE_RE.finditer(text)]
    for pref_start, pref_end in pref_spans:
        for food_start, food_end in food_spans:
            if food_end < pref_start:
                distance = pref_start - food_end
            elif pref_end < food_start:
                distance = food_start - pref_end
            else:
                distance = 0
            if distance <= 120:
                return True
    return False


def food_diet_signal_match(text: str) -> bool:
    pref_spans = [match.span() for match in FOOD_DIET_SIGNAL_RE.finditer(text)]
    food_spans = [match.span() for match in FOOD_VALUE_RE.finditer(text)]
    for pref_start, pref_end in pref_spans:
        for food_start, food_end in food_spans:
            if food_end < pref_start:
                distance = pref_start - food_end
            elif pref_end < food_start:
                distance = food_start - pref_end
            else:
                distance = 0
            if distance <= 120:
                return True
    return False


def food_query_hook(text: str) -> str:
    if food_favorite_value_match(text):
        return "favorite snack/food, craving, weakness"
    if food_diet_signal_match(text):
        return "diet limit, food restriction"
    return ""


def paired_activity_signal_and_value(text: str) -> tuple[re.Match[str], re.Match[str]] | None:
    signal_matches = list(ACTIVITY_EVENT_SIGNAL_RE.finditer(text))
    activity_matches = list(ACTIVITY_HOOK_RE.finditer(text))
    best: tuple[int, int, re.Match[str], re.Match[str]] | None = None
    for signal_match in signal_matches:
        for activity_match in activity_matches:
            if activity_match.group(0).lower() == "class":
                before = text[max(0, activity_match.start() - 20):activity_match.start()].lower()
                if not re.search(r"\b(?:cooking|painting|yoga|dance|art|fitness)\s+$", before):
                    continue
            if activity_match.end() < signal_match.start():
                distance = signal_match.start() - activity_match.end()
            elif signal_match.end() < activity_match.start():
                distance = activity_match.start() - signal_match.end()
            else:
                distance = 0
            if distance > 180:
                continue
            candidate = (distance, signal_match.start(), signal_match, activity_match)
            if best is None or candidate[:2] < best[:2]:
                best = candidate
    if best is None:
        return None
    return best[2], best[3]


def first_sentence(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.search(r"^(.+?[.!?])(?:\s|$)", line)
        return match.group(1) if match else line
    return ""


def lint_record(record: dict[str, Any], expected: list[str], require_query_hooks: bool = False) -> dict[str, Any]:
    body = str(record.get("body") or "")
    title = str(record.get("title") or "")
    labels = label_names(record.get("labels"))
    memory = extract_section(MEMORY_SECTION_RE, body)
    relations = extract_section(RELATIONS_SECTION_RE, body)
    meta = parse_hidden_meta(body)
    searchable = "\n".join(part for part in (title, memory) if part)

    errors: list[str] = []
    warnings: list[str] = []

    if labels and "type:memory" not in labels:
        errors.append("labels do not include type:memory")
    if not memory:
        errors.append("missing non-empty ## Memory section")
    if len(memory) < 40:
        warnings.append("## Memory is very short; check for lossy summary")

    if GENERIC_TITLE_RE.fullmatch(title.strip()):
        warnings.append("title is too generic; include subject, property, value, and date/month/year when known")

    if LOSSY_PHRASE_RE.search(memory):
        warnings.append("## Memory contains possibly lossy phrasing; preserve exact names, dates, counts, and list items when known")

    if re.search(r",.+\band\b|\band\b.+,", title, flags=re.I):
        warnings.append("title may mix unrelated query intents; split unless this is one canonical set or event")

    forbidden = sorted(FORBIDDEN_META.intersection(meta))
    if forbidden:
        errors.append("forbidden hidden metadata fields: " + ", ".join(forbidden))

    if (meta.get("valid_from") or meta.get("valid_to")) and not has_visible_temporal_anchor(memory):
        warnings.append("valid_from/valid_to present but ## Memory has no visible temporal anchor")

    if has_relative_time_phrase(memory) and not has_visible_temporal_anchor(memory):
        warnings.append("relative time phrase in ## Memory lacks a visible source/event date or year anchor")

    relative_only_anchors = relative_only_time_anchors(memory)
    if relative_only_anchors:
        warnings.append("relative time phrase in ## Memory lacks a computed calendar date/month/year next to the original phrase")

    if WEEKDAY_RE.search(memory) and not has_visible_temporal_anchor(memory):
        warnings.append("weekday/weekend anchor in ## Memory lacks a visible date, month, year, or duration")

    if relations and not ISSUE_REF_RE.search(relations):
        warnings.append("## Relations has no GitHub-style issue references")

    hook_warnings = query_hook_warnings(searchable)
    if hook_warnings and require_query_hooks:
        errors.extend(hook_warnings)
    else:
        warnings.extend(hook_warnings)

    if re.search(r"\b(?:event_date|source_date)\s*:", memory, re.I):
        warnings.append("event/source dates should be natural visible memory text, not metadata-looking fields inside ## Memory")

    missing = missing_values(searchable, expected)
    if missing:
        errors.append("expected answer-bearing values missing from title/## Memory")

    return {
        "number": record.get("number"),
        "title": title,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "missing_values": missing,
        "frontloaded_missing_values": missing_values("\n".join([title, first_sentence(memory)]), expected) if expected else [],
        "relative_only_time_anchors": relative_only_anchors,
        "memory_chars": len(memory),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lint ClawMem memory issue bodies.")
    parser.add_argument("--body-file", action="append", default=[], help="Markdown body file to lint; use - for stdin.")
    parser.add_argument("--issue-json", action="append", default=[], help="Issue JSON/JSONL from gh; use - for stdin.")
    parser.add_argument("--expect", action="append", default=[], help="Expected exact value that should appear in title/## Memory.")
    parser.add_argument("--expect-file", action="append", default=[], help="Text/JSON array of expected exact values.")
    parser.add_argument("--qa-jsonl", action="append", default=[], help="QA JSONL whose answer fields should be covered by the memory corpus.")
    parser.add_argument("--require-qa-coverage", action="store_true", help="Fail when QA answers are not covered by the corpus.")
    parser.add_argument("--require-query-hooks", action="store_true", help="Fail when obvious source wording lacks likely query-hook wording.")
    parser.add_argument("--require-frontloaded-expect", action="store_true", help="Fail when expected values are absent from titles/first sentences across the linted corpus.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    records: list[dict[str, Any]] = []
    for path in args.body_file:
        records.append({"title": os.path.basename(path) if path != "-" else "stdin", "body": read_text(path)})
    for path in args.issue_json:
        records.extend(load_issue_json(path))
    if not records:
        print("clawmem_memory_lint.py: provide --body-file or --issue-json", file=sys.stderr)
        return 2

    expected = load_expected_values(args.expect_file, args.expect)
    results = [lint_record(record, expected, args.require_query_hooks) for record in records]

    qa_values: list[str] = []
    for path in args.qa_jsonl:
        qa_values.extend(values_from_qa_jsonl(path))
    coverage = None
    if qa_values:
        corpus = "\n".join(str(r.get("title") or "") + "\n" + extract_section(MEMORY_SECTION_RE, str(r.get("body") or "")) for r in records)
        missing = missing_values(corpus, qa_values)
        coverage = {
            "total_values": len(qa_values),
            "covered_values": len(qa_values) - len(missing),
            "missing_values": missing,
        }

    has_errors = any(not result["ok"] for result in results)
    has_warnings = any(result["warnings"] for result in results)
    if coverage and args.require_qa_coverage and coverage["missing_values"]:
        has_errors = True
    frontloaded_coverage = None
    if expected and args.require_frontloaded_expect:
        frontloaded_corpus = "\n".join(
            str(record.get("title") or "") + "\n" + first_sentence(extract_section(MEMORY_SECTION_RE, str(record.get("body") or "")))
            for record in records
        )
        frontloaded_missing = missing_values(frontloaded_corpus, expected)
        frontloaded_coverage = {
            "total_values": len(expected),
            "covered_values": len(expected) - len(frontloaded_missing),
            "missing_values": frontloaded_missing,
        }
        if frontloaded_missing:
            has_errors = True

    payload = {
        "ok": not has_errors and not (args.strict and has_warnings),
        "records": results,
        **({"qa_coverage": coverage} if coverage else {}),
        **({"frontloaded_expected_coverage": frontloaded_coverage} if frontloaded_coverage else {}),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
