# Skill-Driven ClawMem Redesign

## 1. Thesis

ClawMem should be redesigned around a different memory boundary than most agent
memory systems.

Most memory systems place memory intelligence on the server:

- the client sends messages or a narrow set of memory tool calls
- the server extracts, merges, indexes, and retrieves memories
- the client receives pre-digested context

ClawMem should keep the opposite boundary:

- the server is a GitHub-compatible storage and collaboration backend
- the user's agent performs memory judgment on the client
- the bundled `clawmem` skill is the primary memory runtime
- `gh` and `gh api` are the default storage interface
- the OpenClaw plugin is the local runtime layer for activation, identity,
  transcript mirroring, prompt/context injection, and automation triggers

This is a vNext design, not a compatibility plan. The new plugin does not need
to preserve the current broad tool surface or current finalize-time memory
pipeline. The existing codebase can donate useful parts, but the target product
should be designed boldly around the new boundary.

## 2. North Star

The deeper goal is not merely to store memories on a GitHub-compatible backend.
GitHub is one of the strongest artifacts of human collaboration: issues,
comments, labels, pull requests, repositories, organizations, teams, ownership,
review, and history form a shared operating language for long-running work.

ClawMem should let agents use that language directly. An agent should learn to
use ClawMem the way a skilled human uses GitHub:

- search before acting
- inspect history before deciding what is true
- update the canonical issue instead of creating duplicates
- close stale records with a reason
- link related records
- respect repo, org, team, and collaborator boundaries
- leave an auditable trail for the next collaborator

The goal is an agent that participates in GitHub-shaped collaboration as
naturally as a human teammate.

## 3. Lessons From Other Memory Systems

ClawMem should borrow memory concepts from modern systems without copying their
server-centric architecture.

- MemOS: memory has lifecycle, reader, feedback, activation memory, plaintext
  memory, and scheduler-like management.
- Hindsight: durable memory should distinguish raw facts from observations and
  higher level mental models.
- Mem0: writes should be explicit decisions: `ADD`, `UPDATE`, `DELETE`, or
  `NONE`; contradiction handling is part of memory storage.
- Letta: a small amount of core memory can be always visible; for ClawMem vNext
  this should be handled as compact profile/context loading, not a
  `recall:pinned` label.
- Graphiti: temporal validity matters; the system should know what was true at
  a specific time.
- Cognee: ingestion can transform documents and conversations into richer
  derived knowledge.
- Supermemory: memory should support user profiles, project scopes, and
  cross-client continuity.
- LangMem and LlamaIndex: useful systems combine hot-path memory actions,
  background managers, memory blocks, and token-budget-aware assembly.
- Elliot Chen's 2026-04-28 X article on OpenClaw and EverMind: useful agent
  memory is layered, stable across sessions, and separated from skills;
  procedural memory is an execution asset rather than just another text note;
  high-value memory should capture local, private, or team-specific knowledge
  that pretraining cannot already provide.

For ClawMem, these become client-side skill workflows, labels, issue bodies,
and automation scripts. The server remains the durable record system.

## 4. Architectural Boundaries

### Server

The server remains storage-first.

Responsibilities:

- host GitHub-compatible repositories, issues, comments, labels, orgs, teams,
  collaborators, and search endpoints
- provision agent identities and default repositories
- enforce authentication and collaboration permissions
- keep issue state and comments durable
- provide normal GitHub-compatible search and issue APIs

Non-responsibilities:

- no required LLM memory extraction
- no required server-side embedding pipeline
- no server-owned consolidation logic
- no opaque memory state outside repository objects

### Plugin

The plugin becomes a concise local runtime, not a large memory API.

Responsibilities:

- bootstrap and persist per-agent credentials
- configure `gh`/`gh api` access for the active agent route
- register always-on prompt guidance that activates the bundled skill
- mirror every real user/assistant transcript into `type:conversation` issues
- inject compact memory context before turns when automation has enough signal
- trigger local memory maintenance workflows after turns and at session close
- expose a small number of operational tools when they make automation or
  debugging easier
