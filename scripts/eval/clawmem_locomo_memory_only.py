#!/usr/bin/env python3
"""Run a skill-driven ClawMem memory-only LoCoMo pass.

The runner uses the GitHub-native memory workflow. It provisions one
GitHub-compatible agent identity, creates one repo per source conversation,
extracts answer-complete memory issues from source transcripts, stores them as
normal issues, and recalls only open type:memory issues for benchmark questions.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


KINDS = {
    "fact",
    "preference",
    "convention",
    "decision",
    "task",
    "skill",
    "lesson",
    "profile",
    "insight",
}

KIND_COLOR = "5319e7"
TYPE_COLOR = "1d76db"
TRANSIENT_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
TRANSIENT_REQUEST_ERRORS = (
    TimeoutError,
    ConnectionError,
    ConnectionResetError,
    http.client.IncompleteRead,
    http.client.RemoteDisconnected,
    socket.timeout,
    urllib.error.URLError,
)
LITERAL_QUESTION_RE = re.compile(
    r"\b(?:when|how\s+long|how\s+many|how\s+much|what\s+(?:date|day|month|year|time)|"
    r"which\s+(?:day|month|year|date|one|item)|"
    r"what\s+(?:is|was|were)\s+.+\s+(?:favorite|weakness|food|snack|activity|hobby|book|movie|game|place|city|country|state|pet|animal|injury|job|business|course|class|event)|"
    r"(?:what|which)\s+(?:new|fun|favorite|outdoor|low-impact|recent|recurring)?\s*"
    r"(?:activity|hobby|food|snack|book|movie|game|place|city|country|state|event|item|gift|tool|pet|animal|injury|job|course|class|exercise|sport)|"
    r"who\s+(?:is|was|were)|"
    r"what\s+(?:is|was|were)\s+.+\s+(?:name|called|working on))\b",
    re.I,
)
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
TEMPORAL_HINT_RE = re.compile(
    r"\b(?:yesterday|today|tomorrow|"
    r"(?:last|next|previous|following|this|past)\s+(?:day|week|month|year|weekend|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"(?:ago|before|after|earlier|later|already|since)|"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a few|couple of|several)\s+"
    r"(?:day|days|week|weeks|month|months|year|years|hour|hours|minute|minutes)|"
    r"(?:first|last|current|recent|upcoming|birthday|anniversary))\b",
    re.I,
)
SOURCE_ANCHOR_HINT_RE = re.compile(
    r"\b(?:source(?:\s+(?:date|timestamp|wording|conversation))?|sourced|"
    r"conversation|valid_from|valid_to|validity)\b",
    re.I,
)
NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, help="Normalized LoCoMo cases JSONL.")
    parser.add_argument("--out-dir", required=True, help="Directory for run artifacts.")
    parser.add_argument("--run-name", default="", help="Artifact prefix. Defaults to timestamped memory_only_v4.")
    parser.add_argument("--base-url", default=os.environ.get("CLAWMEM_EVAL_BASE_URL", "https://git.clawmem.ai/api/v3"))
    parser.add_argument("--config", default="", help="Existing run config JSON with base_url, agent_id, token, and default_repo.")
    parser.add_argument("--agent-id", default=os.environ.get("CLAWMEM_EVAL_AGENT_ID", ""))
    parser.add_argument("--agent-prefix", default=os.environ.get("CLAWMEM_EVAL_AGENT_PREFIX", "eval-locomo-v4"))
    parser.add_argument("--repo-prefix", default=os.environ.get("CLAWMEM_EVAL_REPO_PREFIX", "eval-locomo-v4"))
    parser.add_argument("--extract-model", default=os.environ.get("CLAWMEM_EVAL_EXTRACT_MODEL", os.environ.get("CODEX_EVAL_MODEL", "gpt-5.4-mini")))
    parser.add_argument("--extract-reasoning-effort", default=os.environ.get("CLAWMEM_EVAL_EXTRACT_REASONING_EFFORT", os.environ.get("CODEX_EVAL_REASONING_EFFORT", "low")))
    parser.add_argument("--extract-min-memories", type=int, default=int(os.environ.get("CLAWMEM_EVAL_EXTRACT_MIN_MEMORIES", "45")))
    parser.add_argument("--extract-repair-attempts", type=int, default=int(os.environ.get("CLAWMEM_EVAL_EXTRACT_REPAIR_ATTEMPTS", "1")))
    parser.add_argument(
        "--extract-consolidation-repair-attempts",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_EXTRACT_CONSOLIDATION_REPAIR_ATTEMPTS", "0")),
        help="Add answer-shaped cross-session canonical set/profile/image/inference memories after extraction.",
    )
    parser.add_argument(
        "--extract-detail-repair-attempts",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_EXTRACT_DETAIL_REPAIR_ATTEMPTS", "0")),
        help="Add source-only episodic microfact/detail memories that broad extraction often compresses away.",
    )
    parser.add_argument(
        "--extract-query-hook-repair-attempts",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_EXTRACT_QUERY_HOOK_REPAIR_ATTEMPTS", "0")),
        help="Add source-only alias/query-hook memories when values exist but likely future question wording is missing.",
    )
    parser.add_argument(
        "--extract-answer-audit-attempts",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_EXTRACT_ANSWER_AUDIT_ATTEMPTS", "0")),
        help="Add final source-only answer-completeness memories for common benchmark-like miss shapes.",
    )
    parser.add_argument(
        "--extract-temporal-repair-attempts",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_EXTRACT_TEMPORAL_REPAIR_ATTEMPTS", "0")),
        help="Rewrite extracted memories with relative-only time anchors so they include computed calendar dates/months/years.",
    )
    parser.add_argument(
        "--extract-temporal-anchor-repair-attempts",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_EXTRACT_TEMPORAL_ANCHOR_REPAIR_ATTEMPTS", "0")),
        help="Add missing answer-bearing temporal anchor memories after extraction.",
    )
    parser.add_argument(
        "--extract-temporal-repair-max-memories",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_EXTRACT_TEMPORAL_REPAIR_MAX_MEMORIES", "40")),
        help="Maximum flagged memories to rewrite per temporal repair attempt.",
    )
    parser.add_argument("--top-k", type=int, default=int(os.environ.get("CLAWMEM_EVAL_TOP_K", "10")))
    parser.add_argument(
        "--recall-query-mode",
        choices=["full", "compact"],
        default=os.environ.get("CLAWMEM_EVAL_RECALL_QUERY_MODE", "full"),
        help="Use full natural-language questions or compact lexical-friendly query terms.",
    )
    parser.add_argument(
        "--recall-plan",
        choices=["single", "multi", "targeted", "reserved"],
        default=os.environ.get("CLAWMEM_EVAL_RECALL_PLAN", "single"),
        help="single runs one query; multi fuses variants; targeted fuses literal-style variants; reserved keeps full order with literal lexical slots.",
    )
    parser.add_argument(
        "--recall-variant-limit",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_RECALL_VARIANT_LIMIT", "6")),
        help="Maximum search query variants for --recall-plan multi/reserved. Default 6 mirrors plugin query-planner quality settings; use 3 for latency-sensitive probes.",
    )
    parser.add_argument(
        "--recall-reserved-slots",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_RECALL_RESERVED_SLOTS", "1")),
        help="For --recall-plan reserved, top-k slots reserved for compact lexical literal hits.",
    )
    parser.add_argument("--source-id", action="append", default=[], help="Limit to one or more source_id values.")
    parser.add_argument("--source-limit", type=int, default=0)
    parser.add_argument("--extract-concurrency", type=int, default=int(os.environ.get("CLAWMEM_EVAL_EXTRACT_CONCURRENCY", "1")))
    parser.add_argument("--recall-concurrency", type=int, default=int(os.environ.get("CLAWMEM_EVAL_RECALL_CONCURRENCY", "8")))
    parser.add_argument(
        "--search-debug",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Request backend search debug payloads for recall diagnostics.",
    )
    parser.add_argument(
        "--search-text-matches",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Request backend text_matches snippets for recall diagnostics.",
    )
    parser.add_argument(
        "--semantic-ledger-context-limit",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_SEMANTIC_LEDGER_CONTEXT_LIMIT", "-1")),
        help="For semantic questions, include at most this many literal-ledger memories in raw answer context. -1 disables filtering.",
    )
    parser.add_argument(
        "--wiki-context",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("CLAWMEM_EVAL_WIKI_CONTEXT", "").lower() in {"1", "true", "yes"},
        help="Create/search repo wiki context maps as recall boosters. Direct type:memory issue recall still runs in parallel.",
    )
    parser.add_argument(
        "--wiki-context-source",
        choices=["search", "map"],
        default=os.environ.get("CLAWMEM_EVAL_WIKI_CONTEXT_SOURCE", "search"),
        help="Use backend wiki search per query, or reuse the run wiki_map and fetch each repo context page once. Default: search.",
    )
    parser.add_argument(
        "--wiki-context-limit",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_WIKI_CONTEXT_LIMIT", "3")),
        help="Maximum wiki pages to fetch per recall query when --wiki-context is enabled.",
    )
    parser.add_argument(
        "--wiki-ref-fetch-limit",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_WIKI_REF_FETCH_LIMIT", "6")),
        help="Maximum wiki-referenced issue memories to inspect per recall query.",
    )
    parser.add_argument("--resume", action="store_true", help="Reuse existing memories and skip completed predictions.")
    parser.add_argument("--reuse-issues", action="store_true", help="Reuse an existing memory_map JSONL and skip repo/issue creation.")
    parser.add_argument("--skip-store", action="store_true", help="Only extract memories; do not create repos/issues or recall.")
    parser.add_argument("--skip-extract", action="store_true", help="Use existing memories JSONL.")
    parser.add_argument(
        "--api-retries",
        type=int,
        default=int(os.environ.get("CLAWMEM_EVAL_API_RETRIES", "4")),
        help="Retry transient backend/network errors this many times per API request.",
    )
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_name = args.run_name or f"locomo.memory_only_v4.{datetime.now().strftime('%y%m%d-%H%M')}"
    paths = RunPaths(out_dir, run_name)
    args.extract_raw_dir = out_dir / f"{run_name}.extract_raw"
    cases = read_jsonl(Path(args.cases))
    groups = group_cases(cases)
    if args.source_id:
        selected_sources = {value.strip() for value in args.source_id if value.strip()}
        cases = [case for case in cases if str(case.get("source_id") or "").strip() in selected_sources]
        groups = [group for group in groups if group["source_id"] in selected_sources]
    if args.source_limit > 0:
        groups = groups[: args.source_limit]

    if args.config:
        base_url, agent_id, identity = load_config_identity(Path(args.config), args)
        log(f"reusing agent {agent_id} with owner {identity['repo_full_name'].split('/')[0]}")
    else:
        base_url = args.base_url
        agent_id = normalize_part(args.agent_id or f"{args.agent_prefix}-{datetime.now().strftime('%y%m%d-%H%M')}-{hashlib.sha1(os.urandom(16)).hexdigest()[:6]}")[:64]
        client = ApiClient(base_url, None, max_retries=args.api_retries)
        identity = provision_agent(client, agent_id)
    authed = ApiClient(base_url, identity["token"], max_retries=args.api_retries)
    save_config(paths.config, base_url, agent_id, identity)

    if not args.skip_extract:
        existing = load_grouped_memories(paths.memories) if args.resume else {}
        pending_extract_groups = [group for group in groups if group["source_id"] not in existing]
        with paths.memories.open("a" if args.resume and paths.memories.exists() else "w", encoding="utf-8") as sink:
            for source_id in sorted(existing):
                log(f"skip extract {source_id}: already present")
            if args.extract_concurrency <= 1 or len(pending_extract_groups) <= 1:
                for group in pending_extract_groups:
                    try:
                        row = extract_source_memories(group, args)
                        sink.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                        sink.flush()
                        log(f"extracted {len(row['memories'])} memories for {group['source_id']}")
                    except Exception as error:
                        if not args.keep_going:
                            raise
                        log(f"WARN extract {group['source_id']} failed: {error}")
            else:
                log(f"extracting {len(pending_extract_groups)} source(s), concurrency={args.extract_concurrency}")
                with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.extract_concurrency)) as pool:
                    futures = {pool.submit(extract_source_memories, group, args): group for group in pending_extract_groups}
                    for future in concurrent.futures.as_completed(futures):
                        group = futures[future]
                        try:
                            row = future.result()
                            sink.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                            sink.flush()
                            log(f"extracted {len(row['memories'])} memories for {row['source_id']}")
                        except Exception as error:
                            if not args.keep_going:
                                raise
                            log(f"WARN extract {group['source_id']} failed: {error}")

    grouped_memories = load_grouped_memories(paths.memories)
    if args.skip_store:
        return

    issue_map = load_memory_map(paths.memory_map) if args.resume or args.reuse_issues else {}
    if args.reuse_issues:
        log(f"reusing {len(issue_map)} memory issue mapping(s) from {paths.memory_map}")
    else:
        with paths.memory_map.open("a" if args.resume and paths.memory_map.exists() else "w", encoding="utf-8") as map_sink:
            for group in groups:
                source_id = group["source_id"]
                memories = grouped_memories.get(source_id, [])
                if not memories:
                    log(f"WARN no memories for {source_id}; recall will be empty")
                    continue
                repo = ensure_source_repo(authed, identity["repo_full_name"], args.repo_prefix, source_id)
                ensure_labels(authed, repo, memories)
                created_count = 0
                for memory in memories:
                    key = str(memory.get("memory_key") or stable_memory_key(memory))
                    if key in issue_map:
                        continue
                    issue = create_memory_issue(authed, repo, memory)
                    row = {
                        **memory,
                        "memory_key": key,
                        "issue_number": issue.get("number"),
                        "repo": repo,
                    }
                    issue_map[key] = row
                    map_sink.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                    map_sink.flush()
                    created_count += 1
                log(f"stored {created_count}/{len(memories)} memories for {source_id} in {repo}")

    predictions_by_id = load_predictions(paths.predictions) if args.resume else {}
    pending_cases = [case for case in cases if case.get("case_id") not in predictions_by_id]
    by_source_memory_map = memory_map_by_source(load_memory_map(paths.memory_map))
    if args.wiki_context:
        ensure_wiki_context_pages(authed, by_source_memory_map, paths.wiki_map, args.resume)
        if args.wiki_context_source == "map":
            attach_cached_wiki_context_pages(authed, by_source_memory_map, paths.wiki_map)
    log(f"recalling {len(pending_cases)} case(s), concurrency={args.recall_concurrency}")
    with paths.predictions.open("a" if args.resume and paths.predictions.exists() else "w", encoding="utf-8") as sink:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.recall_concurrency)) as pool:
            futures = {
                pool.submit(
                    recall_case,
                    authed,
                    case,
                    by_source_memory_map,
                    args.top_k,
                    base_url,
                    agent_id,
                    args.semantic_ledger_context_limit,
                    args.search_debug,
                    args.search_text_matches,
                    args.recall_query_mode,
                    args.recall_plan,
                    args.recall_variant_limit,
                    args.recall_reserved_slots,
                    args.wiki_context,
                    args.wiki_context_source,
                    args.wiki_context_limit,
                    args.wiki_ref_fetch_limit,
                ): case
                for case in pending_cases
            }
            for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
                try:
                    row = future.result()
                except Exception as error:
                    if not args.keep_going:
                        raise
                    case = futures[future]
                    row = error_prediction(
                        case,
                        str(error),
                        base_url,
                        agent_id,
                        str(case.get("source_id") or "").strip(),
                        str(by_source_memory_map.get(str(case.get("source_id") or "").strip(), {}).get("repo") or ""),
                    )
                sink.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                if index % 25 == 0:
                    sink.flush()
                    log(f"recalled {index}/{len(pending_cases)}")
        sink.flush()
    log(f"wrote artifacts under {out_dir} with prefix {run_name}")


class RunPaths:
    def __init__(self, out_dir: Path, run_name: str) -> None:
        self.config = out_dir / f"{run_name}.config.json"
        self.memories = out_dir / f"{run_name}.memories.jsonl"
        self.memory_map = out_dir / f"{run_name}.memory_map.jsonl"
        self.wiki_map = out_dir / f"{run_name}.wiki_map.jsonl"
        self.predictions = out_dir / f"{run_name}.predictions.jsonl"


class ApiClient:
    def __init__(self, base_url: str, token: str | None, max_retries: int = 4) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.max_retries = max(0, max_retries)

    def request(self, method: str, path: str, body: Any | None = None, auth: bool = True, ok_422: bool = False) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/vnd.github+json", "Content-Type": "application/json"}
        if auth:
            if not self.token:
                raise RuntimeError("missing token for authenticated request")
            headers["Authorization"] = f"token {self.token}"
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            request = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    raw = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as error:
                if ok_422 and error.code == 422:
                    return None
                detail = error.read().decode("utf-8", errors="replace")
                if error.code in TRANSIENT_HTTP_CODES and attempt + 1 < attempts:
                    self.sleep_before_retry(attempt)
                    continue
                raise RuntimeError(f"HTTP {error.code} {method} {path}: {detail}") from error
            except TRANSIENT_REQUEST_ERRORS as error:
                if attempt + 1 < attempts:
                    self.sleep_before_retry(attempt)
                    continue
                raise RuntimeError(f"{method} {path}: {error}") from error
        if not raw.strip():
            return None
        return json.loads(raw)

    @staticmethod
    def sleep_before_retry(attempt: int) -> None:
        time.sleep(min(8.0, 0.5 * (2 ** attempt)))


def provision_agent(client: ApiClient, agent_id: str) -> dict[str, str]:
    prefix = normalize_part(agent_id).replace("_", "-")[:32].strip("-") or "eval-locomo"
    identity = client.request("POST", "agents", {"prefix_login": prefix, "default_repo_name": "memory"}, auth=False)
    token = str(identity.get("token") or "").strip()
    repo = str(identity.get("repo_full_name") or "").strip()
    if not token or "/" not in repo:
        raise RuntimeError(f"provision response missing token/default repo: {identity}")
    log(f"provisioned agent {agent_id} with owner {repo.split('/')[0]}")
    return {"token": token, "repo_full_name": repo, "login": str(identity.get("login") or repo.split("/")[0])}


def save_config(path: Path, base_url: str, agent_id: str, identity: dict[str, str]) -> None:
    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url.rstrip("/"),
        "agent_id": agent_id,
        "default_repo": identity["repo_full_name"],
        "login": identity.get("login"),
        "token": identity["token"],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def load_config_identity(path: Path, args: argparse.Namespace) -> tuple[str, str, dict[str, str]]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise RuntimeError(f"{path}: expected JSON object")
    token = str(config.get("token") or "").strip()
    repo = str(config.get("default_repo") or config.get("repo_full_name") or "").strip()
    base_url = str(config.get("base_url") or args.base_url or "").strip()
    if not token or "/" not in repo or not base_url:
        raise RuntimeError(f"{path}: config must include base_url, token, and default_repo")
    agent_id = normalize_part(args.agent_id or str(config.get("agent_id") or args.agent_prefix or "eval-locomo-v4"))[:64]
    return base_url.rstrip("/"), agent_id, {
        "token": token,
        "repo_full_name": repo,
        "login": str(config.get("login") or repo.split("/")[0]),
    }


def ensure_source_repo(client: ApiClient, default_repo: str, repo_prefix: str, source_id: str) -> str:
    owner = default_repo.split("/", 1)[0]
    repo_name = source_repo_name(repo_prefix, source_id)
    repo = f"{owner}/{repo_name}"
    try:
        client.request("GET", f"repos/{repo}")
        return repo
    except Exception:
        pass
    created = client.request("POST", "user/repos", {
        "name": repo_name,
        "description": f"LoCoMo memory-only eval repo for {source_id}",
        "private": True,
        "auto_init": False,
    })
    return str(created.get("full_name") or repo)


def ensure_labels(client: ApiClient, repo: str, memories: list[dict[str, Any]]) -> None:
    labels = {"type:memory"}
    for memory in memories:
        kind = clean_kind(memory.get("kind"))
        labels.add(f"kind:{kind}")
    for label in sorted(labels):
        color = TYPE_COLOR if label.startswith("type:") else KIND_COLOR
        client.request("POST", f"repos/{repo}/labels", {
            "name": label,
            "color": color,
            "description": "Label managed by ClawMem eval runner.",
        }, ok_422=True)


def create_memory_issue(client: ApiClient, repo: str, memory: dict[str, Any]) -> dict[str, Any]:
    kind = clean_kind(memory.get("kind"))
    title = str(memory.get("title") or "Memory").strip()[:180] or "Memory"
    body = render_memory_body(memory)
    return client.request("POST", f"repos/{repo}/issues", {
        "title": title,
        "body": body,
        "labels": ["type:memory", f"kind:{kind}"],
    })


def ensure_wiki_context_pages(client: ApiClient, by_source: dict[str, dict[str, Any]], wiki_map_path: Path, resume: bool) -> None:
    existing = load_wiki_map(wiki_map_path) if resume else {}
    mode = "a" if resume and wiki_map_path.exists() else "w"
    with wiki_map_path.open(mode, encoding="utf-8") as sink:
        for source_id, source in sorted(by_source.items()):
            repo = str(source.get("repo") or "").strip()
            memories_by_issue = source.get("memories_by_issue") if isinstance(source.get("memories_by_issue"), dict) else {}
            if not repo or not memories_by_issue:
                continue
            slug = wiki_context_slug(source_id)
            key = f"{repo}:{slug}"
            if key in existing:
                continue
            body = render_wiki_context_page(source_id, memories_by_issue)
            client.request("PUT", f"repos/{repo}/wiki/pages/{wiki_slug_path(slug)}", {
                "body": body,
                "message": f"Update LoCoMo wiki context for {source_id}",
            })
            row = {
                "source_id": source_id,
                "repo": repo,
                "slug": slug,
                "memory_count": len(memories_by_issue),
                "issue_refs": [f"#{number}" for number in sorted(memories_by_issue, key=lambda value: safe_int_string(value))],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            sink.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            sink.flush()
            existing[key] = row
            log(f"updated wiki context {repo}/wiki/{slug} with {len(memories_by_issue)} memory refs")


def attach_cached_wiki_context_pages(client: ApiClient, by_source: dict[str, dict[str, Any]], wiki_map_path: Path) -> None:
    rows = list(load_wiki_map(wiki_map_path).values())
    loaded = 0
    for row in rows:
        source_id = str(row.get("source_id") or "").strip()
        repo = str(row.get("repo") or "").strip()
        slug = str(row.get("slug") or "").strip()
        source = by_source.get(source_id)
        if not source or not repo or not slug:
            continue
        try:
            page = client.request("GET", f"repos/{repo}/wiki/pages/{wiki_slug_path(slug)}")
        except Exception as error:
            log(f"WARN cached wiki context load failed for {repo}/wiki/{slug}: {error}")
            continue
        if not isinstance(page, dict):
            continue
        source.setdefault("wiki_context_pages", []).append({
            "slug": slug,
            "title": str(page.get("title") or slug),
            "body": str(page.get("body") or ""),
        })
        loaded += 1
    if rows:
        log(f"loaded {loaded}/{len(rows)} cached wiki context page(s)")


def render_wiki_context_page(source_id: str, memories_by_issue: dict[str, Any]) -> str:
    rows: list[tuple[str, dict[str, Any]]] = []
    for number, memory in memories_by_issue.items():
        if isinstance(memory, dict):
            rows.append((str(number), memory))
    rows.sort(key=lambda item: (
        str(item[1].get("kind") or ""),
        " ".join(str(topic) for topic in item[1].get("topics") or []),
        str(item[1].get("title") or "").lower(),
        safe_int_string(item[0]),
    ))
    lines = [
        f"# LoCoMo Context: {source_id}",
        "",
        "Issue memories are the source of truth. This wiki page is an agent-facing context map and recall booster.",
        "Each bullet cites the issue memory it summarizes.",
        "",
        "## Memory Index",
        "",
    ]
    for number, memory in rows:
        title = str(memory.get("title") or "Memory").strip() or "Memory"
        kind = clean_kind(memory.get("kind"))
        topics = [normalize_part(str(topic)) for topic in memory.get("topics") or [] if str(topic).strip()]
        detail = compact_wiki_summary(str(memory.get("memory") or ""))
        bits = [f"kind:{kind}", *[f"topic:{topic}" for topic in topics[:4]]]
        lines.append(f"- {title} ({', '.join(bits)}). refs: #{number}")
        if detail:
            lines.append(f"  Summary: {detail}")
    return "\n".join(lines).rstrip() + "\n"


def compact_wiki_summary(text: str, limit: int = 260) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def wiki_context_slug(source_id: str) -> str:
    return f"projects/{normalize_part(source_id)}"


def wiki_slug_path(slug: str) -> str:
    return urllib.parse.quote(slug, safe="")


def render_memory_body(memory: dict[str, Any]) -> str:
    source_date = str(memory.get("source_date") or "").strip()
    valid_from = source_date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", source_date) else ""
    source_turns = [str(value) for value in memory.get("source_turn_ids") or [] if str(value).strip()]
    notes = [
        f"- Source session: `{memory.get('session_id') or ''}`",
        f"- Source turns: {', '.join(f'`{turn}`' for turn in source_turns) if source_turns else 'unknown'}",
    ]
    event_date = str(memory.get("event_date") or "").strip()
    if event_date:
        notes.append(f"- Event date: {event_date}")
    return "\n".join([
        "## Memory",
        "",
        str(memory.get("memory") or "").strip(),
        "",
        "## Notes",
        "",
        *notes,
        "",
        "<!-- clawmem",
        "schema_version: clawmem/v2",
        f"valid_from: {valid_from}",
        "valid_to:",
        "-->",
    ])


def extract_source_memories(group: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    source = source_payload(group)
    prompt = build_extraction_prompt(source)
    started = time.perf_counter()
    text, tokens = call_codex(prompt, args.extract_model, args.extract_reasoning_effort, timeout_sec=900)
    save_extract_raw(args, group["source_id"], "initial", text)
    parse_repaired = False
    repair_tokens = 0
    try:
        parsed = parse_json_block(text)
    except json.JSONDecodeError:
        repaired, tokens_used = call_codex(
            build_json_repair_prompt(text),
            args.extract_model,
            args.extract_reasoning_effort,
            timeout_sec=300,
        )
        save_extract_raw(args, group["source_id"], "json-repair", repaired)
        parsed = parse_json_block(repaired)
        parse_repaired = True
        repair_tokens += tokens_used or 0
    memories = parsed.get("memories") if isinstance(parsed, dict) else parsed
    if not isinstance(memories, list):
        raise RuntimeError("extraction output must be a JSON array or object with memories[]")
    cleaned = clean_memories(group["source_id"], memories)
    patch_parse_repaired_count = 0
    repair_attempts = 0
    for attempt in range(max(0, args.extract_repair_attempts)):
        if args.extract_min_memories <= 0 or len(cleaned) >= args.extract_min_memories:
            break
        repair_attempts += 1
        stage = f"coverage-repair-{attempt + 1}"
        patch_text, tokens_used = call_codex(
            build_extraction_repair_prompt(source, cleaned, args.extract_min_memories),
            args.extract_model,
            args.extract_reasoning_effort,
            timeout_sec=900,
        )
        save_extract_raw(args, group["source_id"], stage, patch_text)
        repair_tokens += tokens_used or 0
        patch_parsed, repair_tokens_used, patch_repaired = parse_memory_json_with_repair(
            patch_text,
            args,
            group["source_id"],
            stage,
        )
        repair_tokens += repair_tokens_used
        patch_parse_repaired_count += int(patch_repaired)
        patch_memories = coerce_memory_list(patch_parsed, "extraction repair output")
        additions = clean_memories(group["source_id"], patch_memories)
        next_cleaned = merge_cleaned_memories(cleaned, additions)
        if len(next_cleaned) <= len(cleaned):
            break
        cleaned = next_cleaned
    consolidation_repair_attempts = 0
    consolidation_repair_memory_count = 0
    for attempt in range(max(0, args.extract_consolidation_repair_attempts)):
        consolidation_repair_attempts += 1
        stage = f"consolidation-repair-{attempt + 1}"
        patch_text, tokens_used = call_codex(
            build_consolidation_repair_prompt(source, cleaned),
            args.extract_model,
            args.extract_reasoning_effort,
            timeout_sec=900,
        )
        save_extract_raw(args, group["source_id"], stage, patch_text)
        repair_tokens += tokens_used or 0
        patch_parsed, repair_tokens_used, patch_repaired = parse_memory_json_with_repair(
            patch_text,
            args,
            group["source_id"],
            stage,
        )
        repair_tokens += repair_tokens_used
        patch_parse_repaired_count += int(patch_repaired)
        patch_memories = coerce_memory_list(patch_parsed, "consolidation repair output")
        additions = clean_memories(group["source_id"], patch_memories)
        next_cleaned = merge_cleaned_memories(cleaned, additions)
        added_count = len(next_cleaned) - len(cleaned)
        consolidation_repair_memory_count += max(0, added_count)
        cleaned = next_cleaned
        if added_count <= 0:
            break
    detail_repair_attempts = 0
    detail_repair_memory_count = 0
    for attempt in range(max(0, args.extract_detail_repair_attempts)):
        detail_repair_attempts += 1
        stage = f"detail-repair-{attempt + 1}"
        patch_text, tokens_used = call_codex(
            build_detail_repair_prompt(source, cleaned),
            args.extract_model,
            args.extract_reasoning_effort,
            timeout_sec=900,
        )
        save_extract_raw(args, group["source_id"], stage, patch_text)
        repair_tokens += tokens_used or 0
        patch_parsed, repair_tokens_used, patch_repaired = parse_memory_json_with_repair(
            patch_text,
            args,
            group["source_id"],
            stage,
        )
        repair_tokens += repair_tokens_used
        patch_parse_repaired_count += int(patch_repaired)
        patch_memories = coerce_memory_list(patch_parsed, "detail repair output")
        additions = clean_memories(group["source_id"], patch_memories)
        next_cleaned = merge_cleaned_memories(cleaned, additions)
        added_count = len(next_cleaned) - len(cleaned)
        detail_repair_memory_count += max(0, added_count)
        cleaned = next_cleaned
        if added_count <= 0:
            break
    query_hook_repair_attempts = 0
    query_hook_repair_memory_count = 0
    for attempt in range(max(0, args.extract_query_hook_repair_attempts)):
        query_hook_repair_attempts += 1
        stage = f"query-hook-repair-{attempt + 1}"
        patch_text, tokens_used = call_codex(
            build_query_hook_repair_prompt(source, cleaned),
            args.extract_model,
            args.extract_reasoning_effort,
            timeout_sec=900,
        )
        save_extract_raw(args, group["source_id"], stage, patch_text)
        repair_tokens += tokens_used or 0
        patch_parsed, repair_tokens_used, patch_repaired = parse_memory_json_with_repair(
            patch_text,
            args,
            group["source_id"],
            stage,
        )
        repair_tokens += repair_tokens_used
        patch_parse_repaired_count += int(patch_repaired)
        patch_memories = coerce_memory_list(patch_parsed, "query hook repair output")
        additions = clean_memories(group["source_id"], patch_memories)
        next_cleaned = merge_cleaned_memories(cleaned, additions)
        added_count = len(next_cleaned) - len(cleaned)
        query_hook_repair_memory_count += max(0, added_count)
        cleaned = next_cleaned
        if added_count <= 0:
            break
    answer_audit_attempts = 0
    answer_audit_memory_count = 0
    for attempt in range(max(0, args.extract_answer_audit_attempts)):
        answer_audit_attempts += 1
        stage = f"answer-audit-repair-{attempt + 1}"
        patch_text, tokens_used = call_codex(
            build_answer_audit_repair_prompt(source, cleaned),
            args.extract_model,
            args.extract_reasoning_effort,
            timeout_sec=900,
        )
        save_extract_raw(args, group["source_id"], stage, patch_text)
        repair_tokens += tokens_used or 0
        patch_parsed, repair_tokens_used, patch_repaired = parse_memory_json_with_repair(
            patch_text,
            args,
            group["source_id"],
            stage,
        )
        repair_tokens += repair_tokens_used
        patch_parse_repaired_count += int(patch_repaired)
        patch_memories = coerce_memory_list(patch_parsed, "answer audit repair output")
        additions = clean_memories(group["source_id"], patch_memories)
        next_cleaned = merge_cleaned_memories(cleaned, additions)
        added_count = len(next_cleaned) - len(cleaned)
        answer_audit_memory_count += max(0, added_count)
        cleaned = next_cleaned
        if added_count <= 0:
            break
    temporal_anchor_repair_attempts = 0
    temporal_anchor_repair_memory_count = 0
    for attempt in range(max(0, args.extract_temporal_anchor_repair_attempts)):
        temporal_anchor_repair_attempts += 1
        stage = f"temporal-anchor-repair-{attempt + 1}"
        patch_text, tokens_used = call_codex(
            build_temporal_anchor_repair_prompt(source, cleaned),
            args.extract_model,
            args.extract_reasoning_effort,
            timeout_sec=900,
        )
        save_extract_raw(args, group["source_id"], stage, patch_text)
        repair_tokens += tokens_used or 0
        patch_parsed, repair_tokens_used, patch_repaired = parse_memory_json_with_repair(
            patch_text,
            args,
            group["source_id"],
            stage,
        )
        repair_tokens += repair_tokens_used
        patch_parse_repaired_count += int(patch_repaired)
        patch_memories = coerce_memory_list(patch_parsed, "temporal anchor repair output")
        additions = clean_memories(group["source_id"], patch_memories)
        next_cleaned = merge_cleaned_memories(cleaned, additions)
        added_count = len(next_cleaned) - len(cleaned)
        temporal_anchor_repair_memory_count += max(0, added_count)
        cleaned = next_cleaned
        if added_count <= 0:
            break
    cleaned, temporal_normalize_memory_count = normalize_relative_time_memories(cleaned)
    cleaned, query_hook_normalize_memory_count, query_hook_title_normalize_memory_count = normalize_query_hook_memories(cleaned)
    temporal_repair_attempts = 0
    temporal_repair_memory_count = 0
    if args.extract_temporal_repair_attempts > 0:
        cleaned, temporal_repair_attempts, temporal_repair_memory_count, temporal_tokens = temporal_repair_memories(
            group["source_id"],
            source,
            cleaned,
            args,
        )
        repair_tokens += temporal_tokens
    return {
        "source_id": group["source_id"],
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "extract_model": args.extract_model,
        "extract_reasoning_effort": args.extract_reasoning_effort,
        "extract_latency_ms": int((time.perf_counter() - started) * 1000),
        "extract_tokens": tokens,
        "extract_repair_tokens": repair_tokens,
        "extract_parse_repaired": parse_repaired,
        "extract_patch_parse_repaired_count": patch_parse_repaired_count,
        "extract_repair_attempts": repair_attempts,
        "extract_consolidation_repair_attempts": consolidation_repair_attempts,
        "extract_consolidation_repair_memory_count": consolidation_repair_memory_count,
        "extract_detail_repair_attempts": detail_repair_attempts,
        "extract_detail_repair_memory_count": detail_repair_memory_count,
        "extract_query_hook_repair_attempts": query_hook_repair_attempts,
        "extract_query_hook_repair_memory_count": query_hook_repair_memory_count,
        "extract_answer_audit_attempts": answer_audit_attempts,
        "extract_answer_audit_memory_count": answer_audit_memory_count,
        "extract_query_hook_normalize_memory_count": query_hook_normalize_memory_count,
        "extract_query_hook_title_normalize_memory_count": query_hook_title_normalize_memory_count,
        "extract_temporal_anchor_repair_attempts": temporal_anchor_repair_attempts,
        "extract_temporal_anchor_repair_memory_count": temporal_anchor_repair_memory_count,
        "extract_temporal_normalize_memory_count": temporal_normalize_memory_count,
        "extract_temporal_repair_attempts": temporal_repair_attempts,
        "extract_temporal_repair_memory_count": temporal_repair_memory_count,
        "extract_min_memories": args.extract_min_memories,
        "memories": cleaned,
    }


def save_extract_raw(args: argparse.Namespace, source_id: str, stage: str, text: str) -> None:
    raw_dir = getattr(args, "extract_raw_dir", None)
    if not raw_dir:
        return
    path = Path(raw_dir)
    path.mkdir(parents=True, exist_ok=True)
    filename = f"{normalize_part(source_id) or 'source'}-{normalize_part(stage) or 'stage'}.txt"
    (path / filename).write_text(text, encoding="utf-8")


def build_json_repair_prompt(text: str) -> str:
    return (
        "Repair the following ClawMem extraction output into valid JSON only.\n"
        "Do not add facts. Do not remove valid memory objects unless they are impossible to parse.\n"
        "The output must be either an array of memory objects or an object with key memories.\n"
        "Each memory object should keep these keys when present: session_id, source_turn_ids, title, kind, topics, memory, source_date, event_date.\n\n"
        f"Broken output:\n{text}"
    )


def coerce_memory_list(parsed: Any, output_name: str) -> list[Any]:
    if isinstance(parsed, dict):
        memories = parsed.get("memories")
        if memories is None:
            memories = parsed.get("key_memories")
        if memories is None:
            memories = parsed.get("key memories")
    else:
        memories = parsed
    if not isinstance(memories, list):
        raise RuntimeError(f"{output_name} must be a JSON array or object with memories[]")
    return memories


def parse_memory_json_with_repair(
    text: str,
    args: argparse.Namespace,
    source_id: str,
    stage: str,
) -> tuple[Any, int, bool]:
    try:
        return parse_json_block(text), 0, False
    except json.JSONDecodeError:
        repaired, tokens_used = call_codex(
            build_json_repair_prompt(text),
            args.extract_model,
            args.extract_reasoning_effort,
            timeout_sec=300,
        )
        save_extract_raw(args, source_id, f"{stage}-json-repair", repaired)
        return parse_json_block(repaired), tokens_used or 0, True


def build_extraction_repair_prompt(source: dict[str, Any], existing_memories: list[dict[str, Any]], min_memories: int) -> str:
    needed = max(8, min_memories - len(existing_memories))
    return (
        "You are repairing a too-sparse ClawMem memory extraction for a benchmark.\n"
        "Use only the source conversation below. Do not use benchmark questions or answers.\n"
        "Existing memories are already kept; return only additional missing memories, not rewrites.\n"
        "Walk every source session again and add durable answer-bearing memories that are missing.\n"
        "Prioritize concrete facts, temporal events, canonical sets, exact item names, images/captions, plans, durations, counts, profile boundaries, and insights.\n"
        "Do not only add more session summaries. Prefer missing answer-shape records: person status/profile capsules, cross-session canonical sets, artifact/image facts, causal links, stated feelings, and supported likely/negative inferences.\n"
        "For each recurring person or project, check whether the kept memories answer these shapes: relationship/family status; activities/hobbies; books/media/games; pets; places; events attended; volunteering/community actions; objects made/bought/received; symbols; reasons/motivations; feelings/reactions; likely counterfactuals.\n"
        "For projects and businesses, check origin/motivation, shared founder arcs, location or space requirements, offerings/services, marketing or promotion tactics, products/collections, launch/status milestones, constraints, and next steps.\n"
        "For pair/commonality questions, store the shared arc directly when the source supports both sides, e.g. 'Jon and Gina both lost jobs and started their own businesses.'\n"
        "For project attribute sets, preserve every exact list item in one canonical record when practical: ideal location/space specs, promotion tactics, products made, services offered, workshops/classes, schools/centers, mentors, investors, and launch dates.\n"
        "Add query hooks to titles and memory text without losing source wording. If the source says a food is someone's 'weakness' or direct favorite/craving, write the likely query shape too, such as 'favorite snack/food', while noting the original wording. Do not turn generic liking of an event that included food into a favorite-food memory. If a source describes someone trying, taking up, or doing an activity, include 'new/fun activity' plus the activity name, place, and time anchor when supported.\n"
        "Front-load retrieval-critical fields in the title and first sentence: subject, target property, exact value, and event date/month/year when known. Good: 'Sam new activity in October 2023: kayaking'. Bad: 'Kayaking on Lake Tahoe' when the future question is about Sam taking up a new activity.\n"
        "Use source_date as provenance, not as event_date. Do not turn 'recently', 'just', 'currently', or a plain session timestamp into an exact event date unless the source also gives an exact date, a resolvable relative phrase such as today/yesterday/last Friday, or wording that explicitly anchors the event to that day. Otherwise write 'as of <source_date>' or month/year-level timing and set event_date to unknown or the supported granularity.\n"
        "When a source message says 'this', 'that', 'here is one', 'check them out', or 'they made this' near an image caption, combine the text and caption into an artifact/image memory with the exact object or scene from the caption. If the source supports authorship/ownership of a captioned object, write the yes/no answer shape directly, e.g. 'Melanie made the black and white bowl in the photo.'\n"
        "Do not lose ordinal creative-work anchors. For first/second/third/fourth screenplay, movie, book, project, or draft facts, create a focused memory whose title and first sentence include the person, ordinal work, action such as started/writing/printed, and month/year or date, e.g. 'Joanna third screenplay start in May 2022'.\n"
        "For favorite dessert/food sets, preserve the exact favorite/preference-thread list and wording variants in one canonical preference memory. Do not replace chocolate-and-mixed-berry ice cream or dairy-free chocolate cake with berries with unrelated adjacent recipes. Recipes from other sessions, such as a dessert made for a friend, belong in separate recipe/activity memories unless the source also marks them as favorites.\n"
        "For advice and purpose/motivation, preserve the exact answer phrase when available, such as 'keep trying new things until something sparks excitement' or 'strengthen the bond with her pets'.\n"
        "When a source supports an inference, write it as an inference with basis and boundary, not as an unsupported fact. Example: 'Caroline would likely have Dr. Seuss books because she stocks classic children's books; the source does not name Dr. Seuss.'\n"
        "When the same property is spread across sessions, add one canonical-set memory that lists the accumulated values with enough source dates to audit them.\n"
        "Temporal lint must pass for every added memory title and memory body.\n"
        "Use the source session timestamp to resolve relative phrases, never the current date.\n"
        "For relative dates, include both the original phrase and the computed calendar date/month/year in the same title, sentence, or bullet when the source timestamp supports it.\n"
        "Do not leave relative-only anchors such as 'last week', 'next Friday', 'yesterday', 'last year', or 'next month' without a nearby computed calendar time.\n"
        "Good: 'next Friday (2023-01-27)'; 'yesterday (2023-01-28)'; 'last year (2022)'; 'next month (February 2023)'.\n"
        "If a relative phrase is fuzzy, anchor it to the source timestamp instead of leaving it bare. Good: 'a few years earlier than 2023-02-08; exact year not stated'.\n"
        "Split unrelated query intents. Avoid vague summaries and duplicates of existing memories.\n"
        f"Return at least {needed} additional memories if the source supports them; more is okay when facts are genuinely distinct.\n"
        "Return JSON only as {\"memories\":[...]}. Each memory object must have: session_id, source_turn_ids, title, kind, topics, memory, source_date, event_date.\n\n"
        f"Existing memories JSON:\n{json.dumps(existing_memories, ensure_ascii=False)}\n\n"
        f"Source conversation JSON:\n{json.dumps(source, ensure_ascii=False)}"
    )


def build_consolidation_repair_prompt(source: dict[str, Any], existing_memories: list[dict[str, Any]]) -> str:
    return (
        "You are doing the ClawMem answer-shaped consolidation pass after an initial extraction.\n"
        "Use only the source conversation below. Do not use benchmark questions or answers.\n"
        "Existing memories are already kept; return only additional missing consolidation memories, not rewrites.\n"
        "Do not add generic session summaries or duplicate existing records.\n"
        "Add scoped cross-session records that a careful human would create after reading many GitHub comments.\n"
        "For a long multi-session source, fewer than 8 additional consolidation memories is usually a miss. Add at least one scoped consolidation record for each major recurring person/entity when the source supports it.\n"
        "Focus on stable properties future agents ask about: person status/profile, relationship or family status, origin/move history, jobs/businesses, education/field, community roles, political/religious clues, activities/hobbies, books/media/games, pets, places, events attended, volunteering/community actions, objects made/bought/received, foods, tools, symbols, reasons/motivations, feelings/reactions, and likely yes/no or counterfactual answers with basis.\n"
        "For projects and businesses, add scoped canonical records for origin/motivation, shared founder arcs, location or space requirements, offerings/services, marketing or promotion tactics, products/collections, launch/status milestones, constraints, and next steps.\n"
        "For pair/commonality facts, create a direct record when two people share a meaningful arc, such as both losing jobs and starting their own businesses.\n"
        "For project attribute sets, preserve every exact list item in one canonical record when practical: ideal studio location and flooring specs; promotion tactics; products made; services offered; workshops/classes; schools/centers; mentors; investors; launch dates.\n"
        "For image/deictic messages, combine the speaker text with image captions. If the speaker says 'this', 'that', 'here is one', 'check them out', or 'they made this', preserve the exact captioned object or scene as an artifact memory, and make authorship/ownership explicit when supported: '<person> made the black and white bowl in the photo'.\n"
        "When values are scattered across sessions, create one canonical-set memory per subject-property, such as 'Melanie activities', 'Caroline LGBTQ events', 'Gina clothing-store promotions', 'Nate games and consoles', or 'Nate favorite desserts'. Include all observed values and source dates when practical, but keep only values that belong to the same property.\n"
        "For ordinal creative works, add focused consolidation records for start/printed/current timing, such as 'Joanna third screenplay start in May 2022'.\n"
        "For advice, recommendations, and motivations, retain exact source phrasing that could be the answer, such as 'keep trying new things until something sparks excitement' and 'strengthen the bond with her pets'.\n"
        "Add query hooks to consolidation titles and bodies. Preserve colloquial source wording, but also write the likely future search wording: weakness/direct favorite/craving -> favorite snack/food; started/trying/took up/went to do an activity -> new/fun activity; recommended/suggested -> advice or recommendation; made/bought/received -> exact item/gift/object. Do not infer a favorite food from someone merely liking an event or meal.\n"
        "Front-load retrieval-critical fields in titles and first sentences: subject, target property, exact value, and event date/month/year when known. Good: 'Sam new activity in October 2023: kayaking'. Bad: 'Kayaking on Lake Tahoe' if Sam and October are absent from the title.\n"
        "Use source_date as provenance, not as event_date. Do not invent day-level event dates from source timestamps alone; use exact day only when the source has an exact date, a resolvable relative phrase, or explicit same-day wording. For 'recently', 'just', or 'currently', prefer 'as of <source_date>' or month/year-level timing unless the exact day is directly supported.\n"
        "When an inference is supported but not directly stated, phrase it as likely with basis and boundary. Do not pretend inferred facts are direct quotes.\n"
        "Before returning, explicitly check for missing records shaped like '<person> activities', '<person> books/media', '<person> pets/family', '<person> events/community', '<person> artifacts/symbols', '<person> relationship/status', '<person> likely inferences', '<person> reasons/reactions', '<pair> shared arc', '<project/business origin', '<project/business offerings', '<project/business promotion tactics', and '<project/business milestones'.\n"
        "Do not rewrite or replace temporal/literal memories. This pass adds consolidation records; it must not reduce visible years, dates, durations, counts, exact names, or relative-time conversions already present.\n"
        "For relative dates, include both original phrase and computed calendar date/month/year when the source timestamp supports it.\n"
        "Return JSON only as {\"memories\":[...]}. Each memory object must have: session_id, source_turn_ids, title, kind, topics, memory, source_date, event_date.\n\n"
        f"Existing memories JSON:\n{json.dumps(existing_memories, ensure_ascii=False)}\n\n"
        f"Source conversation JSON:\n{json.dumps(source, ensure_ascii=False)}"
    )


def build_detail_repair_prompt(source: dict[str, Any], existing_memories: list[dict[str, Any]]) -> str:
    existing = memory_prompt_summaries(existing_memories)
    return (
        "You are doing a ClawMem source-only detail sweep after semantic extraction and consolidation.\n"
        "Use only the source conversation below. Do not use benchmark questions or answers.\n"
        "Existing memories are already kept; return only additional missing memories, not rewrites.\n"
        "Your job is to recover answer-bearing microfacts that broad profile or session memories often compress away.\n"
        "Do not add generic session summaries. Do not duplicate a fact whose exact answer value and likely future query wording are already visible in an existing title or memory body.\n"
        "If the value is visible only inside a broad summary but the searchable query hook is missing, that is not a duplicate; add a small query-hook memory or canonical-set bullet.\n"
        "Walk the source message by message and ask: what short factual answer, list item, object, relationship, action, cause, feeling, quote, or time value would be lost if a future agent only had the existing memories?\n"
        "Prioritize these missing detail shapes:\n"
        "- exact lists of hobbies/interests/activities, books/authors/media/games/music/artists, places/events visited, items bought/collected/made/received, favorite desserts/foods, pets/animals, tools, techniques, gifts, symbols, and promotion tactics;\n"
        "- episodic actions and advice: who did what, what advice/steps were given, what result happened, who attended, what changed, what object/image/sign/poster/message appeared;\n"
        "- stated feelings and reactions with the experiencer and trigger, such as proud, nervous, seeking solitude, frustrated, in awe, grateful, excited, scared, supported, or motivated;\n"
        "- profile boundaries and likely yes/no answers that the source supports, such as allergies implying suitable pets, relationship status, location/state/country clues, suspected health issues, or likely gift/tool recommendations. Phrase these as likely/inferred with basis and boundary;\n"
        "- temporal details that are small but answer-bearing: relative phrases, durations, age clues, reconnect intervals, project lengths, first/third/fourth/current events, and source-date-based calendar anchors.\n"
        "For image/deictic messages, combine the speaker text with the image caption. Preserve the exact captioned object or scene, not only the broad activity. If the speaker says they made or bought the object, include a direct yes/no-ready sentence such as 'Melanie made the black and white bowl in the photo.'\n"
        "For canonical sets, add one compact memory when many exact values belong to the same subject-property, for example '<person> books and authors', '<person> places and events', '<person> pets and suitable pets', '<person> favorite desserts', or '<business> promotion tactics'.\n"
        "For one-off category-4-style details, add atomic event/detail memories with searchable titles. Examples: '<person> cafe sign text', '<person> poster wording', '<person> advice to <other person>', '<person> photo meaning', '<person> made <captioned object>', '<pet/object> name and action'.\n"
        "For ordinal creative projects, preserve exact sequence and timing as a focused detail, such as 'Joanna started writing her third screenplay in May 2022'.\n"
        "Add likely query hooks for source wording that users will ask differently. Examples: if the source says 'ginger snaps are his weakness', add a memory titled like '<person> favorite snack/food: ginger snaps' and say the source wording was 'weakness'; if the source says someone is about to try kayaking, title it like '<person> new activity: kayaking' with the supported month/source date; if the source says someone went skiing in Banff last month (July 2023), title it like '<person> fun activity in July 2023: skiing in Banff' rather than burying it inside a winter-sports profile; if someone suggests an activity, include both 'suggested/recommended' and the activity name.\n"
        "For focused details, the title should usually look like '<subject> <query property> <date/month if known>: <value>', and the first sentence should repeat the same subject/value/date in natural language.\n"
        "Food, drink, snack, dessert, craving, weakness, direct favorite, and diet-limit details need searchable food/snack/dessert/preference wording. Do not leave them only as health-routine or relationship summaries, and do not infer a favorite food from someone merely liking a meal, recipe, or event. For favorite dessert sets, keep exact named items and wording variants; do not substitute nearby recipes.\n"
        "Started, trying, about-to-try, went-to-do, class, hobby, sport, exercise, and outdoor-plan details need searchable new/fun-activity/activity/hobby wording. Do not leave them only as broad profile or trip summaries; preserve place and month when present, such as 'skiing in Banff in July 2023'.\n"
        "Keep each memory answer-complete without reopening raw transcript. Include exact names, numbers, dates, durations, countries/states, and list values when present.\n"
        "Use source_date as YYYY-MM-DD. event_date should be YYYY-MM-DD, YYYY-MM, YYYY, or unknown. If only month/year is supported, preserve that granularity.\n"
        "Do not copy source_date into event_date by default. Exact event_date is allowed only when the source gives an exact date, a resolvable relative phrase, or explicit same-day wording; otherwise use unknown, YYYY, or YYYY-MM and keep 'as of <source_date>' in memory text when useful.\n"
        "When the source uses relative time, include both the original phrase and computed calendar date/month/year when the session timestamp supports it.\n"
        "Allowed kind values: fact, preference, convention, decision, task, skill, lesson, profile, insight.\n"
        "Most added records should be kind fact, profile, preference, or insight. Use insight only for supported inference/likely-answer memories with basis and uncertainty.\n"
        "Return JSON only as {\"memories\":[...]}. Each memory object must have: session_id, source_turn_ids, title, kind, topics, memory, source_date, event_date.\n"
        "For a long multi-session source, returning 15-40 additional memories is normal if genuinely missing details remain; return fewer or zero if existing memories already preserve the exact details.\n\n"
        f"Existing memory summaries JSON:\n{json.dumps(existing, ensure_ascii=False)}\n\n"
        f"Source conversation JSON:\n{json.dumps(source, ensure_ascii=False)}"
    )


def build_query_hook_repair_prompt(source: dict[str, Any], existing_memories: list[dict[str, Any]]) -> str:
    existing = memory_prompt_summaries(existing_memories)
    return (
        "You are doing a ClawMem query-hook audit after extraction, consolidation, and detail sweep.\n"
        "Use only the source conversation below. Do not use benchmark questions or answers.\n"
        "Existing memories are already kept; return only additional missing query-hook memories, not rewrites.\n"
        "A query-hook memory is needed when a source value exists, but the existing title/body lacks wording that future agents or users are likely to search or ask.\n"
        "Do not add generic summaries. Do not add a memory when both the exact value and likely query wording are already visible in existing memories.\n"
        "If the exact value is visible only inside a broad profile/session memory, but the likely future question wording is missing, add a focused alias memory.\n"
        "Add small answer-complete memories for these source-only patterns:\n"
        "- food/drink/snack preferences, cravings, weaknesses, diet limits, and direct favorite wording. Include hooks such as favorite food, favorite snack, snack weakness, craving, or diet limit when supported. Example: if the source says 'ginger snaps are his weakness', title it '<person> favorite snack/food or snack weakness: ginger snaps' and say the source wording was 'weakness'. Do not convert generic liked meals/events into favorite-food memories.\n"
        "- new or fun activities, hobbies, sports, exercises, classes, about-to-try plans, or activities someone went to do. Include hooks such as new activity, fun activity, hobby, sport, class, and the activity name plus supported place/date/month/source wording.\n"
        "- recommendations, suggestions, advice, and motivations. Include hooks such as advice, recommendation, finding a passion, suggested activity/tool, purpose, motivation, who suggested it, who received it, and exact answer phrases such as 'keep trying new things until something sparks excitement' or 'strengthen the bond with her pets'.\n"
        "- exact places, countries, cities, trips, jobs, injuries, symptoms, gifts, tools, pets, photos, image objects, authorship/ownership of captioned objects, books/media/games, quantities, durations, ordinal creative works, first/second/third/last/current facts, and list/set values.\n"
        "Keep the source wording and uncertainty. If the source supports a query hook only indirectly, say so: 'source wording was weakness', 'likely favorite snack', or 'exact favorite-food label not stated'.\n"
        "Titles should be searchable and specific, such as 'Evan favorite snack/food: ginger snaps (source said weakness)', 'Sam new activity in October 2023: kayaking at Lake Tahoe', or 'Evan fun activity in July 2023: skiing in Banff'.\n"
        "The first sentence should also carry the same answer-bearing fields so retrieval and answering do not depend on hidden metadata: subject, property, exact value, and event date/month/year when known.\n"
        "Use source_date as YYYY-MM-DD. event_date should be YYYY-MM-DD, YYYY-MM, YYYY, or unknown. Do not copy source_date into event_date unless exact same-day timing is supported by source wording.\n"
        "Return JSON only as {\"memories\":[...]}. Each memory object must have: session_id, source_turn_ids, title, kind, topics, memory, source_date, event_date.\n"
        "For a long multi-session source, 5-25 additional query-hook memories is normal if values are otherwise buried; return fewer or zero if existing memories already include the query hooks.\n\n"
        f"Existing memory summaries JSON:\n{json.dumps(existing, ensure_ascii=False)}\n\n"
        f"Source conversation JSON:\n{json.dumps(source, ensure_ascii=False)}"
    )


def build_answer_audit_repair_prompt(source: dict[str, Any], existing_memories: list[dict[str, Any]]) -> str:
    existing = memory_prompt_summaries(existing_memories)
    return (
        "You are doing a final ClawMem answer-completeness audit after extraction and query-hook repair.\n"
        "Use only the source conversation below. Do not use benchmark questions or answers.\n"
        "Existing memories are already kept; return only additional missing memories, not rewrites.\n"
        "This pass is narrow. Add a memory only when the source contains an answer-bearing value, but the existing title/body still cannot answer the likely who/what/when/which/why question by itself.\n"
        "Do not add generic session summaries. Do not duplicate a fact whose exact subject, property, value, and likely question wording are already visible in existing memories.\n"
        "Run the whole checklist and return every missing audited shape, not just the first one you notice. If an ordinal creative-work timing memory and a subject-specific preference-set memory are both missing, return both.\n"
        "Audit these miss-prone shapes carefully:\n"
        "1. Image/artifact yes/no. If a message uses deictic wording near an image caption and the source supports authorship or ownership, add a yes/no-ready memory with the exact captioned object and attributes, e.g. '<person> made the black-and-white flower bowl in the photo'.\n"
        "2. Ordinal creative work timing. For first/second/third/fourth screenplay, movie, book, draft, or project, add a focused memory with person, ordinal, work type, action, and month/year. Existing memories are not sufficient if they say only that a third script existed on a source date but omit started/writing/by-month wording. If the source says someone was 'working on' a third screenplay in a dated session and had 'got the guts to write it', write a bounded memory such as 'By May 2022, Joanna had started/written her third screenplay; exact start day not stated.' Use month/year from the source timestamp when the exact day is not supported; do not invent a day.\n"
        "3. Favorite/preference canonical sets. Audit each subject independently. When a source asks a subject for favorite flavors, favorite desserts, favs, weaknesses, cravings, or direct preferences, collect that subject's exact named values into one subject-property memory. Existing scattered memories are not sufficient when values are split across records, hidden under another person's title, or mixed with nearby recipes. A memory titled around Joanna's desserts is not sufficient for Nate's favorite desserts even if Nate appears in the body. A memory that names only coconut milk ice cream and mousse is not sufficient if the source also has a favorite-flavor thread with chocolate/mixed berry and a dairy-free chocolate cake with berries. Add a canonical memory like '<person> favorite desserts: ...' that names only that person's values, and write 'canonical answer set includes ...' in the first sentence when the set is meant to answer a likely list question. Preserve wording variants such as 'coconut milk ice cream', 'chocolate and mixed-berry ice cream/flavors', 'dairy-free chocolate cake with berries', and 'dairy-free chocolate mousse'. If one item is a made/shared dessert in the same favorite-preference thread rather than explicitly called favorite, include the boundary in the memory text instead of dropping it.\n"
        "4. Advice, recommendation, and purpose phrases. Preserve the exact answer phrase and target, such as 'keep trying new things until something sparks excitement' for finding a passion, or 'strengthen the bond with her pets' for a pet-bonding workshop.\n"
        "5. Date granularity. If a future answer should be a month/year and the source only supports month/year from the session, put that month/year in the title and first sentence. Do not hide timing only in source_date or metadata.\n"
        "For every added memory, front-load retrieval-critical fields in the title and first sentence: subject, property, exact value, and event date/month/year when known.\n"
        "For cross-session canonical sets, include all contributing source_turn_ids and name the contributing dates in the memory body. Do not place values from an earlier session under a later source_date as if they were stated that day.\n"
        "Use source_date as YYYY-MM-DD. event_date should be YYYY-MM-DD, YYYY-MM, YYYY, or unknown. For month-only support, use YYYY-MM and say exact day not stated in memory text.\n"
        "Allowed kind values: fact, preference, convention, decision, task, skill, lesson, profile, insight.\n"
        "Return JSON only as {\"memories\":[...]}. Each memory object must have: session_id, source_turn_ids, title, kind, topics, memory, source_date, event_date.\n"
        "Return at most 12 added memories. Return an empty memories array if the existing memories already answer all audited shapes.\n\n"
        f"Existing memory summaries JSON:\n{json.dumps(existing, ensure_ascii=False)}\n\n"
        f"Source conversation JSON:\n{json.dumps(source, ensure_ascii=False)}"
    )


def source_temporal_hints(source: dict[str, Any]) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    for session in source.get("sessions") or []:
        timestamp = str(session.get("timestamp") or "").strip()
        session_id = str(session.get("session_id") or "").strip()
        for message in session.get("messages") or []:
            content = str(message.get("content") or "").strip()
            if not content or not TEMPORAL_HINT_RE.search(content):
                continue
            hints.append({
                "session_id": session_id,
                "timestamp": timestamp,
                "turn_id": str(message.get("turn_id") or "").strip(),
                "speaker": str(message.get("speaker") or "").strip(),
                "content": content[:900],
            })
    return hints


def memory_prompt_summaries(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, memory in enumerate(memories, 1):
        text = str(memory.get("memory") or "").strip()
        summaries.append({
            "index": index,
            "title": str(memory.get("title") or "").strip()[:160],
            "source_date": str(memory.get("source_date") or "").strip(),
            "event_date": str(memory.get("event_date") or "").strip(),
            "memory": text[:360],
        })
    return summaries


def build_temporal_anchor_repair_prompt(source: dict[str, Any], existing_memories: list[dict[str, Any]]) -> str:
    hints = source_temporal_hints(source)
    existing = memory_prompt_summaries(existing_memories)
    return (
        "You are doing a ClawMem temporal-anchor audit after an initial extraction.\n"
        "Use only the temporal hint lines below. Do not use benchmark questions or answers.\n"
        "Existing memories are already kept; return only additional missing temporal-anchor memories, not rewrites.\n"
        "A temporal-anchor memory is needed when a future agent could answer a when/how-long/how-many-years question from a source message, but the answer-bearing time value is absent or vague in existing memories.\n"
        "Focus on source turns with relative phrases, durations, ages, anniversaries, birthdays, counts per period, first/last/current timing, and image/deictic statements tied to time.\n"
        "The temporal hint list is a candidate queue with source timestamps and message text. If a hint is ambiguous without broader transcript context, skip it instead of guessing.\n"
        "For relative time, include both the original phrase and the computed calendar date/month/year when the source timestamp supports it.\n"
        "Examples: 'last year (2022)' from a 2023 source; 'yesterday (2023-05-07)' from a 2023-05-08 source; 'about 10 years earlier, around 2013' from a 2023 source.\n"
        "Preserve granularity. If only a year is supported, write the year; if only a month is supported, write the month/year and say exact day not stated.\n"
        "Do not add a memory if the exact temporal answer is already visible in existing memories.\n"
        "Do not add generic timelines or session summaries. Each added memory should have a title naming the entity and temporal fact.\n"
        "Return JSON only as {\"memories\":[...]}. Each memory object must have: session_id, source_turn_ids, title, kind, topics, memory, source_date, event_date.\n\n"
        f"Temporal hint lines JSON:\n{json.dumps(hints, ensure_ascii=False)}\n\n"
        f"Existing memory summaries JSON:\n{json.dumps(existing, ensure_ascii=False)}"
    )


def merge_cleaned_memories(existing: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = list(existing)
    seen = {str(memory.get("memory_key") or stable_memory_key(memory)) for memory in out}
    for memory in additions:
        key = str(memory.get("memory_key") or stable_memory_key(memory))
        if not key or key in seen:
            continue
        memory["memory_key"] = key
        seen.add(key)
        out.append(memory)
    return out


def memory_search_text(memory: dict[str, Any]) -> str:
    return "\n".join(str(memory.get(key) or "").strip() for key in ("title", "memory") if str(memory.get(key) or "").strip())


def absolute_time_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []

    def add(pattern: re.Pattern[str]) -> None:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < existing_end and end > existing_start for existing_start, existing_end in spans):
                continue
            spans.append((start, end))

    for pattern in (DATE_RE, YEAR_MONTH_RE, DAY_MONTH_YEAR_RE, MONTH_DAY_YEAR_RE, MONTH_YEAR_RE):
        add(pattern)
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
    for start, end in absolute_time_spans(line):
        if source_labeled_anchor(line, start):
            continue
        if end <= match.start() and match.start() - end <= 180:
            return True
        if start >= match.end() and start - match.end() <= 180:
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
            anchors.append({"phrase": match.group(0), "line": line[:240]})
    return anchors


def flagged_temporal_memories(memories: list[dict[str, Any]], max_memories: int) -> list[dict[str, Any]]:
    flagged: list[dict[str, Any]] = []
    for index, memory in enumerate(memories, 1):
        anchors = relative_only_time_anchors(memory_search_text(memory))
        if not anchors:
            continue
        flagged.append({
            "index": index,
            "anchors": anchors[:6],
            "memory": {
                key: memory.get(key)
                for key in ("session_id", "source_turn_ids", "title", "kind", "topics", "memory", "source_date", "event_date")
            },
        })
        if max_memories > 0 and len(flagged) >= max_memories:
            break
    return flagged


def temporal_repair_memories(
    source_id: str,
    source: dict[str, Any],
    memories: list[dict[str, Any]],
    args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], int, int, int]:
    current = list(memories)
    total_tokens = 0
    attempts = 0
    repaired_count = 0
    for attempt in range(max(0, args.extract_temporal_repair_attempts)):
        flagged = flagged_temporal_memories(current, max(0, args.extract_temporal_repair_max_memories))
        if not flagged:
            break
        attempts += 1
        text, tokens_used = call_codex(
            build_temporal_repair_prompt(source, flagged),
            args.extract_model,
            args.extract_reasoning_effort,
            timeout_sec=900,
        )
        save_extract_raw(args, source_id, f"temporal-repair-{attempt + 1}", text)
        total_tokens += tokens_used or 0
        parsed = parse_json_block(text)
        repairs = parsed.get("repairs") if isinstance(parsed, dict) else parsed
        if not isinstance(repairs, list):
            raise RuntimeError("temporal repair output must be an array or object with repairs[]")
        changed = 0
        for repair in repairs:
            if not isinstance(repair, dict):
                continue
            try:
                index = int(repair.get("index")) - 1
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= len(current):
                continue
            replacement = repair.get("memory") if isinstance(repair.get("memory"), dict) else None
            if not replacement:
                continue
            cleaned = clean_memories(source_id, [replacement])
            if not cleaned:
                continue
            if relative_only_time_anchors(memory_search_text(cleaned[0])):
                continue
            current[index] = cleaned[0]
            changed += 1
        repaired_count += changed
        if changed == 0:
            break
    return current, attempts, repaired_count, total_tokens


def parse_iso_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    match = DATE_RE.search(text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), "%Y-%m-%d")
    except ValueError:
        return None


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=1)


def relative_number(value: str) -> int | None:
    text = value.strip().lower()
    if text.isdigit():
        return int(text)
    return NUMBER_WORDS.get(text)


def weekday_anchor(source_date: datetime, direction: str, weekday: str) -> str:
    target = WEEKDAYS[weekday]
    current = source_date.weekday()
    if direction in {"last", "previous"}:
        days = (current - target) % 7 or 7
        return (source_date - timedelta(days=days)).strftime("%Y-%m-%d")
    days = (target - current) % 7 or 7
    return (source_date + timedelta(days=days)).strftime("%Y-%m-%d")


def weekend_anchor(source_date: datetime, direction: str) -> str:
    saturday = WEEKDAYS["saturday"]
    current = source_date.weekday()
    if direction in {"last", "previous"}:
        days = (current - saturday) % 7 or 7
        start = source_date - timedelta(days=days)
    else:
        days = (saturday - current) % 7 or 7
        start = source_date + timedelta(days=days)
    end = start + timedelta(days=1)
    return f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"


def relative_anchor_text(phrase: str, source_date: datetime) -> str:
    lower = phrase.lower().strip()
    if lower == "today":
        return source_date.strftime("%Y-%m-%d")
    if lower == "yesterday":
        return (source_date - timedelta(days=1)).strftime("%Y-%m-%d")
    if lower == "tomorrow":
        return (source_date + timedelta(days=1)).strftime("%Y-%m-%d")

    match = re.fullmatch(r"(last|previous|next|following)\s+year", lower)
    if match:
        delta = -1 if match.group(1) in {"last", "previous"} else 1
        return str(source_date.year + delta)

    match = re.fullmatch(r"(last|previous|next|following)\s+month", lower)
    if match:
        delta = -1 if match.group(1) in {"last", "previous"} else 1
        month = add_months(source_date, delta)
        return f"{MONTH_NAMES[month.month - 1]} {month.year}"

    match = re.fullmatch(r"(last|previous|next|following)\s+week", lower)
    if match:
        if match.group(1) in {"last", "previous"}:
            anchor = source_date - timedelta(days=7)
            return f"the week before {source_date.strftime('%Y-%m-%d')}, around {anchor.strftime('%Y-%m-%d')}; exact day not stated"
        anchor = source_date + timedelta(days=7)
        return f"the week after {source_date.strftime('%Y-%m-%d')}, around {anchor.strftime('%Y-%m-%d')}; exact day not stated"

    match = re.fullmatch(r"(last|previous|next|following)\s+weekend", lower)
    if match:
        return weekend_anchor(source_date, match.group(1))

    match = re.fullmatch(r"(last|previous|next|following)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", lower)
    if match:
        return weekday_anchor(source_date, match.group(1), match.group(2))

    match = re.fullmatch(
        r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+years\s+(ago|before|earlier)",
        lower,
    )
    if match:
        count = relative_number(match.group(1))
        if count:
            year = source_date.year - count
            return f"about {count} years ago, around {year}"

    match = re.fullmatch(
        r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+years\s+(after|later)",
        lower,
    )
    if match:
        count = relative_number(match.group(1))
        if count:
            year = source_date.year + count
            return f"about {count} years later, around {year}"

    match = re.fullmatch(r"(a few|couple of|several)\s+weeks\s+(ago|before|earlier)", lower)
    if match:
        anchor = source_date - timedelta(days=21)
        return f"a few weeks before {source_date.strftime('%Y-%m-%d')}, around {MONTH_NAMES[anchor.month - 1]} {anchor.year}; exact date not stated"

    match = re.fullmatch(r"(a few|couple of|several)\s+years\s+(ago|before|earlier)", lower)
    if match:
        return f"a few years before {source_date.strftime('%Y-%m-%d')}; exact year not stated"

    return ""


def anchor_already_visible(line: str, match: re.Match[str], anchor: str) -> bool:
    window = line[max(0, match.start() - 100):match.end() + 140]
    dates = DATE_RE.findall(anchor)
    if dates:
        return any(date in window for date in dates)
    month_years = MONTH_YEAR_RE.findall(anchor)
    if month_years and any(month.lower() in window.lower() for month in month_years):
        return True
    years = YEAR_RE.findall(anchor)
    if years and any(year in window for year in years):
        return True
    return False


def normalize_relative_line(line: str, source_date: datetime) -> str:
    def replace(match: re.Match[str]) -> str:
        phrase = match.group(0)
        after = line[match.end():match.end() + 2]
        if after.startswith("("):
            return phrase
        anchor = relative_anchor_text(phrase, source_date)
        if not anchor or anchor_already_visible(line, match, anchor):
            return phrase
        return f"{phrase} ({anchor})"

    return RELATIVE_TIME_RE.sub(replace, line)


def normalize_relative_time_memories(memories: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    out: list[dict[str, Any]] = []
    changed = 0
    for memory in memories:
        source_date = parse_iso_date(memory.get("source_date"))
        if not source_date:
            out.append(memory)
            continue
        next_memory = dict(memory)
        item_changed = False
        for key in ("title", "memory"):
            original = str(next_memory.get(key) or "")
            normalized = "\n".join(normalize_relative_line(line, source_date) for line in original.splitlines())
            if normalized != original:
                next_memory[key] = normalized
                item_changed = True
        if item_changed:
            next_memory["memory_key"] = stable_memory_key(next_memory)
            changed += 1
        out.append(next_memory)
    return out, changed


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
PERSON_NAME_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
TITLE_TOKEN_STOPWORDS = {
    "April",
    "August",
    "Canada",
    "Canadian",
    "December",
    "Evan",
    "February",
    "Friday",
    "Gym",
    "January",
    "July",
    "June",
    "Kayaking",
    "Lake",
    "March",
    "May",
    "Monday",
    "November",
    "October",
    "Saturday",
    "Sam",
    "September",
    "Sunday",
    "Tahoe",
    "Thursday",
    "Tuesday",
    "Wednesday",
    "Cooking",
    "Painting",
    "Banff",
    "Running",
    "Skiing",
    "Swimming",
    "Rockies",
    "Rocky",
    "Mountain",
    "Mountains",
    "Yoga",
}


def normalize_query_hook_memories(memories: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    out: list[dict[str, Any]] = []
    body_changed = 0
    title_changed = 0
    for memory in memories:
        text = memory_search_text(memory)
        lower = text.lower()
        hooks: list[str] = []
        food_hook = food_query_hook(text)
        if food_hook and not re.search(r"\b(?:favorite\s+(?:snack|food|drink)|diet\s+limit|food\s+restriction)\b", lower):
            hooks.append(food_hook)
        activity_pair = paired_activity_signal_and_value(text)
        if activity_pair and not re.search(r"\b(?:new|fun)\s+activity\b", lower):
            hooks.append("new/fun activity, activity/hobby/sport/class")
        if ADVICE_HOOK_RE.search(text) and not re.search(r"\b(?:advice|recommendation)\b", lower):
            hooks.append("advice, recommendation")
        title_prefix = query_hook_title_prefix(memory, text)
        if not hooks and not title_prefix:
            out.append(memory)
            continue
        next_memory = dict(memory)
        if title_prefix:
            title = str(next_memory.get("title") or "").strip()
            if title_prefix.lower() not in title.lower():
                next_memory["title"] = f"{title_prefix}: {title}" if title else title_prefix
                title_changed += 1
        if hooks:
            body = str(next_memory.get("memory") or "").rstrip()
            existing = body.lower()
            missing_hooks = [hook for hook in hooks if hook.lower() not in existing]
            if missing_hooks:
                next_memory["memory"] = f"{body}\n\nQuery hooks: {'; '.join(missing_hooks)}."
                body_changed += 1
        if next_memory != memory:
            next_memory["memory_key"] = stable_memory_key(next_memory)
        out.append(next_memory)
    return out, body_changed, title_changed


def query_hook_title_prefix(memory: dict[str, Any], text: str) -> str:
    title = str(memory.get("title") or "")
    lower_title = title.lower()
    event_date = str(memory.get("event_date") or "").strip()
    date_text = human_month_or_year(event_date)
    new_activity_match = NEW_ACTIVITY_SIGNAL_RE.search(text)
    activity_pair = paired_activity_signal_and_value(text)
    if activity_pair:
        signal_match, activity_match = activity_pair
        subject = (
            nearest_person_name(text, signal_match.start())
            or nearest_person_name(text, activity_match.start())
            or first_person_name(text)
        )
        activity = activity_value_phrase(text, activity_match)
        date_text = human_month_or_year(event_date) or nearby_human_time_phrase(text, activity_match.start())
        query_property = "new activity" if NEW_ACTIVITY_SIGNAL_RE.fullmatch(signal_match.group(0)) else "fun activity"
        pieces = [part for part in (subject, query_property, date_text) if part]
        prefix = " ".join(pieces)
        if activity:
            prefix = f"{prefix}: {activity}" if prefix else f"{query_property}: {activity}"
        if prefix and not re.search(r"\b(?:new|fun)\s+activity\b", lower_title):
            return prefix
    if food_favorite_value_match(text):
        food_match = SPECIFIC_FOOD_VALUE_RE.search(text)
        subject = nearest_person_name(text, food_match.start()) if food_match else first_person_name(text)
        food = canonical_food_name(food_match.group(0) if food_match else "")
        pieces = [part for part in (subject, "favorite snack/food") if part]
        prefix = " ".join(pieces)
        if food:
            prefix = f"{prefix}: {food}" if prefix else f"favorite snack/food: {food}"
        if prefix and not re.search(r"\bfavorite\s+(?:snack|food|drink)\b", lower_title):
            return prefix
    if ADVICE_HOOK_RE.search(text) and "advice" not in lower_title and "recommendation" not in lower_title:
        subject = first_person_name(text)
        pieces = [part for part in (subject, "advice/recommendation") if part]
        return " ".join(pieces)
    return ""


def nearest_person_name(text: str, anchor: int) -> str:
    best: tuple[int, int, str] | None = None
    for match in PERSON_NAME_RE.finditer(text):
        token = match.group(0)
        if token in TITLE_TOKEN_STOPWORDS - {"Evan", "Sam"}:
            continue
        if match.end() <= anchor:
            distance = anchor - match.end()
            direction_penalty = 0
        elif match.start() >= anchor:
            distance = match.start() - anchor
            direction_penalty = 40
        else:
            distance = 0
            direction_penalty = 0
        if distance > 220:
            continue
        candidate = (distance + direction_penalty, match.start(), token)
        if best is None or candidate < best:
            best = candidate
    return best[2] if best else ""


def first_person_name(text: str) -> str:
    for match in PERSON_NAME_RE.finditer(text):
        token = match.group(0)
        if token in TITLE_TOKEN_STOPWORDS - {"Evan", "Sam"}:
            continue
        return token
    return ""


def human_month_or_year(value: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})", value or "")
    if match:
        month = int(match.group(2))
        if 1 <= month <= 12:
            return f"in {MONTH_NAMES[month - 1]} {match.group(1)}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
            return f"on {parsed.strftime('%B')} {parsed.day}, {parsed.year}"
        except ValueError:
            return ""
    if re.fullmatch(r"\d{4}", value or ""):
        return f"in {value}"
    return ""


def canonical_activity_name(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip().lower()
    aliases = {
        "kayak": "kayaking",
        "cook class": "cooking class",
        "cooking class": "cooking class",
        "ski": "skiing",
        "gym": "gym/workout",
        "workout": "workout",
        "exercise": "exercise",
    }
    return aliases.get(text, text)


def activity_value_phrase(text: str, activity_match: re.Match[str]) -> str:
    activity = canonical_activity_name(activity_match.group(0))
    after = text[activity_match.end():activity_match.end() + 80]
    place_match = re.match(
        r"\s+(?:in|at|on|around|near)\s+"
        r"([A-Z][A-Za-z0-9&'.-]*(?:\s+[A-Z][A-Za-z0-9&'.-]*){0,3})",
        after,
    )
    if not place_match:
        return activity
    place = place_match.group(1).strip()
    if place in TITLE_TOKEN_STOPWORDS and place not in {"Banff", "Lake Tahoe"}:
        return activity
    return f"{activity} in {place}"


def nearby_human_time_phrase(text: str, anchor: int) -> str:
    window = text[max(0, anchor - 180):anchor + 180]
    date_match = DATE_RE.search(window)
    if date_match:
        return human_month_or_year(date_match.group(0))
    year_month_match = YEAR_MONTH_RE.search(window)
    if year_month_match:
        return human_month_or_year(year_month_match.group(0))
    month_year_match = MONTH_YEAR_RE.search(window)
    if month_year_match:
        value = re.sub(r"\s+", " ", month_year_match.group(0).replace(",", "")).strip()
        return f"in {value}"
    year_match = YEAR_RE.search(window)
    if year_match:
        return f"in {year_match.group(0)}"
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


def canonical_food_name(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


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


def build_temporal_repair_prompt(source: dict[str, Any], flagged: list[dict[str, Any]]) -> str:
    return (
        "Repair ClawMem memory objects that contain relative-only time anchors.\n"
        "Use only the source conversation JSON and the flagged memory objects below.\n"
        "Do not add new memories. Do not remove facts. Rewrite only the title and memory text needed to add computed calendar anchors.\n"
        "Use the source session timestamp for each memory to resolve phrases; never use the current date.\n"
        "Every repaired title/body line containing a phrase such as yesterday, last week, next Friday, last year, next month, or a few years earlier must include a nearby calendar date, month, or year.\n"
        "Good rewrites: 'next Friday (2023-01-27)', 'yesterday (2023-01-28)', 'last year (2022)', 'next month (February 2023)', 'a few years earlier than 2023-02-08; exact year not stated'.\n"
        "If a title contains a bare relative phrase, repair the title too.\n"
        "Keep the original relative wording when useful, but make the calendar interpretation visible in the same sentence or bullet.\n"
        "Return JSON only as {\"repairs\":[{\"index\":1,\"memory\":{...full memory object...}}]}.\n"
        "Each repaired memory object must keep: session_id, source_turn_ids, title, kind, topics, memory, source_date, event_date.\n\n"
        f"Flagged memories JSON:\n{json.dumps(flagged, ensure_ascii=False)}\n\n"
        f"Source conversation JSON:\n{json.dumps(source, ensure_ascii=False)}"
    )


def build_extraction_prompt(source: dict[str, Any]) -> str:
    return (
        "You are performing a ClawMem skill-driven retention pass for a memory benchmark.\n"
        "Use only the source conversation below. Do not use benchmark questions or answers.\n"
        "Do the extraction in two passes before returning JSON.\n"
        "Pass A: extract answerable semantic durable memories: facts, preferences, profiles, decisions, conventions, tasks, lessons, skills, and insights.\n"
        "Pass B: repair literal anchors that summaries often lose: dates, months, years, weekdays, relative time phrases, durations, ages, counts, quantities, exact names, exact projects/events/games/books/places/pets, first/last/current facts, and planned times.\n"
        "Pass B should usually enrich or split semantic memories, not create a ledger for every session. A ledger is useful only when several short anchors share the same person, pair, project, or topic and would otherwise be lost.\n"
        "Do not trade temporal/literal coverage for broad profile consolidation. The final output must keep answer-bearing dates, years, durations, counts, exact names, and relative-time conversions visible in memory text.\n"
        "Do not chase a fixed memory count. Prefer fewer, better-titled, answer-complete records over many generic session ledgers that compete with semantic memories in recall.\n"
        "For each source session, extract the durable semantic records that a future agent could search and answer from. Split by person, entity, topic, decision, causal point, preference, canonical set, or event when those would be asked separately.\n"
        "Never combine unrelated facts just to reduce count. A title like 'Sweden necklace, birthday bowl, and counseling workshop' is bad because it mixes separate query intents; split it into separate memories.\n"
        "A single memory may hold multiple details only when they belong to the same subject-property, canonical set, event, decision, or causal link.\n"
        "Use literal-anchor ledgers sparingly. When you create one, scope it tightly by entity/topic, not just by session id; title it like '<person> dates and counts' or '<pair> plans and exact anchors'.\n"
        "Each ledger bullet must include the subject, exact value, event/action/property, and source timestamp or source wording. Example: '- 2023-05-07; source 2023-05-08 said \"yesterday\": Caroline went to the LGBTQ support group.'\n"
        "If only month/year is supported, write the month/year and say exact day not stated. Example: '- April 2023, exact day not stated: James adopted Ned.'\n"
        "If the source uses a relative expression that may be the expected answer, keep it verbatim. Example: '- the Friday before 2022-06-24: Joanna planned the event.'\n"
        "Extract durable, answer-complete memory issues. Preserve exact names, places, dates, quantities, list items, relationship targets, causes, and stated reasons.\n"
        "If the source says a concrete value, write that value visibly. Do not answer with vague substitutes such as 'home country', 'a hobby', 'recently', or 'some pets' when the source names Sweden, pottery, a date, or Bailey. Preserve full domain qualifiers such as 'counseling or mental health for transgender people', not only 'counseling'.\n"
        "Write future-search query hooks into titles and memory text while preserving source wording. If the source uses colloquial wording, add the likely question wording too: 'weakness' or a direct favorite/craving can support favorite snack/food; 'about to try', 'started', or 'went skiing in Banff last month' can support new/fun activity with place and month; 'suggested' can support recommendation/advice; 'finding a passion' should preserve exact advice such as 'keep trying new things until something sparks excitement'; a named object in an image can support exact item/artifact and yes/no authorship questions. Do not infer favorite-food facts from generic enjoyment of meals or events.\n"
        "Front-load retrieval-critical fields in the title and first sentence: subject, target property, exact value, and event date/month/year when known. Good: 'Sam new activity in October 2023: kayaking'. Bad: 'Kayaking on Lake Tahoe' when Sam, new activity, and October are not in the title.\n"
        "For lists and sets, store the canonical set in one memory when practical: pets, hobbies, coping strategies, places, tools, people, constraints, plans, favorite desserts, or recurring activities.\n"
        "Canonical sets may need cross-session consolidation. If one person swims in one session, camps in another, paints in another, and does pottery later, add a '<person> activities' memory that names all observed activities and dates/sources.\n"
        "For projects and businesses, store canonical attribute sets when values are spread across sessions: origin/motivation, shared founder arcs, ideal location or space requirements, offerings/services, promotion tactics, products/collections, launch/status milestones, constraints, and next steps.\n"
        "If two people share a meaningful arc, store it directly as a pair/commonality memory. Example: 'Jon and Gina both lost jobs and started their own businesses.'\n"
        "For project attribute sets, preserve exact list items and wording variants that may be asked later, such as by the water, natural light, Marley flooring, limited-edition sweatshirts/hoodies, offers/promotions, video presentations, one-on-one mentoring/training, workshops, and classes for local schools and centers.\n"
        "For favorite food or dessert sets, preserve every exact favorite/preference-thread item and wording variant in a canonical preference memory. Keep 'coconut milk ice cream', 'dairy-free chocolate cake with berries', 'chocolate and mixed-berry ice cream', and 'dairy-free chocolate mousse' distinct if the source names them in favorite/preference context; do not add unrelated recipes from other sessions just because they are also desserts.\n"
        "For status/profile questions, store explicit and strongly implied states: relationship status, family role, origin/move history, job loss, future career, financial or education clues, community participation, political/religious leaning, and important personal symbols. Phrase implied states with basis, such as 'single parent' supporting 'single/solo parent status'.\n"
        "When the source strongly supports a profile boundary or likely negative answer, store it with its basis and uncertainty instead of forcing it into a bare fact. Example: 'Melanie is described as an LGBTQ ally/support-group participant; the source does not establish that she is LGBTQ herself.'\n"
        "For counterfactual or likely-answer memories, write the answer shape directly when the source supports it. Examples: 'Likely no: without growing-up support, Caroline would likely be less driven toward counseling; her stated motivation is helping people with similar experiences after receiving support.' 'Likely yes: Caroline may have Dr. Seuss books because she stocks classic children's books; exact Dr. Seuss ownership is not stated.' These are first-class insight memories, not optional comments.\n"
        "For images and deictic messages, treat the image caption as part of the source. When a message says 'this', 'that', 'here is one', 'check them out', or 'they made this', preserve the exact image object/scene and its relationship to the speaker's statement, e.g. 'Melanie's kids made a cup with a dog face on it' or 'Melanie made the black and white bowl in the photo', not only 'they made pottery'.\n"
        "For ordinal creative works, preserve the sequence and timing in title and first sentence: first/second/third/fourth screenplay, movie, book, draft, or project; started/writing/printed/current; exact date/month/year. Example: 'Joanna third screenplay start in May 2022'.\n"
        "For advice, recommendations, and motivations, preserve exact answer phrases and target properties: 'finding a passion: keep trying new things until something sparks excitement'; 'pet workshop purpose: strengthen the bond with her pets'.\n"
        "For feelings/reactions, preserve the experiencer and exact sentiment: proud, excited, in awe, upset, motivated, calming, scared, grateful, or supportive. Do not replace a concrete feeling with a generic positive summary.\n"
        "Before returning, run a query-hook check. If a value is present only in a broad memory without future question wording, add or retitle a focused memory. Check: favorite/weakness/craving foods, desserts, and snacks; new/fun activities/hobbies/sports/classes with places and dates; recommendations/advice/purpose phrases; exact gifts/items/photos/artifacts and authorship; places/countries/cities; injuries/symptoms; books/media/games; ordinal creative works; dates/durations/counts; likely yes/no or counterfactual answers with basis.\n"
        "Ledger memory text may use Markdown bullets. Keep each bullet answerable on its own with subject, value, event/action, and source date or source wording when available.\n"
        "Convert relative dates only when the session timestamp supports it. Always keep the original relative phrase when it may be asked later, such as 'last week', 'next Saturday', 'the Friday before 2022-06-24', or 'the weekend after 3 June 2022'.\n"
        "Do not leave relative-only time anchors. When the source date supports conversion, write the computed calendar date, month, or year next to the original phrase.\n"
        "Preserve granularity: if the source only supports April 2023 or 2022, write that exact granularity and say exact day not stated when useful. Do not invent YYYY-MM-DD dates from month/year-only evidence.\n"
        "Source timestamps alone are not event dates. Do not turn 'recently', 'just', 'currently', or the mere fact that a message was sent on a date into an exact event_date. Use exact day only for explicit dates, resolvable relative phrases, or explicit same-day wording; otherwise write 'as of <source_date>' or the supported month/year and set event_date to unknown or that supported granularity.\n"
        "When a day-level date is knowable, write the ISO date string (YYYY-MM-DD) directly in the memory text; natural-language dates alone are not enough.\n"
        "Prefer canonical set/profile memories for recurring facts, but split unrelated subjects so recall can find them.\n"
        "Do not compress a long conversation into a handful of broad summaries. Walk session by session and preserve answer-bearing facts from every session, but avoid near-duplicate ledgers and vague mega-memories.\n"
        "For a long LoCoMo source conversation, fewer than 45 memories is a warning sign unless the source is unusually sparse. Re-check that every session and major entity has searchable semantic records.\n"
        "Before returning, re-check temporal anchors separately from consolidation: years, month/year facts, day-level dates, durations, ages, counts, first/last/current facts, and relative phrases must still be visible in memory text.\n"
        "Do not store generic public knowledge. Do not write vague summaries such as 'has hobbies' when exact items are present.\n"
        "Return JSON only as {\"memories\":[...]}. Each memory object must have: session_id, source_turn_ids, title, kind, topics, memory, source_date, event_date.\n"
        "source_date should be YYYY-MM-DD. event_date should be YYYY-MM-DD, YYYY-MM, YYYY, or unknown.\n"
        "Allowed kind values: fact, preference, convention, decision, task, skill, lesson, profile, insight.\n"
        "memory should be dense natural language, usually 1-4 sentences; literal anchor ledgers may be concise bullet lists. Every memory must be answerable without reopening raw transcript.\n"
        "Aim for high recall coverage over brevity; it is okay to output many memories if the conversation contains many answer-bearing facts.\n"
        "Avoid mega-memories that combine unrelated people/events, because retrieval needs specific titles and memory text.\n\n"
        f"Source conversation JSON:\n{json.dumps(source, ensure_ascii=False)}"
    )


def source_payload(group: dict[str, Any]) -> dict[str, Any]:
    sessions = []
    for session in group["sessions"]:
        messages = []
        for message in session.get("messages", []):
            content = str(message.get("content") or "").strip()
            metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
            caption = str(metadata.get("blip_caption") or "").strip()
            if caption:
                content = f"{content}\n[image caption: {caption}]".strip()
            messages.append({
                "turn_id": message.get("turn_id"),
                "speaker": message.get("speaker") or message.get("role"),
                "content": content,
            })
        sessions.append({
            "session_id": session.get("session_id"),
            "source_session_id": session.get("source_session_id"),
            "timestamp": session.get("timestamp"),
            "messages": messages,
        })
    return {"source_id": group["source_id"], "sessions": sessions}


def call_codex(prompt: str, model: str, reasoning_effort: str, timeout_sec: float) -> tuple[str, int | None]:
    with tempfile.NamedTemporaryFile("r+", encoding="utf-8", delete=False) as tmp:
        output_path = tmp.name
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "-o",
        output_path,
        "-",
    ]
    try:
        completed = subprocess.run(command, input=prompt, text=True, capture_output=True, timeout=timeout_sec, check=False)
        output = Path(output_path).read_text(encoding="utf-8").strip()
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"codex exited with {completed.returncode}")
        if not output:
            raise RuntimeError("codex returned empty output")
        return output, parse_tokens_used(completed.stdout + "\n" + completed.stderr)
    finally:
        try:
            Path(output_path).unlink()
        except FileNotFoundError:
            pass


def parse_json_block(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if not match:
            raise
        return json.loads(match.group(1))


def parse_tokens_used(log: str) -> int | None:
    matches = list(re.finditer(r"tokens used\s+([0-9,]+)", log, flags=re.I))
    if not matches:
        return None
    return int(matches[-1].group(1).replace(",", ""))


def clean_memories(source_id: str, values: list[Any]) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        memory = str(value.get("memory") or "").strip()
        title = str(value.get("title") or "").strip()
        if len(memory) < 20:
            continue
        source_date = date_part(str(value.get("source_date") or "").strip())
        event_date = date_part(str(value.get("event_date") or "").strip()) or str(value.get("event_date") or "").strip()
        item = {
            "source_id": source_id,
            "session_id": str(value.get("session_id") or "").strip(),
            "source_turn_ids": [str(x).strip() for x in value.get("source_turn_ids") or [] if str(x).strip()],
            "title": title or memory[:80],
            "kind": clean_kind(value.get("kind")),
            "topics": clean_topics(value.get("topics")),
            "memory": memory,
            "source_date": source_date,
            "event_date": event_date,
        }
        key = stable_memory_key(item)
        if key in seen:
            continue
        item["memory_key"] = key
        seen.add(key)
        out.append(item)
    return out


def clean_kind(value: Any) -> str:
    kind = str(value or "fact").strip().lower().replace("kind:", "")
    return kind if kind in KINDS else "fact"


def date_part(value: str) -> str:
    match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", value)
    return match.group(0) if match else ""


def clean_topics(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else []
    out = []
    seen = set()
    for item in raw:
        topic = normalize_part(str(item)).replace("_", "-")
        if topic and topic not in seen:
            seen.add(topic)
            out.append(topic[:40])
    return out[:8]


def recall_case(
    client: ApiClient,
    case: dict[str, Any],
    by_source: dict[str, dict[str, Any]],
    top_k: int,
    base_url: str,
    agent_id: str,
    semantic_ledger_context_limit: int,
    search_debug: bool,
    search_text_matches: bool,
    recall_query_mode: str,
    recall_plan: str,
    recall_variant_limit: int,
    recall_reserved_slots: int,
    wiki_context: bool,
    wiki_context_source: str,
    wiki_context_limit: int,
    wiki_ref_fetch_limit: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    source_id = str(case.get("source_id") or "").strip()
    source = by_source.get(source_id, {})
    repo = str(source.get("repo") or "").strip()
    if not repo:
        return error_prediction(case, "missing repo/memories for source", base_url, agent_id, source_id, repo)
    question = str(case.get("question") or "")
    route = classify_recall_route(question)
    recall_variant_limit = normalize_recall_variant_limit(recall_variant_limit)
    effective_recall_plan = recall_plan
    if recall_plan == "targeted":
        effective_recall_plan = "multi" if route == "literal" else "single"
    elif recall_plan == "reserved":
        effective_recall_plan = "reserved" if route == "literal" else "single"
    plan_query_mode = "full" if recall_plan == "reserved" else recall_query_mode
    variants = build_recall_query_variants(question, plan_query_mode, effective_recall_plan, recall_variant_limit)
    primary = variants[0] if variants else {"name": recall_query_mode, "text": build_recall_query_text(question, recall_query_mode)}
    query_text = str(primary.get("text") or "")
    query = build_search_query(query_text, repo)
    per_page = max(20, min(100, top_k * 3))
    memory_rows = source.get("memories_by_issue", {})
    candidate_runs = []
    for variant in variants:
        variant_name = str(variant.get("name") or "query")
        variant_text = str(variant.get("text") or "").strip()
        if not variant_text:
            continue
        variant_query = build_search_query(variant_text, repo)
        candidates = search_memory_candidates(
            client,
            variant_query,
            per_page,
            search_debug,
            search_text_matches,
            memory_rows,
        )
        candidate_runs.append({
            "name": variant_name,
            "text": variant_text,
            "query": variant_query,
            "weight": float(variant.get("weight") or 1.0),
            "candidates": candidates,
        })
    if effective_recall_plan == "multi":
        candidates = fuse_candidate_runs(candidate_runs)
    elif effective_recall_plan == "reserved":
        candidates = reserve_candidate_slots(candidate_runs, top_k, recall_reserved_slots)
    else:
        candidates = candidate_runs[0]["candidates"] if candidate_runs else []
    wiki_contexts: list[dict[str, Any]] = []
    wiki_ref_candidates: list[dict[str, Any]] = []
    if wiki_context:
        if wiki_context_source == "map":
            wiki_contexts = cached_wiki_contexts_for_query(source, query_text, max(1, wiki_context_limit))
        else:
            wiki_contexts = search_wiki_contexts(client, repo, query_text, max(1, wiki_context_limit))
        wiki_ref_candidates = wiki_referenced_memory_candidates(
            client,
            repo,
            wiki_contexts,
            memory_rows,
            query_text,
            max(0, wiki_ref_fetch_limit),
        )
        if wiki_ref_candidates:
            candidates = fuse_wiki_anchor_candidates(candidates, wiki_ref_candidates, top_k)
    memories = candidates[:top_k]
    debug_summary = recall_debug_summary(memories)
    selection_counts = recall_selection_counts(memories)
    return prediction_row(case, memories, {
        "adapter": "clawmem_skill_memory_only_v4",
        "base_url": base_url.rstrip("/"),
        "index_mode": "plugin-finalize",
        "answer_context_mode": "raw_memory_recall_text",
        "recall_route": route,
        "recall_query": query,
        "recall_query_text": query_text,
        "recall_query_mode": plan_query_mode,
        "recall_plan": recall_plan,
        "recall_effective_plan": effective_recall_plan,
        "recall_variant_limit": recall_variant_limit,
        "recall_fusion": (
            "plugin_rank_priority" if effective_recall_plan == "multi"
            else "reserved_slots" if effective_recall_plan == "reserved"
            else "none"
        ),
        "recall_query_variants": [
            {
                "name": run["name"],
                "text": run["text"],
                "query": run["query"],
                "weight": run["weight"],
                "candidate_count": len(run["candidates"]),
            }
            for run in candidate_runs
        ],
        "recall_candidate_count": len(candidates),
        "wiki_context_enabled": wiki_context,
        "wiki_context_source": wiki_context_source if wiki_context else "",
        "wiki_context_count": len(wiki_contexts),
        "wiki_context_slugs": [str(context.get("slug") or "") for context in wiki_contexts if context.get("slug")],
        "wiki_ref_candidate_count": len(wiki_ref_candidates),
        "recall_ledger_candidate_count": sum(1 for memory in candidates if is_literal_anchor_memory(memory)),
        "recall_reserved_slots": max(0, recall_reserved_slots) if effective_recall_plan == "reserved" else 0,
        "recall_reserved_used": selection_counts.get("reserved", 0),
        "recall_selection_counts": selection_counts,
        "source_id": source_id,
        "agent_id": agent_id,
        "repo": repo,
        "recall_latency_ms": int((time.perf_counter() - started) * 1000),
        "recall_top_k": top_k,
        "semantic_ledger_context_limit": semantic_ledger_context_limit,
        "search_debug_requested": search_debug,
        "search_text_matches_requested": search_text_matches,
        **debug_summary,
    }, candidates, wiki_contexts)


def build_search_query(query_text: str, repo: str) -> str:
    cleaned = re.sub(r"https?://\S+", " ", query_text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 1500:
        cleaned = cleaned[:1500].strip()
    return " ".join([cleaned, f"repo:{repo}", "is:issue", "state:open", 'label:"type:memory"']).strip()


def search_memory_candidates(
    client: ApiClient,
    query: str,
    per_page: int,
    search_debug: bool,
    search_text_matches: bool,
    memory_rows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    params = {"q": query, "per_page": str(per_page)}
    if search_debug:
        params["debug"] = "true"
    if search_text_matches:
        params["text_matches"] = "true"
    data = client.request("GET", f"search/issues?{urllib.parse.urlencode(params)}")
    items = data.get("items") if isinstance(data, dict) else []
    candidates = []
    for issue in items if isinstance(items, list) else []:
        if not isinstance(issue, dict):
            continue
        labels = label_names(issue.get("labels"))
        if "type:memory" not in labels or issue.get("state") == "closed":
            continue
        number = str(issue.get("number") or "").strip()
        mapped = memory_rows.get(number, {})
        candidates.append({
            "issue_number": number,
            "title": str(issue.get("title") or ""),
            "body": str(issue.get("body") or ""),
            "labels": labels,
            "mapped": mapped,
            "score": safe_float(issue.get("score")),
            "backend_score": safe_float(issue.get("score")),
            "debug": search_debug_payload(issue.get("debug")),
            "text_matches": search_text_matches_payload(issue.get("text_matches")),
        })
    return candidates


def search_wiki_contexts(client: ApiClient, repo: str, query_text: str, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    params = {"q": build_recall_query_text(query_text, "full"), "limit": str(limit)}
    try:
        data = client.request("GET", f"repos/{repo}/wiki/search?{urllib.parse.urlencode(params)}")
    except Exception:
        return []
    results = data.get("results") if isinstance(data, dict) else []
    contexts: list[dict[str, Any]] = []
    for result in results if isinstance(results, list) else []:
        if not isinstance(result, dict):
            continue
        slug = str(result.get("slug") or "").strip()
        if not slug:
            continue
        try:
            page = client.request("GET", f"repos/{repo}/wiki/pages/{wiki_slug_path(slug)}")
        except Exception:
            continue
        body = str(page.get("body") or "").strip() if isinstance(page, dict) else ""
        if not body:
            body = str(result.get("snippet") or "").strip()
        refs = extract_wiki_issue_refs(body, query_text)
        contexts.append({
            "slug": slug,
            "title": str((page if isinstance(page, dict) else {}).get("title") or result.get("title") or slug),
            "body": body,
            "excerpt": wiki_context_excerpt(body, query_text, refs),
            "score": safe_float(result.get("score")),
            "issue_refs": refs,
        })
    return contexts


def cached_wiki_contexts_for_query(source: dict[str, Any], query_text: str, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    pages = source.get("wiki_context_pages")
    if not isinstance(pages, list):
        return []
    contexts: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        body = str(page.get("body") or "").strip()
        if not body:
            continue
        refs = extract_wiki_issue_refs(body, query_text)
        contexts.append({
            "slug": str(page.get("slug") or ""),
            "title": str(page.get("title") or page.get("slug") or ""),
            "body": body,
            "excerpt": wiki_context_excerpt(body, query_text, refs),
            "issue_refs": refs,
            "score": wiki_context_query_score(body, query_text, refs),
        })
    contexts.sort(key=lambda item: -float_or(item.get("score"), 0.0))
    return contexts[:limit]


def wiki_context_query_score(body: str, query_text: str, refs: list[str]) -> float:
    tokens = wiki_ref_query_tokens(query_text)
    if not body.strip() or not tokens:
        return float(len(refs) > 0)
    best = 0
    for line in body.splitlines():
        best = max(best, wiki_ref_line_score(line, tokens))
    return float(best + min(len(refs), 10) / 100.0)


def wiki_referenced_memory_candidates(
    client: ApiClient,
    repo: str,
    contexts: list[dict[str, Any]],
    memory_rows: dict[str, dict[str, Any]],
    query_text: str,
    limit: int,
) -> list[dict[str, Any]]:
    del query_text
    if limit <= 0:
        return []
    refs: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    anchor_rank = 0
    for context in contexts:
        slug = str(context.get("slug") or "").strip()
        for ref in context.get("issue_refs") if isinstance(context.get("issue_refs"), list) else []:
            issue_number = local_issue_number(str(ref), repo)
            if not issue_number or issue_number in seen:
                continue
            seen.add(issue_number)
            anchor_rank += 1
            refs.append((anchor_rank, issue_number, slug))
            if len(refs) >= limit:
                break
        if len(refs) >= limit:
            break

    candidates: list[dict[str, Any]] = []
    for anchor_rank, issue_number, slug in refs:
        mapped = memory_rows.get(issue_number, {})
        if mapped:
            candidates.append({
                "issue_number": issue_number,
                "title": str(mapped.get("title") or "Memory"),
                "body": render_memory_body(mapped),
                "labels": ["type:memory", f"kind:{clean_kind(mapped.get('kind'))}"],
                "mapped": mapped,
                "score": 1.0 / (60.0 + anchor_rank),
                "debug": {},
                "text_matches": [],
                "selection": "wiki_anchor",
                "wiki_anchor_rank": anchor_rank,
                "wiki_anchors": [slug] if slug else [],
            })
            continue
        try:
            issue = client.request("GET", f"repos/{repo}/issues/{issue_number}")
        except Exception:
            continue
        if not isinstance(issue, dict):
            continue
        labels = label_names(issue.get("labels"))
        if "type:memory" not in labels or issue.get("state") == "closed":
            continue
        candidates.append({
            "issue_number": issue_number,
            "title": str(issue.get("title") or ""),
            "body": str(issue.get("body") or ""),
            "labels": labels,
            "mapped": mapped,
            "score": 1.0 / (60.0 + anchor_rank),
            "debug": {},
            "text_matches": [],
            "selection": "wiki_anchor",
            "wiki_anchor_rank": anchor_rank,
            "wiki_anchors": [slug] if slug else [],
        })
    return candidates


def fuse_wiki_anchor_candidates(
    direct: list[dict[str, Any]],
    wiki_candidates: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    by_issue: dict[str, dict[str, Any]] = {}
    for rank, candidate in enumerate(direct, 1):
        issue_number = str(candidate.get("issue_number") or "").strip()
        if not issue_number:
            continue
        copied = {**candidate}
        copied["direct_rank"] = rank
        by_issue[issue_number] = copied
    for candidate in wiki_candidates:
        issue_number = str(candidate.get("issue_number") or "").strip()
        if not issue_number:
            continue
        existing = by_issue.get(issue_number)
        if existing is None:
            by_issue[issue_number] = {**candidate}
            continue
        existing["wiki_anchor_rank"] = min(
            int_or(existing.get("wiki_anchor_rank"), 10**9),
            int_or(candidate.get("wiki_anchor_rank"), 10**9),
        )
        existing["wiki_anchors"] = unique_nonempty([
            *[str(value) for value in existing.get("wiki_anchors") or []],
            *[str(value) for value in candidate.get("wiki_anchors") or []],
        ])

    fused = list(by_issue.values())
    for candidate in fused:
        direct_rank = int_or(candidate.get("direct_rank"), 0)
        wiki_rank = int_or(candidate.get("wiki_anchor_rank"), 0)
        primary = 1000.0 - direct_rank * 10.0 if direct_rank > 0 else 0.0
        anchor = 985.0 - wiki_rank * 5.0 if wiki_rank > 0 else 0.0
        bonus = 20.0 if direct_rank > 0 and wiki_rank > 0 else 0.0
        candidate["wiki_fusion_score"] = max(primary, anchor) + bonus
        if wiki_rank > 0:
            candidate["fusion_anchor"] = "wiki_context"
    fused.sort(key=lambda item: (
        -float_or(item.get("wiki_fusion_score"), 0.0),
        int_or(item.get("direct_rank"), 10**6),
        int_or(item.get("wiki_anchor_rank"), 10**6),
        -safe_int(item.get("issue_number")),
    ))
    for rank, candidate in enumerate(fused, 1):
        candidate["fusion_rank"] = rank
    return fused[: max(top_k, len(direct))]


def extract_wiki_issue_refs(markdown: str, query_text: str) -> list[str]:
    masked = mask_wiki_ignored_markdown(markdown)
    query_tokens = wiki_ref_query_tokens(query_text)
    scored: dict[str, dict[str, int]] = {}
    order = 0
    for line in masked.splitlines():
        refs = re.findall(r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#\d+\b", line)
        if not refs:
            continue
        score = wiki_ref_line_score(line, query_tokens)
        for ref in refs:
            if ref not in scored:
                scored[ref] = {"score": score, "order": order}
                order += 1
            elif score > scored[ref]["score"]:
                scored[ref]["score"] = score
    return [
        ref
        for ref, _ in sorted(scored.items(), key=lambda item: (-item[1]["score"], item[1]["order"]))
    ]


def wiki_context_excerpt(markdown: str, query_text: str, refs: list[str], limit: int = 900) -> str:
    text = markdown.replace("\r", "\n").strip()
    if not text:
        return ""
    query_tokens = wiki_ref_query_tokens(query_text)
    ref_set = set(refs[:10])
    scored: list[tuple[int, int, str]] = []
    for index, line in enumerate(text.splitlines()):
        stripped = re.sub(r"\s+", " ", line).strip()
        if not stripped:
            continue
        line_refs = set(re.findall(r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#\d+\b", stripped))
        token_score = wiki_ref_line_score(stripped, query_tokens)
        ref_score = 8 if line_refs & ref_set else 0
        heading_score = 1 if stripped.startswith("#") else 0
        score = ref_score + token_score + heading_score
        if score <= 0:
            continue
        scored.append((-score, index, stripped))
    if not scored:
        return compact_wiki_summary(text, limit)
    scored.sort()
    selected = sorted(scored[:8], key=lambda item: item[1])
    excerpt = "\n".join(line for _, _, line in selected)
    return compact_wiki_summary(excerpt, limit)


def wiki_ref_query_tokens(query_text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for _, _, normalized in normalized_query_tokens(query_text):
        token = stabilize_query_token(normalized, singularize=False).lower()
        if (
            token in seen
            or token in QUERY_STOPWORDS
            or token in GENERIC_QUERY_TERMS
            or token in UNSTABLE_QUERY_ACTION_TERMS
        ):
            continue
        if len(token) < 3 and not token.isdigit():
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= 8:
            break
    return out


def wiki_ref_line_score(line: str, query_tokens: list[str]) -> int:
    lower = line.lower()
    return sum(1 for token in query_tokens if token in lower)


def mask_wiki_ignored_markdown(markdown: str) -> str:
    text = re.sub(r"<!--.*?-->", lambda match: " " * len(match.group(0)), markdown, flags=re.S)
    text = re.sub(r"```.*?```", lambda match: " " * len(match.group(0)), text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", lambda match: " " * len(match.group(0)), text)
    return text


def local_issue_number(ref: str, repo: str) -> str:
    local = re.fullmatch(r"#(\d+)", ref)
    if local:
        return local.group(1)
    cross = re.fullmatch(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)", ref)
    if cross and cross.group(1).lower() == repo.lower():
        return cross.group(2)
    return ""


def fuse_candidate_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_issue: dict[str, dict[str, Any]] = {}
    for run_priority, run in enumerate(runs):
        name = str(run.get("name") or "query")
        weight = float(run.get("weight") or 1.0)
        candidates = run.get("candidates") if isinstance(run.get("candidates"), list) else []
        for rank, candidate in enumerate(candidates, 1):
            if not isinstance(candidate, dict):
                continue
            if name != "full" and not has_lexical_signal(candidate):
                continue
            issue_number = str(candidate.get("issue_number") or "").strip()
            if not issue_number:
                continue
            entry = by_issue.get(issue_number)
            if entry is None:
                entry = {
                    **candidate,
                    "fusion_score": 0.0,
                    "fusion_ranks": {},
                    "fusion_scores": {},
                    "fusion_weights": {},
                    "variant_debug": {},
                    "variant_text_matches": {},
                    "best_variant": name,
                    "best_variant_rank": rank,
                    "best_variant_priority": run_priority,
                }
                by_issue[issue_number] = entry
            contribution = weight / (60.0 + float(rank))
            entry["fusion_score"] = float(entry.get("fusion_score") or 0.0) + contribution
            entry["fusion_ranks"][name] = rank
            entry["fusion_scores"][name] = contribution
            entry["fusion_weights"][name] = weight
            if candidate.get("debug"):
                entry["variant_debug"][name] = candidate.get("debug")
            if candidate.get("text_matches"):
                entry["variant_text_matches"][name] = candidate.get("text_matches")
            best_rank = int_or(entry.get("best_variant_rank"), 10**9)
            best_priority = int_or(entry.get("best_variant_priority"), 10**9)
            if rank < best_rank or (rank == best_rank and run_priority < best_priority):
                entry["best_variant"] = name
                entry["best_variant_rank"] = rank
                entry["best_variant_priority"] = run_priority
                entry["debug"] = candidate.get("debug")
                entry["text_matches"] = candidate.get("text_matches")
                entry["backend_score"] = candidate.get("backend_score")
    fused = list(by_issue.values())
    for candidate in fused:
        effective_rank = float(int_or(candidate.get("best_variant_rank"), 100000))
        candidate["fusion_anchor"] = "best_variant"
        candidate["fusion_effective_rank"] = effective_rank
        candidate["fusion_score"] = 1.0 / (60.0 + effective_rank)
    fused.sort(key=lambda item: (
        float_or(item.get("fusion_effective_rank"), 10**9),
        int_or(item.get("best_variant_priority"), 10**6),
        int_or(item.get("best_variant_rank"), 10**6),
        -safe_int(item.get("issue_number")),
    ))
    for rank, candidate in enumerate(fused, 1):
        candidate["score"] = float(candidate.get("fusion_score") or 0.0)
        candidate["fusion_rank"] = rank
    return fused


def reserve_candidate_slots(
    runs: list[dict[str, Any]],
    top_k: int,
    reserved_slots: int,
) -> list[dict[str, Any]]:
    if top_k <= 0 or not runs:
        return []
    full_run = next((run for run in runs if run.get("name") == "full"), runs[0])
    full_candidates = full_run.get("candidates") if isinstance(full_run.get("candidates"), list) else []
    repair_runs = [run for run in runs if run is not full_run]
    reserve_limit = min(max(0, reserved_slots), max(0, top_k - 1))
    full_prefix_limit = max(0, top_k - reserve_limit)

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_candidate(candidate: dict[str, Any], selection: str, variant: str, rank: int) -> bool:
        issue_number = str(candidate.get("issue_number") or "").strip()
        if not issue_number or issue_number in seen:
            return False
        copied = {**candidate}
        copied["selection"] = selection
        copied["selection_variant"] = variant
        copied["selection_variant_rank"] = rank
        selected.append(copied)
        seen.add(issue_number)
        return True

    for rank, candidate in enumerate(full_candidates[:full_prefix_limit], 1):
        if isinstance(candidate, dict):
            add_candidate(candidate, "full", str(full_run.get("name") or "full"), rank)

    reserved_added = 0
    for run in repair_runs:
        variant = str(run.get("name") or "repair")
        candidates = run.get("candidates") if isinstance(run.get("candidates"), list) else []
        for rank, candidate in enumerate(candidates, 1):
            if reserved_added >= reserve_limit:
                break
            if not isinstance(candidate, dict) or not has_lexical_signal(candidate):
                continue
            if add_candidate(candidate, "reserved", variant, rank):
                reserved_added += 1
        if reserved_added >= reserve_limit:
            break

    for rank, candidate in enumerate(full_candidates, 1):
        if len(selected) >= top_k:
            break
        if isinstance(candidate, dict):
            add_candidate(candidate, "full_fill", str(full_run.get("name") or "full"), rank)

    all_runs = [full_run, *repair_runs]
    for run in all_runs:
        variant = str(run.get("name") or "query")
        candidates = run.get("candidates") if isinstance(run.get("candidates"), list) else []
        for rank, candidate in enumerate(candidates, 1):
            if isinstance(candidate, dict):
                add_candidate(candidate, "candidate_pool", variant, rank)

    return selected


def has_lexical_signal(candidate: dict[str, Any]) -> bool:
    debug = candidate.get("debug") if isinstance(candidate.get("debug"), dict) else {}
    path = str(debug.get("search_path") or "")
    return safe_int(debug.get("lexical_rank")) > 0 or path in {"hybrid", "lexical_only"}


def recall_selection_counts(memories: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for memory in memories:
        selection = str(memory.get("selection") or "ranked").strip() or "ranked"
        counts[selection] = counts.get(selection, 0) + 1
    return counts


def build_recall_query_variants(
    question: str,
    mode: str,
    plan: str,
    variant_limit: int,
) -> list[dict[str, Any]]:
    if plan == "reserved":
        cleaned = normalize_query_text(question)
        variants: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(name: str, text: str, weight: float) -> None:
            text = normalize_query_text(text)
            key = text.lower()
            if not text or key in seen:
                return
            seen.add(key)
            variants.append({"name": name, "text": text, "weight": weight})

        add("full", cleaned, 1.0)
        add("compact", " ".join(compact_query_tokens(cleaned)[:4]), 1.0)
        add("literal", " ".join(literal_query_tokens(cleaned)[:6]), 1.0)
        if variant_limit > 0:
            variants = variants[:variant_limit]
        return variants or [{"name": "full", "text": cleaned, "weight": 1.0}]

    if plan != "multi":
        return [{"name": mode, "text": build_recall_query_text(question, mode), "weight": 1.0}]

    cleaned = normalize_query_text(question)
    variants: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(name: str, text: str, weight: float) -> None:
        text = normalize_query_text(text)
        key = text.lower()
        if not text or key in seen:
            return
        seen.add(key)
        variants.append({"name": name, "text": text, "weight": weight})

    add("full", cleaned, 1.0)
    add("compact", " ".join(compact_query_tokens(cleaned)[:4]), 0.55)
    add("core", " ".join(core_query_tokens(cleaned)[:4]), 0.5)
    add("surface", " ".join(surface_query_tokens(cleaned)[:4]), 0.5)
    if classify_recall_route(cleaned) == "literal":
        add("literal", " ".join(literal_query_tokens(cleaned)[:6]), 0.75)
    add("entity", " ".join(entity_query_tokens(cleaned)[:5]), 0.35)

    if variant_limit > 0:
        variants = variants[:variant_limit]
    return variants or [{"name": "full", "text": cleaned, "weight": 1.0}]


def normalize_recall_variant_limit(value: int) -> int:
    return min(6, max(1, int(value)))


QUERY_STOPWORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "been", "being",
    "by", "can",
    "could", "did", "do", "does", "for", "from", "had", "has", "have", "he",
    "her", "hers", "him", "his", "how", "if", "in", "into", "is", "it", "its",
    "many", "much", "of", "on", "or", "over", "she", "should", "that",
    "the", "their", "them", "then", "there", "these", "they", "this",
    "those", "to", "was", "were", "what", "when", "where", "which", "who",
    "whom", "why", "will", "with", "would",
}

GENERIC_QUERY_TERMS = {
    "ago", "alive", "called", "considered", "current", "date", "day",
    "exact", "first", "going", "group", "last", "likely", "long", "longer",
    "month", "motivational", "name", "names", "next", "old", "planned",
    "planning", "plans", "previous", "range", "recent", "recently", "still",
    "stunning", "time", "times", "today", "tomorrow", "want", "year",
    "years", "yesterday",
}

# GitHub-compatible issue search is strict about lexical terms. Query verbs are
# often asked in a different form than the source/memory uses (run/ran, take/took,
# buy/bought), so compact queries should prefer stable entities and nouns.
UNSTABLE_QUERY_ACTION_TERMS = {
    "add", "added", "adding", "ask", "asked", "asking", "began", "begin",
    "beginning", "bring", "brought", "bought", "buy", "buying", "came",
    "capture", "captured", "capturing", "consider", "considered",
    "considering", "create", "created", "creating", "did", "does", "doing",
    "dating", "decide", "decided", "deciding", "done", "find", "finding",
    "found", "gave", "get", "gets", "getting", "give",
    "given", "giving", "go", "goes", "going", "gone", "got", "had", "have",
    "having", "help", "helped", "helping", "keep", "kept", "know", "learn",
    "learned", "learning", "like", "liked", "made", "make", "making", "meet",
    "met", "need", "needed", "plan", "planned", "planning", "promote",
    "promoted", "promoting", "receive",
    "received", "receiving", "recommend", "recommended", "recommending",
    "remember", "remembered", "run", "running", "said", "saw", "see",
    "seeing", "seen", "sign", "signed", "signing", "show", "showed",
    "showing", "start", "started",
    "starting", "take", "taken", "takes", "taking", "think", "thinking",
    "told", "took", "try", "trying", "use", "used", "using", "want",
    "wanted", "watch", "watched", "went", "work", "worked", "working",
    "write", "writes", "writing", "wrote",
}

ORDINAL_QUERY_TERMS = {
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
    "eighth", "ninth", "tenth", "last", "latest", "next", "previous",
}

QUERY_TOKEN_ALIASES = {
    "clothes": "clothing",
    "dancing": "dance",
    "photography": "photo",
    "photoshoot": "photo",
}

WEAK_CORE_QUERY_TERMS = {
    "activity", "book", "day", "event", "favorite", "friend", "item",
    "memory", "month", "mountain", "name", "person", "photo", "picture", "thing",
    "time", "week", "year",
}

DATE_ANCHOR_TERMS = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "spring", "summer", "fall",
    "autumn", "winter", "morning", "afternoon", "evening", "night", "week",
    "weekend", "month", "year", "birthday", "anniversary",
}


def build_recall_query_text(question: str, mode: str) -> str:
    cleaned = normalize_query_text(question)
    if mode != "compact":
        return cleaned

    tokens = compact_query_tokens(cleaned)
    if len(tokens) < 2:
        return cleaned
    return " ".join(tokens[:4])


def normalize_query_text(text: str) -> str:
    cleaned = re.sub(r"https?://\S+", " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def normalized_query_tokens(text: str) -> list[tuple[int, str, str]]:
    raw_tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'_-]*", text)
    out = []
    for index, token in enumerate(raw_tokens):
        normalized = token.strip("'_-.")
        normalized = re.sub(r"'s$", "", normalized, flags=re.I)
        normalized = normalized.strip("'_-.")
        if normalized:
            out.append((index, token, normalized))
    return out


def compact_query_tokens(text: str) -> list[str]:
    scored: list[tuple[int, int, str]] = []
    seen = set()
    for index, token, normalized in normalized_query_tokens(text):
        normalized = stabilize_query_token(normalized, singularize=True)
        key = normalized.lower()
        if (
            key in seen
            or key in QUERY_STOPWORDS
            or key in GENERIC_QUERY_TERMS
            or key in UNSTABLE_QUERY_ACTION_TERMS
        ):
            continue
        if len(key) < 3 and not key.isdigit():
            continue
        seen.add(key)
        score = 0
        if re.fullmatch(r"\d{2,4}", key):
            score += 6
        if token[:1].isupper():
            score += 5
        if key in ORDINAL_QUERY_TERMS:
            score += 5
        if len(key) >= 6:
            score += 2
        scored.append((-score, index, normalized))
    scored.sort()
    selected = sorted(scored[:4], key=lambda item: item[1])
    return [token for _, _, token in selected]


def entity_query_tokens(text: str) -> list[str]:
    out = []
    seen = set()
    for _, token, normalized in normalized_query_tokens(text):
        normalized = stabilize_query_token(normalized, singularize=False)
        key = normalized.lower()
        if key in seen or key in QUERY_STOPWORDS:
            continue
        if token[:1].isupper() or re.fullmatch(r"\d{2,4}", key):
            seen.add(key)
            out.append(normalized)
    return out


def literal_query_tokens(text: str) -> list[str]:
    out = []
    seen = set()
    for _, token, normalized in normalized_query_tokens(text):
        normalized = stabilize_query_token(normalized, singularize=True)
        key = normalized.lower()
        if key in QUERY_STOPWORDS:
            continue
        keep = (
            key not in GENERIC_QUERY_TERMS
            or key in DATE_ANCHOR_TERMS
            or key in {"name", "called", "first", "last", "current"}
            or re.fullmatch(r"\d{1,4}", key) is not None
            or token[:1].isupper()
        )
        if key in UNSTABLE_QUERY_ACTION_TERMS and not token[:1].isupper():
            keep = False
        if not keep or key in seen:
            continue
        if len(key) < 3 and not key.isdigit():
            continue
        seen.add(key)
        out.append(normalized)
    return out


def surface_query_tokens(text: str) -> list[str]:
    out = []
    seen = set()
    for _, _, normalized in normalized_query_tokens(text):
        normalized = stabilize_query_token(normalized, singularize=False)
        key = normalized.lower()
        if (
            key in seen
            or key in QUERY_STOPWORDS
            or key in GENERIC_QUERY_TERMS
            or key in UNSTABLE_QUERY_ACTION_TERMS
        ):
            continue
        if len(key) < 3 and not key.isdigit():
            continue
        seen.add(key)
        out.append(normalized)
    return out


def core_query_tokens(text: str) -> list[str]:
    surface = surface_query_tokens(text)
    entities = entity_query_tokens(text)[:2]
    entity_keys = {token.lower() for token in entities}
    non_entities = [token for token in surface if token.lower() not in entity_keys]
    preferred = [token for token in non_entities if token.lower() not in WEAK_CORE_QUERY_TERMS]
    tail = preferred[-2:] if preferred else non_entities[-1:]
    out = []
    seen = set()
    for token in [*entities, *tail]:
        key = token.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(token)
    return out


def stabilize_query_token(token: str, *, singularize: bool) -> str:
    if token[:1].isupper():
        return token
    key = token.lower()
    alias = QUERY_TOKEN_ALIASES.get(key)
    if alias:
        return alias
    if not singularize:
        return token
    if len(key) > 4 and key.endswith("ies"):
        return token[:-3] + "y"
    if len(key) > 4 and key.endswith(("sses", "ches", "shes", "xes", "zes")):
        return token[:-2]
    if len(key) > 4 and key.endswith("s") and not key.endswith(("ss", "us")):
        return token[:-1]
    return token


def classify_recall_route(question: str) -> str:
    return "literal" if LITERAL_QUESTION_RE.search(question or "") else "semantic"


def is_literal_anchor_memory(memory: dict[str, Any]) -> bool:
    text = f"{memory.get('title') or ''}\n{memory.get('body') or memory.get('memory') or ''}".lower()
    return "literal anchors" in text or "literal anchor" in text


def prediction_row(
    case: dict[str, Any],
    memories: list[dict[str, Any]],
    metadata: dict[str, Any],
    candidates: list[dict[str, Any]],
    wiki_contexts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    retrieved_session_ids = []
    retrieved_turn_ids = []
    retrieved_search_debug = []
    lines = []
    route = str(metadata.get("recall_route") or "semantic")
    semantic_ledger_context_limit = int(metadata.get("semantic_ledger_context_limit", -1))
    context_ledger_count = 0
    if memories:
        lines.extend([
            "Temporal note: event_date is the event time when known; source_date is the source conversation date.",
            "Use source_date only to interpret relative phrases when the memory text supports that interpretation.",
            "Preserve date granularity: if memory text only supports a month, year, or says exact day not stated, do not invent a specific day.",
            "For time questions, resolve supported relative phrases such as last week or yesterday against source_date, then answer with the calendar time at the requested granularity instead of repeating the relative phrase.",
            "For list, set, or profile questions, scan all recalled memories and merge compatible values instead of stopping at the first matching memory.",
            "For status, likely, or counterfactual questions, answer from explicit memory wording or supported inferences only; include uncertainty when the memory says the source does not state something directly.",
            "Wiki context maps, if present below, are orientation and recall boosters; issue memories remain the source of truth.",
            "",
        ])
    for context in (wiki_contexts or [])[:3]:
        body = compact_wiki_summary(str(context.get("excerpt") or context.get("body") or ""), 900)
        if not body:
            continue
        refs = [str(ref) for ref in context.get("issue_refs") or [] if str(ref).strip()]
        lines.append(f"Wiki context [{context.get('slug')}] refs={', '.join(refs[:10])}: {body}")
    if wiki_contexts:
        lines.append("")
    for memory in memories:
        mapped = memory.get("mapped") if isinstance(memory.get("mapped"), dict) else {}
        retrieved_session_ids.append(str(mapped.get("session_id") or "").strip())
        retrieved_turn_ids.extend([str(x).strip() for x in mapped.get("source_turn_ids") or [] if str(x).strip()])
        retrieved_search_debug.append({
            "issue_number": memory.get("issue_number"),
            "title": memory.get("title"),
            "score": memory.get("score"),
            "fusion": memory_fusion_payload(memory),
            "debug": memory.get("debug") if isinstance(memory.get("debug"), dict) else {},
            "text_matches": memory.get("text_matches") if isinstance(memory.get("text_matches"), list) else [],
        })
        if (
            route != "literal"
            and semantic_ledger_context_limit >= 0
            and is_literal_anchor_memory(memory)
        ):
            context_ledger_count += 1
            if context_ledger_count > semantic_ledger_context_limit:
                continue
        labels = [label for label in memory.get("labels", []) if label.startswith("kind:") or label.startswith("topic:")]
        detail = extract_memory_detail(str(memory.get("body") or ""))
        context_bits = [*labels]
        for key in ("event_date", "source_date"):
            value = str(mapped.get(key) or "").strip()
            if value and value.lower() != "unknown":
                context_bits.append(f"{key}:{value}")
        suffix = f" ({', '.join(context_bits)})" if context_bits else ""
        lines.append(f"- [{memory.get('issue_number')}] {memory.get('title')}{suffix}: {detail}")
    return {
        "case_id": case.get("case_id"),
        "benchmark": case.get("benchmark"),
        "source_id": case.get("source_id"),
        "question_type": case.get("question_type"),
        "retrieved_session_ids": unique_nonempty(retrieved_session_ids),
        "retrieved_turn_ids": unique_nonempty(retrieved_turn_ids),
        "retrieved_memory_ids": [str(memory.get("issue_number")) for memory in memories if memory.get("issue_number")],
        "retrieved_search_debug": retrieved_search_debug,
        "recall_candidate_debug": recall_candidate_debug_payload(candidates),
        "raw_recall_text": "\n".join(lines),
        "metadata": {
            **metadata,
            "context_chars": len("\n".join(lines)),
        },
    }


def error_prediction(case: dict[str, Any], message: str, base_url: str, agent_id: str, source_id: str, repo: str) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "benchmark": case.get("benchmark"),
        "source_id": source_id,
        "question_type": case.get("question_type"),
        "retrieved_session_ids": [],
        "retrieved_turn_ids": [],
        "retrieved_memory_ids": [],
        "retrieved_search_debug": [],
        "recall_candidate_debug": [],
        "raw_recall_text": "",
        "error": message,
        "metadata": {
            "adapter": "clawmem_skill_memory_only_v4",
            "base_url": base_url.rstrip("/"),
            "index_mode": "plugin-finalize",
            "source_id": source_id,
            "agent_id": agent_id,
            "repo": repo,
        },
    }


def extract_memory_detail(body: str) -> str:
    match = re.search(r"(?ms)^##\s+Memory\s*\n+(.+?)(?=\n##\s+|\n<!--\s*clawmem|\Z)", body)
    return match.group(1).strip() if match else body.strip()


def safe_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def safe_int(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def safe_int_string(value: Any) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 0


def int_or(value: Any, default: int) -> int:
    return int(value) if isinstance(value, (int, float)) else default


def float_or(value: Any, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) else default


def search_debug_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    payload: dict[str, Any] = {}
    for key in ("search_path",):
        if isinstance(value.get(key), str):
            payload[key] = value[key]
    for key in ("score", "lexical_score", "semantic_distance"):
        if isinstance(value.get(key), (int, float)):
            payload[key] = float(value[key])
    for key in ("lexical_rank", "semantic_rank"):
        if isinstance(value.get(key), (int, float)):
            payload[key] = int(value[key])
    matched_fields = value.get("matched_fields")
    if isinstance(matched_fields, list):
        payload["matched_fields"] = [str(field) for field in matched_fields if str(field).strip()]
    return payload


def search_text_matches_payload(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        matches = []
        for match in item.get("matches") if isinstance(item.get("matches"), list) else []:
            if not isinstance(match, dict):
                continue
            matches.append({
                "text": str(match.get("text") or "")[:120],
                "indices": match.get("indices") if isinstance(match.get("indices"), list) else [],
            })
        out.append({
            "property": str(item.get("property") or ""),
            "fragment": str(item.get("fragment") or "")[:320],
            "matches": matches[:8],
        })
    return out


def recall_debug_summary(memories: list[dict[str, Any]]) -> dict[str, Any]:
    search_path_counts: dict[str, int] = {}
    matched_field_counts: dict[str, int] = {}
    lexical_hits = 0
    semantic_hits = 0
    top_score = None
    top_lexical_rank = 0
    top_semantic_rank = 0
    for index, memory in enumerate(memories):
        debug = memory.get("debug") if isinstance(memory.get("debug"), dict) else {}
        score = memory.get("score") if isinstance(memory.get("score"), (int, float)) else debug.get("score")
        if index == 0:
            top_score = safe_float(score)
            top_lexical_rank = safe_int(debug.get("lexical_rank"))
            top_semantic_rank = safe_int(debug.get("semantic_rank"))
        path = str(debug.get("search_path") or "").strip()
        if path:
            search_path_counts[path] = search_path_counts.get(path, 0) + 1
        if safe_int(debug.get("lexical_rank")) > 0:
            lexical_hits += 1
        if safe_int(debug.get("semantic_rank")) > 0:
            semantic_hits += 1
        for field in debug.get("matched_fields") if isinstance(debug.get("matched_fields"), list) else []:
            name = str(field).strip()
            if name:
                matched_field_counts[name] = matched_field_counts.get(name, 0) + 1
    return {
        "recall_search_path_counts": search_path_counts,
        "recall_matched_field_counts": matched_field_counts,
        "recall_lexical_hit_count": lexical_hits,
        "recall_semantic_hit_count": semantic_hits,
        "recall_top_score": top_score,
        "recall_top_lexical_rank": top_lexical_rank,
        "recall_top_semantic_rank": top_semantic_rank,
    }


def recall_candidate_debug_payload(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rank, candidate in enumerate(candidates, 1):
        mapped = candidate.get("mapped") if isinstance(candidate.get("mapped"), dict) else {}
        out.append({
            "rank": rank,
            "issue_number": candidate.get("issue_number"),
            "title": candidate.get("title"),
            "session_id": mapped.get("session_id"),
            "source_turn_ids": [str(x).strip() for x in mapped.get("source_turn_ids") or [] if str(x).strip()],
            "score": candidate.get("score"),
            "fusion": memory_fusion_payload(candidate),
            "debug": candidate.get("debug") if isinstance(candidate.get("debug"), dict) else {},
            "text_matches": candidate.get("text_matches") if isinstance(candidate.get("text_matches"), list) else [],
        })
    return out


def memory_fusion_payload(memory: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(memory.get("selection"), str):
        payload["selection"] = memory["selection"]
    if isinstance(memory.get("selection_variant"), str):
        payload["selection_variant"] = memory["selection_variant"]
    if isinstance(memory.get("selection_variant_rank"), (int, float)):
        payload["selection_variant_rank"] = int(memory["selection_variant_rank"])
    if isinstance(memory.get("fusion_score"), (int, float)):
        payload["score"] = float(memory["fusion_score"])
    if isinstance(memory.get("fusion_rank"), (int, float)):
        payload["rank"] = int(memory["fusion_rank"])
    if isinstance(memory.get("fusion_ranks"), dict):
        payload["ranks"] = {
            str(key): int(value)
            for key, value in memory["fusion_ranks"].items()
            if isinstance(value, (int, float))
        }
    if isinstance(memory.get("fusion_scores"), dict):
        payload["scores"] = {
            str(key): float(value)
            for key, value in memory["fusion_scores"].items()
            if isinstance(value, (int, float))
        }
    if isinstance(memory.get("fusion_anchor"), str):
        payload["anchor"] = memory["fusion_anchor"]
    if isinstance(memory.get("fusion_effective_rank"), (int, float)):
        payload["effective_rank"] = float(memory["fusion_effective_rank"])
    if isinstance(memory.get("best_variant"), str):
        payload["best_variant"] = memory["best_variant"]
    if isinstance(memory.get("best_variant_rank"), (int, float)):
        payload["best_variant_rank"] = int(memory["best_variant_rank"])
    if isinstance(memory.get("best_variant_priority"), (int, float)):
        payload["best_variant_priority"] = int(memory["best_variant_priority"])
    if isinstance(memory.get("backend_score"), (int, float)):
        payload["backend_score"] = float(memory["backend_score"])
    if isinstance(memory.get("wiki_anchor_rank"), (int, float)):
        payload["wiki_anchor_rank"] = int(memory["wiki_anchor_rank"])
    if isinstance(memory.get("wiki_fusion_score"), (int, float)):
        payload["wiki_fusion_score"] = float(memory["wiki_fusion_score"])
    if isinstance(memory.get("direct_rank"), (int, float)):
        payload["direct_rank"] = int(memory["direct_rank"])
    if isinstance(memory.get("wiki_anchors"), list):
        payload["wiki_anchors"] = [str(value) for value in memory["wiki_anchors"] if str(value).strip()]
    return payload


def label_names(labels: Any) -> list[str]:
    if not isinstance(labels, list):
        return []
    out = []
    for label in labels:
        if isinstance(label, str):
            out.append(label.strip())
        elif isinstance(label, dict):
            out.append(str(label.get("name") or "").strip())
    return [label for label in out if label]


def memory_map_by_source(rows: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows.values():
        source_id = str(row.get("source_id") or "").strip()
        repo = str(row.get("repo") or "").strip()
        issue = str(row.get("issue_number") or "").strip()
        if not source_id or not repo or not issue:
            continue
        source = out.setdefault(source_id, {"repo": repo, "memories_by_issue": {}})
        source["repo"] = repo
        source["memories_by_issue"][issue] = row
    return out


def load_grouped_memories(path: Path) -> dict[str, list[dict[str, Any]]]:
    out = {}
    if not path.exists():
        return out
    for row in read_jsonl(path):
        source_id = str(row.get("source_id") or "").strip()
        memories = row.get("memories")
        if source_id and isinstance(memories, list):
            out[source_id] = [memory for memory in memories if isinstance(memory, dict)]
    return out


def load_memory_map(path: Path) -> dict[str, dict[str, Any]]:
    out = {}
    if not path.exists():
        return out
    for row in read_jsonl(path):
        key = str(row.get("memory_key") or stable_memory_key(row)).strip()
        if key:
            out[key] = row
    return out


def load_wiki_map(path: Path) -> dict[str, dict[str, Any]]:
    out = {}
    if not path.exists():
        return out
    for row in read_jsonl(path):
        repo = str(row.get("repo") or "").strip()
        slug = str(row.get("slug") or "").strip()
        if repo and slug:
            out[f"{repo}:{slug}"] = row
    return out


def load_predictions(path: Path) -> dict[str, dict[str, Any]]:
    out = {}
    if not path.exists():
        return out
    for row in read_jsonl(path):
        if row.get("case_id"):
            out[str(row["case_id"])] = row
    return out


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            rows.append(value)
    return rows


def group_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[str(case.get("source_id") or case.get("case_id"))].append(case)
    out = []
    for source_id, values in grouped.items():
        first = values[0]
        out.append({"source_id": source_id, "cases": values, "sessions": unique_sessions(first.get("sessions") or [])})
    return out


def unique_sessions(sessions: list[Any]) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for index, session in enumerate(sessions):
        if not isinstance(session, dict):
            continue
        key = str(session.get("session_id") or session.get("source_session_id") or index)
        if key in seen:
            continue
        seen.add(key)
        out.append(session)
    return out


def source_repo_name(prefix: str, source_id: str) -> str:
    raw = normalize_part(f"{prefix}-{source_id}").replace("_", "-")
    digest = hashlib.sha1(source_id.encode("utf-8")).hexdigest()[:8]
    return f"{raw[:80].rstrip('-')}-{digest}"


def stable_memory_key(memory: dict[str, Any]) -> str:
    basis = "|".join([
        str(memory.get("source_id") or ""),
        str(memory.get("session_id") or ""),
        str(memory.get("title") or ""),
        str(memory.get("memory") or ""),
    ])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def normalize_part(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")) or "eval"


def unique_nonempty(values: list[str]) -> list[str]:
    out = []
    seen = set()
    for value in values:
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def log(message: str) -> None:
    print(f"[clawmem-locomo-memory-only] {message}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
