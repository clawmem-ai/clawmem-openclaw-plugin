---
name: clawmem
description: "GitHub-native durable memory workflows for the ClawMem OpenClaw plugin. Use when ClawMem is installed and you need to recall, create, update, close, link, or maintain repo-backed memory issues; reason about transcript mirrors or OKF wiki compiled knowledge pages; choose private, project, team, or org memory repos; manage team memory topology, membership, repo grants, or lifecycle; or operate ClawMem through GitHub-compatible gh / gh api commands and AGS-specific gh ags commands."
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
GitHub-compatible `gh` / `gh api` operations, with `gh ags` used for AGS Wiki
extension APIs.

## Turn Loop

On each user turn:

1. Ask whether prior memory could materially improve the answer.
2. Use auto-injected ClawMem context when it is enough.
3. If explicit recall or writing is needed, resolve the route, list accessible
   repos, choose the right repo, and list labels for that repo. For team-scoped
   work, discover current org teams, memberships, and repo grants before routing.
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

For exact commands, read [references/operations.md](references/operations.md).

## Team Memory And Governance

Use GitHub-native state as ClawMem's team control plane. Org teams, memberships,
and repo grants determine actual access; open memory issues describe team scope,
responsibilities, conventions, and decisions; OKF wiki pages compile those
records for orientation. Do not create a second static team configuration or a
monolithic policy issue by default.

For team-scoped work:

- treat an auto-provisioned agent default repo as private unless it is explicitly
  configured as shared
- use an org-owned team memory repo for team knowledge and an optional org
  memory repo for organization-wide governance
- discover live team membership and repo grants instead of relying on a cached
  team list or naming convention
- route by task ownership and the narrowest audience that needs the memory; do
  not search every accessible team repo on every turn
- keep one canonical cross-team memory in the owning team's repo, or use a
  deliberately shared project repo when ownership is genuinely joint
- prefer archiving a team's semantic records and preserving its memory repo over
  deleting history

Team additions, membership changes, repo grants, renames, archives, and deletes
are runtime GitHub operations plus memory/wiki maintenance, not plugin code
changes. For discovery, routing, precedence, and lifecycle workflows, read
[references/team.md](references/team.md).

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
[references/operations.md](references/operations.md).

## Retention

Choose one write decision:

- `ADD`: create a new memory issue
- `UPDATE`: edit the existing canonical issue
- `DELETE`: close a false, stale, superseded, or harmful issue with a reason
- `NONE`: do not write

Before any issue or wiki write, read [references/schema.md](references/schema.md)
for the normative formats and [references/operations.md](references/operations.md)
for the exact operations. Search for duplicates and conflicts first. Prefer one
canonical open issue per living subject/property when practical. Update
canonical set or profile memories instead of scattering near-duplicates.

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

## Two-Layer Write Decision

ClawMem has two authored memory layers. Keep their responsibilities explicit:

1. Write each new durable fact, preference, decision, task, lesson, profile
   update, or skill trigger to a canonical open `type:memory` issue first.
2. Update an OKF wiki page only after the backing issue exists and the page adds
   reusable synthesis: current state, history, a causal chain, a workflow, a
   profile, a long-lived decision, or cross-task orientation.
3. Cite the backing memory issues with visible `#123` or `owner/repo#123`
   references in the wiki body.
4. If an open memory issue conflicts with wiki prose, answer from the issue and
   repair the wiki.

Do not promote every issue. If a page would only repeat one issue, keep the issue
as the durable record. Do not use conversation mirrors as the normal recall
layer, and do not treat search indexes as memory; they are provenance and
rebuildable acceleration layers respectively.

## OKF Wiki Write Checklist

When creating or updating a compiled knowledge page:

- use OKF YAML frontmatter with non-empty `type` and useful `title`,
  `description`, `resource`, `tags`, and `timestamp`
- write a compact `# Current State`, then include history, canonical memories,
  status, related concepts, open questions, and citations when they add value
- keep backing issue references visible in the markdown body, not only in
  frontmatter
- refresh `timestamp`, state the page status, and include an update condition
  for claims that can go stale
- link related wiki concepts with stable slug-relative paths
- compile the useful view instead of copying every source memory

Use `index` / `*/index` for nearby concept listings and `log` / `*/log` for
chronological maintenance notes. Avoid default `sessions/*` pages because
conversation issues already preserve episodes.

For the canonical OKF page template and page-family guidance, read
[references/schema.md](references/schema.md). For wiki search, fetch, create,
and update commands, read [references/operations.md](references/operations.md).

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
- For concrete GitHub-compatible `gh` / `gh api` and AGS-specific `gh ags`
  commands, read
  [references/operations.md](references/operations.md).
- For team memory, org/team/agent topology, team lifecycle changes, and
  team-aware recall/store routing, read [references/team.md](references/team.md).
- For activation repair and route verification, read
  [references/repair.md](references/repair.md).