- ship helper scripts and skill references

Non-responsibilities:

- no broad `memory_*` CRUD tool family
- no broad `collaboration_*` tool family
- no server-style memory service abstraction
- no hidden server-side memory decisions

### Skill

The skill becomes the agent-facing memory runtime.

Responsibilities:

- decide when memory is relevant
- choose personal, project, team, or org memory repos
- run recall through `gh`/`gh api` and local helpers
- synthesize retrieved issues into compact context
- decide whether a turn produced durable memory
- perform `ADD`, `UPDATE`, `DELETE`, or `NONE`
- handle feedback and contradiction repair
- manage profiles, temporal facts, skill-promotion notes, and reflection
  workflows
- operate org/team/repo collaboration through `gh api`

### Local Helpers

Local helpers are allowed and encouraged.

They should wrap repeated `gh`/`gh api` patterns, but they must not create a new
opaque storage layer. Any local cache or index is disposable and rebuildable
from repository state.

## 5. Plugin Surface

The tool surface does not need to be zero or one. It should be small and
operational, not a second memory API.

Recommended default tools:

- `clawmem_status`: show active agent id, memory host, default repo, mirror
  health, skill version, and `gh` auth health without leaking secrets.
- `clawmem_sync`: force transcript mirror flush/retry for the current session.
- `clawmem_maintain`: run local client-side memory maintenance now, using the
  skill workflow and `gh` commands.

Avoid tools such as:

- `memory_store`
- `memory_update`
- `memory_forget`
- `collaboration_team_add`
- `collaboration_repo_transfer`

Those operations should be performed as GitHub-native actions through the skill
and `gh api`, because the point is to teach the agent to operate the shared
record system.

The plugin may still perform automatic recall/context injection without exposing
that behavior as a user-visible tool.

## 6. Mandatory Transcript Mirror

Transcript mirroring is mandatory when the plugin is enabled.

The conversation issue is the raw episodic record. It is the source material
from which memories, profiles, reflections, corrections, and task state are
derived.

Rules:

- every real session gets one `type:conversation` issue
- each user/assistant message is mirrored as its own append-only comment
- tool chatter, tool results, system prompts, and heartbeat noise stay out of
  the human-readable transcript by default
- the issue body stores session metadata and a rolling or final summary
- durable memory issues link back to source conversation issues and comment ids
- mirror failures are retried and surfaced in `clawmem_status`
- finalization waits when the transcript mirror is incomplete
- memory maintenance should not run on a session until the transcript mirror is
  sufficiently current

Conversation issues are not optional audit logs. They are the GitHub-native
episodic memory layer.

## 7. Label Taxonomy

Labels should follow the classification patterns used by other memory systems,
but stay low-cardinality and GitHub-friendly.

Use labels only for routing, filtering, and shared vocabulary that benefits
from GitHub label search. Put source comments, exact timestamps, relationships,
review notes, and other high-cardinality data in the issue body.

Layering should exist, but not necessarily as `layer:*` labels. In ClawMem,
layers are represented by different GitHub-native record forms:

- raw episodic memory is the mandatory `type:conversation` transcript mirror
- durable semantic memory is `type:memory` plus a small `kind:*` vocabulary
- procedural memory should usually live as executable skills, repo docs, or
  runbooks, with `kind:skill` issues recording when to use, create, or update
  those artifacts
- profiles and preferences are compact semantic models, not raw logs
- multimodal traces are source artifacts linked from conversation issues or
  memory issues, not a default memory kind

### Object Type

- `type:conversation`
- `type:memory`

`type:*` is the right top-level discriminator because it says exactly what the
GitHub issue is. It is familiar to human GitHub users and simple for agents to
filter.

`type:conversation` is the mandatory transcript mirror. In memory-system terms,
it is the raw episodic source material for later memory, profile, and
reflection work.

`type:memory` is the normal durable memory record.

### Memory Kind

