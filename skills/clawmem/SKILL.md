---
name: clawmem
description: "GitHub-native durable memory workflows for the ClawMem OpenClaw plugin. Use when ClawMem is installed and you need to recall, create, update, close, link, or maintain repo-backed memory issues; reason about transcript mirrors or OKF wiki compiled knowledge pages; choose the right memory repo; or operate ClawMem through GitHub-compatible gh / gh api commands."
---

# ClawMem

ClawMem is the active long-term memory system for this OpenClaw installation.
Use it the way a careful human uses GitHub:

- issues are records
- comments are history
- labels are schema
- visible issue references are relations
- issue state is lifecycle

The core rule:

> Issue memory carries atomic durable memory. OKF wiki pages carry compiled,
> reviewable knowledge.

Wiki context can restore background, explain why facts fit together, and boost
recall. It is the preferred orientation layer for broad or recurring questions,
but it is not allowed to override open memory issues. When wiki prose conflicts
with an open memory issue, trust the issue and repair the wiki.

The plugin intentionally exposes a small tool surface:

- `clawmem_status`
- `clawmem_sync`
- `clawmem_maintain`

Do not look for `memory_store`, `memory_update`, `memory_forget`, or broad
collaboration wrapper tools. Durable memory work is skill-driven through
GitHub-compatible `gh` / `gh api` operations.

## Turn Loop

On each user turn:

1. Ask whether prior memory could materially improve the answer.
2. Use auto-injected ClawMem context when it is enough.
3. If explicit recall or writing is needed, resolve the route, list accessible
   repos, choose the right repo, and list labels for that repo.
4. Search OKF wiki pages early for page-level synthesis on broad or recurring
   topics, and search direct `type:memory` issues in parallel so orphan or fresh
   memories are not missed.
5. Answer from open memory issues and cited OKF page claims when available. Use
   uncited wiki prose as background, not as the sole source of truth.
6. After answering, ask whether the turn produced durable local alpha.
7. If yes, create, update, close, or deliberately skip memory issues through
   GitHub operations.
8. If a fact, decision, workflow, or profile should be fast to recover or would
   otherwise require query-time synthesis from fragments, update the relevant
   OKF wiki page after the issue memory exists.

Local alpha means knowledge specific to this person, team, repo, project,
environment, decision, failure, preference, or procedure. Do not store generic
public knowledge unless it is tied to a local convention or decision.

## Scope And Routing

Before any explicit recall, store, update, close, or schema-sensitive operation:

```sh
eval "$(python3 scripts/clawmem_exports.py)"
```

This exports `CLAWMEM_AGENT_ID`, `CLAWMEM_BASE_URL`,
`CLAWMEM_EXT_BASE_URL`, `CLAWMEM_HOST`, `CLAWMEM_DEFAULT_REPO`,
`CLAWMEM_REPO`, and `CLAWMEM_TOKEN`.

Never print, store, paste, log, or commit the token.

Then:

- list accessible repos and choose the right owner/repo
- prefer explicit user-, team-, or project-selected repos
- use the configured default repo only when it is clearly the intended scope
- list labels in the chosen repo before recall or write
- create missing required labels before writing

Scope is represented by repo/org/team boundaries, not by `scope:*` labels. If
multiple repos are plausible and the choice materially affects the answer or
write, ask the user.

For exact commands, read [references/github-ops.md](references/github-ops.md).

## Recall

Recall only open durable memories by default:

- search the selected repo
- require `type:memory`
- inspect exact issues before relying on them
- keep `type:conversation` issues out of normal online recall

Conversation issues are mandatory transcript mirrors: provenance, audit trail,
and rebuild input. If answer-bearing information exists only in a conversation
issue, repair or create the durable memory issue instead of depending on raw
transcript recall.

OKF wiki recall is page-first orientation, not a gate:

- use relevant OKF pages to recover current state, history, sources, status,
  update conditions, and related concepts
- search issue memories directly even when wiki search is available
- follow visible `#123` / `owner/repo#123` refs to in-scope `type:memory` issues
- treat wiki-referenced memories as boosted candidates, not the only candidates
- verify unsupported wiki prose against memory issues when it would materially
  affect the answer

For debugging recall quality, use backend search observability with
`debug=true`. Do not treat snippets or matched fields alone as proof of final
ranking contribution. Page indexes, embedding indexes, BM25, or wiki search are
acceleration layers; the reviewable knowledge lives in issues and OKF pages.

For exact recall, OKF wiki, and debug commands, read
[references/github-ops.md](references/github-ops.md).

## Retention

Choose one write decision:

- `ADD`: create a new memory issue
- `UPDATE`: edit the existing canonical issue
- `DELETE`: close a false, stale, superseded, or harmful issue with a reason
- `NONE`: do not write

Before writing, search for duplicates and conflicts. Prefer one canonical open
issue per living subject/property when practical. Update canonical set or profile
memories instead of scattering fragments across many near-duplicate issues.

Write durable information to issue memory first. Promote to OKF wiki only when the
memory is high-importance, high-frequency, cross-task, current project/user/topic
background, or useful for fast agent startup.

Use page-first retention for recurring synthesis. Do not leave future agents to
reconstruct stable answers from scattered fragments every time. If several
memory issues together establish a current status, causal chain, workflow,
profile, or long-lived decision, compile or update the OKF wiki page with the
current view, history, source memories, status, and update conditions.

