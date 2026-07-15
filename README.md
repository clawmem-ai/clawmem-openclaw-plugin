# clawmem

`clawmem` is a GitHub-backed conversation and memory plugin for OpenClaw.

**What it does:**
- Creates one mandatory `type:conversation` issue per real session and mirrors each user/assistant message as its own transcript comment.
- Before turns: best-effort injects compact context from active `type:memory` issues when it can do so cheaply.
- On reset/end: best-effort writes the final conversation summary/title. Durable memory retention is skill-driven, not plugin-owned.
- Exposes only operational tools: `clawmem_status`, `clawmem_sync`, and `clawmem_maintain`.

---

## Install

```bash
openclaw plugins install @clawmem-ai/clawmem
openclaw plugins enable clawmem
openclaw config set plugins.slots.memory clawmem
openclaw config validate
openclaw gateway restart
```

After restart, confirm OpenClaw shows ClawMem as the active memory plugin. On first use, clawmem bootstraps each agent identity by calling `POST /api/ext/v1/agents` on `git.clawmem.ai`, then writes the returned `token` plus `repo_full_name` back into your config under `plugins.entries.clawmem.config.agents.<agentId>` as that agent's `defaultRepo`. Automatic flows use that `defaultRepo`; explicit memory work should resolve the route and operate on GitHub-compatible repos through the bundled skill and `gh` / `gh api`.

The package now also ships a bundled `clawmem` skill for runtime memory behavior:
- GitHub-native recall and retention workflow
- GitHub-native team memory routing, governance, and lifecycle guidance
- post-install repair and verification guidance
- memory schema and OKF wiki compiled-knowledge rules
- concrete GitHub-compatible `gh` / `gh api` operations

The website `SKILL.md` should stay bootstrap-focused. Once the plugin is installed, rely on the bundled plugin skill for day-to-day memory behavior.

---

## Publishing

This repo publishes `@clawmem-ai/clawmem` through GitHub Actions using npm trusted publishing.

Before the workflow can publish successfully, configure the package on npmjs.com with this trusted publisher:

- Organization or user: `clawmem-ai`
- Repository: `clawmem-openclaw-plugin`
- Workflow filename: `release.yml`

Release flow:

1. Bump `package.json` to the version you want to ship.
2. Create and push a matching tag such as `0.1.6`.
3. GitHub Actions runs `.github/workflows/release.yml` and publishes with OIDC. No long-lived `NPM_TOKEN` secret is required.

The workflow intentionally publishes from a tag push instead of `workflow_dispatch`, because npm validates the workflow filename exactly when using trusted publishing.

---

## Runtime Model

ClawMem is OpenClaw's durable memory system.

- Durable facts, preferences, conventions, decisions, lessons, skill pointers, and active-task state belong in ClawMem memory issues.
- Files remain for tools or humans to read directly.
- Memory routing is per agent identity: `plugins.entries.clawmem.config.agents.<agentId>.defaultRepo` is the default space, and explicit `gh` / `gh api` operations may target other repos.
- Shared or team memory should live in a shared repo, not in one agent's private default repo.
- Use the bundled skill and GitHub-compatible operations for memory work. Plugin tools are operational controls, not memory CRUD wrappers.

## Bundled Skill And Docs

The plugin package is now the runtime source of truth:

- Bundled runtime skill: [`skills/clawmem/SKILL.md`](skills/clawmem/SKILL.md)
- Runtime references: [`skills/clawmem/references/`](skills/clawmem/references/)
- LoCoMo evaluation harness: [`scripts/eval/`](scripts/eval/)
- Setup/bootstrap guide: the website `SKILL.md`
- Skill-driven redesign: [`docs/skill-driven-redesign.md`](docs/skill-driven-redesign.md)

That bundled skill covers:
- recall and save behavior
- schema discipline and answerable retention
- repo-scoped shared-memory routing
- live org/team membership and repo-grant aware team workflows
- repair and verification guidance
- raw `gh` / `gh api` / `curl` flows

The LoCoMo harness is the benchmark companion to the runtime plugin. It
provisions GitHub-compatible agents/repos, writes normal `type:memory` issues,
recalls only memory issues, runs answer/judge batches, and classifies failures
into retention, recall, and answer stages.

---

## Config Reference

Minimal config (after auto-provisioning):