`kind:*` labels should be few, mutually distinguishable, and useful for recall
or maintenance. They are record roles for GitHub-native memory maintenance, not
a full cognitive taxonomy.

Most memory systems use broad memory classes such as semantic, episodic, and
procedural memory. ClawMem already stores raw episodic memory as
`type:conversation`, and agent procedural memory should usually become skills.
The remaining `kind:*` labels mostly divide semantic memory only when the
distinction changes how agents retrieve, update, or maintain the record.

Default kinds:

| Label | Meaning | Cognitive bucket |
| --- | --- | --- |
| `kind:fact` | Stable declarative truth about a user, project, system, or world state | Semantic memory |
| `kind:preference` | A person's or team's preferred style, default, taste, or recurring choice | Semantic/social memory |
| `kind:convention` | Standing agreement, rule, policy, or norm that should govern future behavior | Semantic/social memory |
| `kind:decision` | A choice that has been made and should guide future work | Semantic/commitment memory |
| `kind:task` | Ongoing or future work that should remain active until resolved | Prospective memory |
| `kind:skill` | Knowledge about when and how an agent should use, create, or update a skill/capability | Agent procedural memory |
| `kind:lesson` | Correction, mistake, postmortem, or rule learned from experience | Episodic-to-semantic learning |
| `kind:profile` | Compact model of a person, project, team, repo, or agent | Semantic/social model |
| `kind:insight` | Synthesized pattern, interpretation, hypothesis, or mental model | Reflective semantic memory |

Why split semantic memory at all:

- `preference` affects defaults and tone.
- `convention` acts like a standing rule.
- `decision` records a commitment and often supersedes alternatives.
- `profile` is compact context loaded as a model of an entity.
- `insight` is synthesized and should be reviewed more carefully than a direct
  fact.

If a semantic subtype does not change retrieval or maintenance behavior, it
should be written as `kind:fact` plus `topic:*` or plain Markdown text, not a new
kind label.

Guidelines:

- use `kind:fact` for neutral truths, including constraints that are simply true
- use `kind:convention` when the memory is an agreed rule, policy, or norm that
  should govern future behavior
- use `kind:decision` when people or agents deliberately chose something
- use `kind:preference` when the memory is about how someone likes work to be
  done
- use `kind:skill` for agent procedural knowledge: when to invoke a bundled
  skill, when a learned workflow should be promoted into a skill, what a skill
  is good for, or what constraints apply to it
- use `kind:lesson` when the memory exists because something went wrong or was
  corrected
- use `kind:profile` for compressed context that represents an entity over time
- use `kind:insight` for synthesized observations or mental models that are not
  direct facts from one source
- use `kind:insight` sparingly; if the memory can be stated as a direct truth,
  prefer `kind:fact`, and if it came from a correction or failure, prefer
  `kind:lesson`

Episodic memory is not a `kind:*` label. Raw episodes are `type:conversation`
issues. If an event from an episode becomes durable, extract the reusable part
as one of the kinds above.

Repeatable workflows should usually be promoted into skills, repo docs, or
runbooks instead of living forever as memory issues. A `kind:skill` memory can
remember that such a skill exists, should be used, or needs to be created or
updated.

Executable procedure belongs in the skill or runbook itself. The memory issue
is the GitHub-native trail around that procedure: why it exists, when to invoke
it, what changed, and which conversations or failures caused the update.

### Topics

Use `topic:*` sparingly. Topics are shared vocabulary, not free-form keywords.
Prefer existing topic labels before creating new ones.

## 8. Repository And Issue State

Repositories and GitHub issue state carry structure that should not be repeated
as labels.

Scope is represented by the memory repo, organization, team access, and explicit
repo selection.

Lifecycle is represented by issue state:

- open `type:memory` issues are active memories
- closed `type:memory` issues are inactive, stale, superseded, or archived

The exact inactive reason belongs in the closing comment and, when useful, the
visible issue body. Uncertain observations stay in the conversation record or
maintenance logs until the agent has enough support to write a durable memory.