Use answerable retention. `## Memory` must contain enough visible detail for a
future agent to search, answer, judge, and maintain the memory without reopening
raw transcript comments.

Preserve exact answer-bearing values when provided:

- names, places, organizations, dates, months, years, durations, quantities
- list items, relation targets, causes, stated reasons, and constraints
- event dates and original relative phrases when useful for review
- uncertainty boundaries for supported inferences

Do not store lossy summaries such as `Melanie has hobbies` when the source gave
`pottery, camping, painting, and swimming`.

Strong user corrections and validations are retention signals. Store the durable
lesson, convention, or skill trigger when the signal would change future agent
behavior. Do not save a play-by-play of the session; the transcript mirror
already does that.

For full schema, kinds, body format, and temporal rules, read
[references/schema.md](references/schema.md).

## Memory Body

Use GitHub Flavored Markdown. Minimal body shape:

```markdown
## Memory

The durable fact, preference, decision, task, lesson, profile note, insight, or
skill trigger. Include exact values and boundaries needed for future answers.

## Relations

- Source: #123
- Supersedes: #88

## Notes

Optional caveats or review notes.

<!-- clawmem
schema_version: clawmem/v2
valid_from: 2026-04-24
valid_to:
-->
```

Labels:

- always include `type:memory`
- choose one `kind:*` when useful
- use `topic:*` sparingly

Default kinds:

- `kind:fact`
- `kind:preference`
- `kind:convention`
- `kind:decision`
- `kind:task`
- `kind:skill`
- `kind:lesson`
- `kind:profile`
- `kind:insight`

Lifecycle is native issue state: open means active; closed means inactive,
stale, superseded, false, or archived. Put the inactive reason in the closing
comment.

## OKF Wiki Knowledge Pages

Wiki pages are OKF v0.1-style compiled knowledge pages for agents. They are the
human- and agent-readable artifact that turns scattered memory issues into
reviewable pages with current state, history, source references, status, update
conditions, and links to related concepts.

ClawMem uses four layers:

- raw source: `type:conversation` issues, tool outputs, documents, logs, and
  other provenance
- atomic memory: `type:memory` issues that preserve answerable durable facts,
  preferences, decisions, lessons, tasks, and profile notes
- compiled knowledge: OKF wiki concept pages that organize related memories into
  a page another human or agent can read directly
- index: wiki search, PageIndex, BM25, embeddings, or graph indexes that can be
  rebuilt from the issues and wiki pages

Do not treat the index as knowledge. Rebuild or discard indexes freely; repair
issues and OKF pages when the knowledge itself is wrong.

Treat a ClawMem wiki slug like `projects/clawmem` as the OKF concept document
`projects/clawmem.md`. Each non-index, non-log page should start with YAML
frontmatter. OKF requires only `type`, and recommends `title`, `description`,
`resource`, `tags`, and `timestamp`. Use `type: ClawMem Knowledge Page` unless a
more specific concept type is clearer.

Target Google OKF v0.1 (draft) until the upstream spec changes:
https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md

Recommended page families:

- `users/{user}`
- `projects/{project}`
- `topics/{topic}`
- `decisions/{area}`
- `workflows/{workflow}`

Avoid default `sessions/*` wiki pages. Conversation issues already mirror raw
episodes.

Wiki maintenance rules:

- create or update issue memory first
- update OKF wiki for important, frequently reused, cross-task, or synthesized
  context
- compile, do not copy every memory
- keep visible issue refs in the markdown body; do not rely on frontmatter-only refs
- if wiki is stale, repair the wiki rather than changing the answer source
- archive stale page content inside the page or move it to an archive page when
  history is useful; do not leave outdated current-state claims active

Concept page template:

```markdown
---
type: ClawMem Knowledge Page
title: Project: Example
description: Current cross-task compiled knowledge for the Example project.
resource: clawmem://wiki/projects/example
tags: [project, example]
timestamp: 2026-06-24T00:00:00Z
---

# Current State

The compiled current view. Keep this compact and answer-oriented.

# History

- Previous or deprecated states that still explain the current answer.

# Canonical Memories

- #123: Short statement of the memory and why it matters here.

# Status

- active
- Revisit when the user, project, workflow, owner, or underlying source changes.

# Related

- [Related concept](../topics/example)

# Open Questions

- Unknowns or stale areas to verify before relying on this context.

# Citations

[1] #123
```

Use `index` / `projects/index` slugs for OKF index pages that list nearby
concepts, and `log` / `projects/log` slugs for chronological maintenance notes.

## User Communication

Memory work should not be surprising:

- when memory materially shaped an answer, mention it briefly in the user's
  current language
- when a memory is created, updated, or closed, give a short confirmation
- store human-readable titles and bodies in the user's current language when
  creating new memories
- preserve an existing memory issue's language unless the user asks for a rewrite
- keep labels and structural markers such as `type:*`, `kind:*`, and `topic:*`
  fixed and machine-readable

Do not generate token-bearing console URLs unless the user explicitly asks for a
console link and the route token was read for this authenticated session.

## References

- For memory schema, kinds, body format, OKF wiki compiled knowledge pages, write decisions, and
  temporal rules, read [references/schema.md](references/schema.md).
- For concrete GitHub-compatible `gh` / `gh api` commands, read
  [references/github-ops.md](references/github-ops.md).
- For activation repair and route verification, read
  [references/repair.md](references/repair.md).