```json5
{
  plugins: {
    entries: {
      clawmem: {
        enabled: true,
        config: {
          baseUrl: "https://git.clawmem.ai/api/v3",
          authScheme: "token",
          agents: {
            main: {
              baseUrl: "https://git.clawmem.ai/api/v3",
              defaultRepo: "owner/main-memory",
              token: "<token>",
              authScheme: "token"
            }
          }
        }
      }
    }
  }
}
```

Full config with all options:

```json5
{
  plugins: {
    entries: {
      clawmem: {
        enabled: true,
        config: {
          baseUrl: "https://git.clawmem.ai/api/v3",
          authScheme: "token",
          agents: {
            main: {
              baseUrl: "https://git.clawmem.ai/api/v3",
              defaultRepo: "owner/main-memory",
              token: "<token>",
              authScheme: "token"
            },
            coder: {
              defaultRepo: "owner/coder-memory",
              token: "<token>"
            }
          },
          summaryWaitTimeoutMs: 120000,
          memoryAutoRecallLimit: 3,
          memoryAutoRecallStrategy: "query-planner",
          memoryAutoRecallPlannerVariantLimit: 6,
          apiRequestRetries: 3,
          transcriptCommentBatchSize: 1,
          conversationSummaryMode: "llm"
        }
      }
    }
  }
}
```

---

## Notes

- Conversation comments exclude tool calls, tool results, system messages, and heartbeat noise.
- By default, one normalized user/assistant message maps to one issue comment. `transcriptCommentBatchSize` exists only for explicit bulk/evaluation runs.
- `conversationSummaryMode: "placeholder"` skips LLM summary/title generation for bulk or eval runs; keep the default `"llm"` for normal use.
- Comment writes use stable hidden message markers for retry checks. If mirroring falls behind, finalization waits and `clawmem_status` surfaces the repair error.
- Each `agent_end` mirrors conversation comments only; no plugin-owned memory extraction runs after turns.
- Finalization generates only the final conversation issue summary/title.
- Summary failures do not block finalization; the mirrored transcript remains the durable source of truth for manual follow-up.
- Memory search and auto-recall only return open `type:memory` issues. Closed memory issues are treated as stale.
- ClawMem automatically injects a small set of relevant memories before each turn using the agent's default repo and the backend recall API. Auto-recall is best-effort and quietly skips injection when backend recall is unavailable.
- `memoryAutoRecallStrategy: "query-planner"` is the default. It runs the full query plus focused compact/core/surface/literal/entity variants concurrently, with duplicate variants removed. `memoryAutoRecallPlannerVariantLimit` defaults to 6 for recall quality; lower it toward 3 for latency-sensitive deployments that only want full, compact, and core query variants. `"single"` forces one backend search; `"literal-repair"` keeps the normal full-query order, but for obvious date/count/name questions it may reserve one low-rank slot for a compact lexical repair hit.
- `apiRequestRetries` retries transient GitHub-compatible read/search failures such as 429, 5xx, and dropped connections. Write requests are not blindly retried.
- Normal recall is memory-first: `type:conversation` issues are provenance, audit trail, and rebuild input, not the default serving layer. Important transcript details should be distilled into answerable `type:memory` issues.
- `valid_from` / `valid_to` describe memory validity. Event dates and relative-date conversions that matter for answering belong in the visible `## Memory` text.
- Retention should include literal anchor ledgers when needed: dates, durations, quantities, exact item names, and first/last/current/planned facts belong in visible memory text, not only in transcript provenance.
- Retention should also make supported inferences answer-shaped: likely/counterfactual/status/suitability memories need the likely answer, basis, and uncertainty boundary in visible text.
- Always-on ClawMem prompt guidance requires the dedicated memory prompt-registration API.
- The plugin exposes `clawmem_status`, `clawmem_sync`, and `clawmem_maintain` only.
- Route resolution is now: agent identity supplies credentials, `defaultRepo` is the default memory space, and explicit GitHub-native operations may override repo per operation.
- Memory issues no longer use `session:*` labels. Session linkage remains a conversation concern, not part of the durable memory schema.
- Conversation lifecycle is stored in native issue state (`open` while live, `closed` after finalize); memory lifecycle uses native issue state too (`open` active, `closed` stale).
- Memory issue bodies should use visible GitHub Flavored Markdown plus a minimal hidden `<!-- clawmem ... -->` metadata block.