## 9. Memory Issue Body

Memory issue bodies should be both machine-readable enough for agents and
pleasant for humans to review in a GitHub UI.

GitHub issue and comment bodies are GitHub Flavored Markdown. ClawMem should use
plain Markdown as the primary format, because that is what GitHub renders and
what humans already understand. Machine-readable metadata should be limited and
kept in a hidden HTML comment so the visible issue remains clean.

Recommended body shape:

```markdown
## Memory

ClawMem should move memory intelligence into the bundled skill. The server
should remain GitHub-compatible storage, while the plugin handles local runtime
automation and mandatory transcript mirroring.

## Relations

- Source: #123
- Supersedes: #88
- Related: #91

## Notes

This replaces the older broad plugin-tool direction.

<!-- clawmem
schema_version: clawmem/v2
valid_from: 2026-04-24
valid_to:
-->
```

Design notes:

- visible Markdown is the canonical human-facing memory record
- GitHub issue references such as `#123` and `owner/repo#123` create clickable
  links and backlinks in the GitHub UI
- relation sections should use native GitHub references instead of duplicating
  relation arrays in hidden metadata
- the hidden `<!-- clawmem ... -->` block is only for stable metadata that
  GitHub does not model directly, starting with temporal validity
- `## Memory` is the canonical human-readable fact
- `## Relations` records source and related issue references
- `## Evidence` is optional and should only be added for synthesized, uncertain,
  or multi-source memories where a short justification helps human review
- `## Notes` is optional and can hold caveats or review comments
- comments on the issue are used for later discussion, corrections, and
  maintenance history
- labels carry `type:*`, `kind:*`, and `topic:*`; issue state carries active
  versus inactive lifecycle
- source conversation references make each memory auditable, repairable, and
  rebuildable, but normal online recall should answer from `type:memory`
  records rather than reopening raw transcript text
- event dates and useful relative-date conversions belong in `## Memory`;
  `valid_from` and `valid_to` describe the validity of the memory statement
- literal anchor ledgers are allowed inside `## Memory` for dense short-answer
  facts such as dates, months, durations, quantities, exact item names, and
  first/last/current/planned facts; they are usually `kind:fact`, not a new
  `kind:*` label

## 10. GitHub-Native Relations

ClawMem should use the same relationship mechanics that make GitHub issues
pleasant for humans:

- write references such as `#123` or `owner/repo#123` in the visible Markdown
  body or comments
- keep `Source`, `Supersedes`, and `Related` sections as plain Markdown lists
- use issue dependencies for task-like memories that block or are blocked by
  other task-like memories
- use sub-issues only when a real hierarchy helps humans navigate the memory
  repo

Responsibility split:

- The plugin and skill write normal GitHub-style references in Markdown.
- The GitHub-compatible backend is responsible for recognizing those references
  when issues or comments are created or edited, storing reference edges, and
  emitting timeline/backlink events on the mentioned issues.
- The frontend renders the Markdown links and displays the backlink, dependency,
  or sub-issue relationships exposed by the backend.

In other words, ClawMem should not invent relation labels or maintain a separate
relation table in memory issue bodies. It should rely on GitHub-compatible
reference semantics: write `#123`, let the backend index the edge, and let the
UI show the relationship.

## 11. Automated Workflows

The workflow should be as automatic as possible while keeping intelligence on
the client. Automatic does not mean heavy work on every turn. The hot path must
stay small: mirror the transcript, use cached or cheap context when available,
and enqueue heavier recall or retention work in the background.

Performance budget:

- transcript mirroring is mandatory but incremental
- pre-turn recall should have a short timeout and must never block the user turn
  for long
- post-turn retention should usually run asynchronously after the assistant
  response
- expensive semantic search, reflection, profile refresh, and dedupe should be
  batched, debounced, or triggered by clear signals
- local sidecar indexes may accelerate recall, but GitHub issues remain the
  source of truth

### Pre-Turn Recall

Before a real user turn reaches the model, the plugin may assemble memory
context when the prompt or session state suggests memory is likely to help:

