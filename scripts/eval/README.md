# ClawMem LoCoMo Harness

This directory is the reproducible evaluation harness for the skill-driven
ClawMem design. It is a formal companion deliverable to the OpenClaw plugin,
not a temporary benchmark scratchpad.

The harness validates the runtime assumptions that matter for ClawMem:

- one provisioned GitHub-compatible agent can own many memory repos
- each LoCoMo source conversation can be stored in its own repo
- recall serves only open `type:memory` issues, not `type:conversation` issues
- extracted memories must be answer-complete enough for downstream answering
- failures should be classified into retention, recall, and answer stages

## Main Flow

Run the memory-only pass:

```bash
python3 scripts/eval/clawmem_locomo_memory_only.py \
  --cases /path/to/locomo.cases.jsonl \
  --out-dir /tmp/clawmem-locomo \
  --run-name memory_only \
  --recall-plan multi \
  --recall-variant-limit 6 \
  --search-debug \
  --keep-going
```

It writes:

- `memory_only.config.json`: provisioned agent route and run config
- `memory_only.memories.jsonl`: extracted grouped memories
- `memory_only.memory_map.jsonl`: repo/issue mapping for stored memories
- `memory_only.predictions.jsonl`: memory-only recall predictions

Generate answers and judge them:

```bash
python3 scripts/eval/codex_batch_answers.py \
  --cases /path/to/locomo.cases.jsonl \
  --predictions /tmp/clawmem-locomo/memory_only.predictions.jsonl \
  --output /tmp/clawmem-locomo/memory_only.answers.jsonl \
  --resume \
  --keep-going

python3 scripts/eval/codex_batch_judge.py \
  --cases /path/to/locomo.cases.jsonl \
  --answers /tmp/clawmem-locomo/memory_only.answers.jsonl \
  --output /tmp/clawmem-locomo/memory_only.answer_metrics.jsonl \
  --resume \
  --keep-going
```

Audit failures:

```bash
python3 scripts/eval/clawmem_locomo_failure_audit.py \
  --cases /path/to/locomo.cases.jsonl \
  --memories-jsonl /tmp/clawmem-locomo/memory_only.memories.jsonl \
  --predictions /tmp/clawmem-locomo/memory_only.predictions.jsonl \
  --answer-metrics /tmp/clawmem-locomo/memory_only.answer_metrics.jsonl \
  --output /tmp/clawmem-locomo/memory_only.failure_audit.json \
  --per-case-output /tmp/clawmem-locomo/memory_only.failure_audit.jsonl

python3 scripts/eval/clawmem_locomo_repair_queue.py \
  --audit /tmp/clawmem-locomo/memory_only.failure_audit.jsonl \
  --output /tmp/clawmem-locomo/memory_only.repair_queue.json
```

## Focused Checks

Use the deterministic retention gate before spending time on answering:

```bash
python3 skills/clawmem/scripts/clawmem_locomo_gate.py \
  --memories-jsonl /tmp/clawmem-locomo/memory_only.memories.jsonl \
  --qa-jsonl /path/to/locomo.cases.jsonl \
  --fail-on-date-granularity-mismatch \
  --fail-on-relative-only-time
```

Use the regression slice for quick comparisons across runs:

```bash
python3 scripts/eval/clawmem_locomo_regression_harness.py \
  --cases /path/to/locomo.cases.jsonl \
  --answer-metrics /tmp/clawmem-locomo/memory_only.answer_metrics.jsonl
```

Use backend search debug when recall changed:

```bash
python3 scripts/eval/clawmem_locomo_recall_debug_analysis.py \
  --cases /path/to/locomo.cases.jsonl \
  --memories-jsonl /tmp/clawmem-locomo/memory_only.memories.jsonl \
  --memory-map-jsonl /tmp/clawmem-locomo/memory_only.memory_map.jsonl \
  --predictions /tmp/clawmem-locomo/memory_only.predictions.jsonl \
  --answer-metrics /tmp/clawmem-locomo/memory_only.answer_metrics.jsonl
```

## Design Notes

The harness intentionally mirrors plugin behavior where it affects measured
quality:

- `--recall-plan multi --recall-variant-limit 6` matches the plugin's default
  query-planner quality mode.
- `--recall-variant-limit 3` is useful only for latency-sensitive probes.
- `conversationSummaryMode: "placeholder"` is acceptable for benchmark runs
  because conversation issues are provenance and do not participate in recall.
- One message per comment remains the normal product behavior; bulk/eval paths
  should not redefine the runtime contract.

Run artifacts should stay outside the repo, usually under `/tmp` or
`~/.codex/tmp`.