1. plugin ensures transcript mirror state is current enough
2. plugin resolves active agent route and default memory spaces
3. plugin first checks cached profile/context from recent maintenance work
4. local recall helper runs focused `gh`/`gh api` searches only when the cache is
   missing, stale, or the turn has memory-sensitive signals
5. helper expands through related and supersession links only within a tight
   budget
6. helper filters temporal facts using `valid_from` and `valid_to`
7. plugin injects a compact context block with source issue ids if recall
   finishes within budget

The model should usually receive synthesized memory, not raw issue dumps.
If recall misses the budget, the turn proceeds without injected memory and a
background maintenance task can refresh context for the next turn.

Conversation issues are not a default fallback recall corpus. They are the raw
source of truth for audit, repair, and re-retention. If a transcript detail is
important enough to answer future questions, the retention helper should write
or update a `type:memory` issue so the serving layer remains memory-first.

### Post-Turn Retention

After each assistant turn, the plugin does only the mandatory mirror work. Any
durable retention pass is a skill/agent workflow, not plugin-owned runtime
state:

1. plugin mirrors the latest transcript comments
2. skill/agent workflow reads a cheap retention hint emitted by the active agent
   or falls back to conservative scheduling
3. if no durable signal is found, the workflow records nothing and stops
4. if there is a durable signal, the workflow runs local retention work
5. retention helper extracts answerable facts, decisions, tasks, skill updates,
   profiles, insights, and feedback
6. helper normalizes event dates when source dates make relative time
   resolvable, keeping the visible `## Memory` self-contained
7. helper searches existing memory issues before writing
8. helper chooses `ADD`, `UPDATE`, `DELETE`, or `NONE`
9. helper applies the change with `gh`/`gh api`
10. helper links source comments and related records
11. workflow logs any retention failure in the relevant issue/comment or
    external eval harness; `clawmem_status` remains focused on mirror and
    summary health

This is automatic client-side memory sedimentation. The server stores the
result, but the local agent workflow decides what memory means. The plugin
should not carry candidate memory state or pretend that retention is complete.

The trigger should not be plain text matching. The best default is to have the
active agent emit a tiny structured retention hint as part of its normal turn,
using the same model call that already produced the answer. A skill,
automation, or eval harness can read that hint from turn metadata or a hidden
channel, then decide whether to run retention. If no hint is available, that
workflow should schedule conservatively based on session state, turn size, and
recent maintenance cadence instead of trying to infer durable meaning from
brittle regexes.

Retention hint contract:

```json
{
  "needsRetention": true,
  "reasons": ["decision", "convention"],
  "targets": [
    {
      "kind": "decision",
      "summary": "ClawMem vNext should use active-agent retention hints instead of regex trigger matching.",
      "action": "add"
    }
  ]
}
```

Fields:

- `needsRetention`: boolean. `true` means the turn likely produced durable
  memory work; `false` means no retention job is needed.
- `reasons`: zero or more coarse trigger reasons. Allowed values should map to
  the default memory kinds where possible: `fact`, `preference`, `convention`,
  `decision`, `task`, `skill`, `lesson`, `profile`, `insight`, plus `feedback`
  for correction/repair turns.
- `targets`: optional compact hints for the retention helper. Each target may
  include `kind`, `summary`, and `action`.
- `action`: one of `add`, `update`, `delete`, or `none`. This is a hint, not
  the final write decision; the retention helper must still inspect existing
  memory issues before writing. Omit `action` when unsure.

Rules:

- the hint is not user-facing copy
- the hint must not include secrets, tool outputs, long logs, or full memory
  bodies
- the active agent should omit `targets` when unsure and set `needsRetention`
  based on durable memory value, not on whether it personally wants to remember
  the turn
- durable memory value should be biased toward local alpha: facts, preferences,
  procedures, lessons, and decisions that are specific to this person, team,
  repo, or environment and would not already be obvious from public model
  knowledge
- the plugin may ignore malformed hints and fall back to conservative scheduling
- the retention helper owns final `ADD`, `UPDATE`, `DELETE`, or `NONE`
  decisions

This keeps the hot path free of an extra LLM call while still relying on the
agent's semantic understanding rather than simple text matching. Ambiguous
turns should become low-priority asynchronous review jobs.

### Training And Evaluation Readiness

ClawMem should not treat memory only as inference-time recall. A durable,
GitHub-native trail of transcripts, decisions, corrections, supersessions, and
skill updates can become high-quality evaluation or post-training material in
the future.

That future use has to remain explicit and auditable:

- transcript mirrors preserve the raw interaction trajectory
- memory issues preserve distilled reusable knowledge with source references
- feedback repair preserves what was wrong, what replaced it, and why
- skill updates preserve procedural learning separately from factual memory
- exports for training or evaluation must be opt-in, privacy-aware, and
  reconstructable from repository state rather than hidden server data

The product value is not just remembering more. It is producing cleaner
experience data: what worked, what failed, what changed, and which local
procedure made the agent better next time.

### Feedback Repair

When the user corrects a memory or says the agent remembered something wrong:

1. mark the source kind as feedback in the corrected memory metadata
2. search likely wrong memories
3. inspect exact issues and source conversations
4. close, supersede, or relabel incorrect records
5. create or update the corrected canonical memory
6. link old and new records
7. briefly tell the user what changed

Feedback repair should run immediately, not wait for session finalization.

### Reflection And Profiles

Reflection should be automated but bounded.

Run reflection when:

- a session closes with enough durable material
- many related memories accumulate under one topic
- a project profile is stale
- feedback reveals recurring contradictions
- the user explicitly asks for consolidation

Reflection outputs are ordinary `type:memory` records, usually `kind:insight`
or `kind:profile`.

Reflections must link back to source memories and conversations.

### Import And Ingestion

Document and repository ingestion should also be client-side.

The skill may use local tools to parse files, summarize them, and write memory
issues through `gh`. The server should not need to understand the source file
format.

Multimodal sources should enter as episodic source material before they become
semantic memory. Screenshots, images, audio transcripts, video summaries, or
device/context traces should be attached to or linked from conversation issues,
then cited by derived memory issues when they produce a reusable fact,
preference, lesson, profile update, or skill update. Modality is provenance,
not a default `kind:*` label.

## 12. Retrieval Strategy

Skill-driven does not mean primitive retrieval.

The retrieval stack can become stronger while keeping GitHub issues as the
source of truth:

- label filters for exact routing
- GitHub issue search for keyword recall
- agent-generated multi-query recall for semantic breadth
- profile and stable context loading
- hidden metadata for temporal validity
- issue references for graph expansion
- temporal filtering with `valid_from` and `valid_to`
- local sidecar indexes for speed and semantic reranking
- final agent synthesis under a token budget

Optional local sidecar artifacts:

```text
.clawmem/index.sqlite
.clawmem/embeddings.sqlite
.clawmem/graph.json
```

Sidecar indexes must be disposable and reproducible from issues.

## 13. Write Strategy

Memory writes should feel like careful GitHub maintenance.

`ADD`, `UPDATE`, `DELETE`, and `NONE` are write decisions, not user-facing tool
names. They are the agent's internal classification for what should happen after
it compares proposed memory content with existing GitHub records.

- `ADD`: create a new `type:memory` issue because the proposed content is
  durable and no existing canonical memory already represents it.
- `UPDATE`: edit an existing memory issue because the new information refines,
  corrects, or advances the same canonical fact, preference, task, skill note,
  or profile.
- `DELETE`: retire a memory from normal recall because it is false, stale,
  superseded, or harmful to reuse. In GitHub terms this means close the issue,
  leave a closing comment, and link the replacement in `superseded_by` if one
  exists. It is not a hard delete by default.
- `NONE`: do not write anything because the turn produced no durable memory, the
  support is too weak, or the content is already represented accurately.

Default write algorithm:

1. generate one proposed record per atomic durable fact, or one canonical record
   for a set-like memory that should be maintained together
2. reject generic public knowledge unless it is tied to a local preference,
   decision, convention, environment, or failure
3. write `## Memory` so it can answer future questions without raw transcript
   expansion
4. run a literal anchor pass for dates, durations, quantities, exact names,
   and first/last/current/planned facts that narrative summaries often lose
5. normalize event dates and relative dates when the source date is known, while
   preserving the original relative phrase and source granularity
6. lint or audit high-value drafts for answer-complete exact-value coverage;
   for Locomo-style runs, run the corpus gate by `source_id` after each
   conversation/repo retention pass
7. classify kind, topics, source references, and uncertainty
8. search for duplicates, conflicts, and related records
9. decide `ADD`, `UPDATE`, `DELETE`, or `NONE`
10. preserve one canonical issue per living subject/property when practical
11. add source conversation and comment references
12. update labels and metadata together
13. add a comment when changing meaning or superseding another memory
14. close superseded or stale records with a reason
15. leave enough evidence for human review

The agent should behave like a maintainer of shared knowledge, not a key-value
store client.

## 14. OpenClaw Plugin Implementation Notes

The vNext design is still an OpenClaw plugin, so it must respect the agent loop.
The plugin sits on the critical path for prompt construction, transcript
updates, and session lifecycle events.

### Hook Placement

- Use memory prompt registration, when available, for stable ClawMem guidance.
  Fallback prompt hooks should only inject concise guidance and dynamic context.
- Use `before_prompt_build` for budgeted dynamic recall. This path must be fast,
  bounded, and safe to skip.
- Use transcript update events and `agent_end` for incremental mirroring.
- Use `before_reset` and `session_end` to flush mirrors and enqueue maintenance,
  not to run expensive synchronous extraction.
- Allow bulk/evaluation routes to use placeholder conversation summaries while
  preserving transcript mirroring; durable memory quality should be measured
  from `type:memory` issues, not from conversation summary text.
- Use subagents only for bounded background work with idempotency keys and
  cleanup; do not let helper sessions become durable user-visible transcripts.

### Critical Path Budget

- Prompt construction must not wait on slow GitHub search, LLM extraction, or
  broad dedupe.
- Pre-turn recall should use cached context first, then a short-timeout recall
  attempt, then gracefully skip.
- Post-turn retention should be asynchronous by default.
- Reflection, profile refresh, and broad maintenance must be debounced and
  queued outside the immediate turn.

### Transcript Mirror Guarantees

- Mirroring is mandatory and should be the most reliable path in the plugin.
- Mirror writes must be incremental, idempotent, and resumable after restart.
- The plugin should store enough local state to know which messages were
  mirrored, which issue owns the session, and which retries are pending.
- Memory writes should link to mirrored conversation comments whenever possible.
- If the mirror is behind, retention should wait or record a retry rather than
  creating source-less memories.

### State, Concurrency, And Idempotency

- Use per-session queues for transcript writes.
- Use per-repo queues for issue writes that may race with each other.
- All maintenance jobs need idempotency keys based on session id, cursor, repo,
  and job type.
- A plugin restart should never duplicate comments, duplicate memories, or lose
  pending maintenance state.
- Local sidecar indexes are caches only and must be rebuildable from issues.

### GitHub And `gh` Integration

- The plugin should provision credentials and make the active route easy for
  helper scripts to consume.
- `gh` should be the default operation path for skills and helpers, but the
  plugin should validate that auth, host, and repo configuration are healthy.
- Shell helpers must avoid leaking tokens into logs, prompts, issue bodies, or
  command output.
- All GitHub operations should be retry-aware and rate-limit-aware.

### Tool Surface

- Tools should be operational controls, not memory CRUD wrappers.
- Good tools report status, flush mirrors, or trigger maintenance.
- Mutating collaboration operations should remain GitHub-native skill actions
  through `gh api`, with explicit user approval for high-impact changes.

### Failure Semantics

- Mirror failures are high priority and visible in `clawmem_status`.
- Recall failures should be silent or low-noise unless the user explicitly asks
  for memory-backed accuracy.
- Retention failures belong to the skill/agent workflow or eval harness; they
  should not derail the user turn or appear as plugin-owned memory state.
- Maintenance should prefer "do nothing" over writing uncertain or unlinked
  memories.

### Compatibility With OpenClaw Versions

- New prompt registration APIs should be preferred.
- Older hook paths can be supported only as fallback implementation details.
- Version checks should be explicit and logged once, not rediscovered on every
  turn.

### Security And Prompt Hygiene

- Never mirror system prompts, tool results, tokens, or internal helper chatter
  into conversation issues by default.
- Sanitize recall queries so injected memory blocks, URLs, logs, and tool noise
  do not poison backend search.
- Treat issue bodies as untrusted input when injecting memory context back into
  the prompt.

### Observability

- `clawmem_status` should show mirror health, summary health, route health, and
  `gh` auth health.
- Logs should be concise and redact secrets.
- Failed skill/agent retention jobs should be inspectable in the relevant
  GitHub issue/comment or external eval harness, not in plugin-owned memory
  state.

## 15. Implementation Plan

### Phase 1: Define The New Contract

- finalize the vNext label taxonomy
- finalize the memory issue body format
- rewrite the bundled skill around GitHub-native workflows
- add helper scripts for route resolution, recall, retention, feedback repair,
  and label/body rendering

### Phase 2: Build The New Plugin

- keep or rewrite per-agent provisioning
- make transcript mirroring mandatory
- add mirror retry and health state
- register concise prompt guidance
- expose only operational tools such as `clawmem_status`, `clawmem_sync`, and
  `clawmem_maintain`
- remove the broad memory and collaboration tool families

### Phase 3: Automate Recall And Retention

- implement budgeted pre-turn recall helper invocation with cache fallback
- implement skill/agent-driven asynchronous post-turn retention
- add active-agent retention hints before retention workflows run
- add debounce/rate-limit controls for maintenance jobs
- make memory writes use `gh`/`gh api`
- surface maintenance errors clearly without blocking the user turn
- keep all durable results in GitHub-compatible issues

### Phase 4: Add Feedback, Lifecycle, And Reflection

- implement immediate feedback repair
- implement supersession and temporal validity handling
- implement profile refresh and reflection workflows
- add review queues for uncertain or high-impact changes

### Phase 5: Add Optional Local Indexes

- build local indexes from repo state
- add semantic reranking and graph expansion helpers
- keep indexes disposable
- verify that deleting the index never loses memory

## 16. Current Code To Reuse Or Replace

Useful pieces to reuse:

- per-agent route provisioning
- GitHub-compatible client pieces
- transcript normalization
- session state queues
- conversation mirroring concepts
- bundled skill packaging
- route export script

Pieces to replace:

- broad `memory_*` tool family
- broad `collaboration_*` tool family
- plugin-managed finalize-time memory extraction
- plugin-centric memory CRUD mental model
- flat YAML-only memory body format

## 17. Open Questions

- Should operational tools be exactly `clawmem_status`, `clawmem_sync`, and
  `clawmem_maintain`, or should `clawmem_maintain` be split into recall,
  retention, and repair modes?
- Should local automation run as plugin-managed subprocesses, OpenClaw
  subagents, or both?
- Which concrete future workflow would justify adding more hidden metadata
  beyond temporal validity?
- Where should local sidecar indexes live: memory repo checkout, OpenClaw state
  dir, or cache dir?

## 18. Design Principle

ClawMem should not compete by becoming a heavier memory server.

It should compete by making memory legible: every fact, correction, profile,
reflection, task, and team decision should be stored as repository-native state
that an agent can reason over and a human can inspect.

The plugin wakes the memory system up, mirrors the conversation, and runs local
automation. The skill teaches the agent how to think with GitHub-native memory.
The server keeps the record.
