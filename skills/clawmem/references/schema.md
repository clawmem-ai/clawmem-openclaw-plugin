# ClawMem Memory Schema

This is the schema reference for ClawMem memory issues and OKF wiki compiled
knowledge pages.
Runtime workflow belongs in [../SKILL.md](../SKILL.md). Concrete commands belong
in [operations.md](operations.md).

## Contents

- [Records](#records)
- [Labels](#labels)
- [Default Kinds](#default-kinds)
- [Body Format](#body-format)
- [Answerable Text](#answerable-text)
- [Temporal Semantics](#temporal-semantics)
- [Write Decisions](#write-decisions)
- [OKF Wiki Compiled Knowledge Pages](#okf-wiki-compiled-knowledge-pages)
- [Page-First Retention](#page-first-retention)
- [Shared Memory Quality](#shared-memory-quality)

## Records

- `type:conversation`: mandatory transcript mirror and raw episodic source
- `type:memory`: durable distilled memory

Conversation issues are provenance, audit trail, and rebuild input. They are not
the normal online recall layer. If a transcript fact should affect future answers
or behavior, write it into a `type:memory` issue.

Wiki pages are OKF compiled knowledge pages. They summarize important current
context, explain how fragments fit together, and cite issue memories with
visible references.

## Labels

Required labels:

- `type:conversation`
- `type:memory`

Memory issue labels:

- always include `type:memory`
- choose one `kind:*` when useful
- use `topic:*` sparingly for stable retrieval anchors

Do not use `scope:*` labels by default. Scope is represented by repo/org/team
boundaries. Do not add lifecycle labels by default; issue state is lifecycle.

## Default Kinds

| Label | Use for |
| --- | --- |
| `kind:fact` | Stable declarative truth about a user, project, system, or world state |
| `kind:preference` | A person's or team's preferred style, default, taste, or recurring choice |
| `kind:convention` | Standing agreement, rule, policy, or norm |
| `kind:decision` | A choice that has been made and should guide future work |
| `kind:task` | Ongoing or future work that should remain active until resolved |
| `kind:skill` | When/how to use, create, or update a skill, doc, or runbook |
| `kind:lesson` | Correction, mistake, postmortem, or rule learned from experience |
| `kind:profile` | Compact model of a person, project, team, repo, or agent |
| `kind:insight` | Synthesized pattern, interpretation, hypothesis, or mental model |

Use `kind:insight` sparingly. If the memory is a direct truth, prefer
`kind:fact`; if it came from a correction or failure, prefer `kind:lesson`.

`kind:skill` issues should remember when a reusable procedure should be used,
created, or updated. Do not bury long executable workflows in memory issues; put
those in skills, repo docs, or runbooks.

## Body Format

Use GitHub Flavored Markdown:

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

The hidden metadata block is lifecycle metadata. Do not use it as a substitute
for answerable event details in `## Memory`.

Default metadata:

- `schema_version`: schema identifier
- `valid_from`: when the memory statement becomes valid for future use, when
  known
- `valid_to`: when the statement stops being valid, if known

Do not add `memory_id` by default; the GitHub issue number is the durable
human-facing identifier. Do not add `confidence` unless ClawMem has a concrete
confidence policy or review workflow that uses it. Do not add agent-only
authorship fields by default; GitHub records issue and comment authors.

## Answerable Text

`## Memory` must contain enough visible detail for future recall and answering
without reopening raw transcript comments.

Preserve:

- subject, fact, scope, condition, trigger, exception, and uncertainty boundary
- exact names, places, organizations, dates, months, years, durations, quantities
- list items, relation targets, causes, stated reasons, and constraints
- event date plus source date or original relative phrase when useful
- supported likely/counterfactual answer shape when the source supports it

Do not generalize away answer-bearing values. If the source says `Sweden`, do
not store only `home country`. If the source lists `pottery, camping, painting,
and swimming`, do not store only `hobbies`.

One memory may contain several details only when they support the same
subject-property, canonical set, event, decision, skill trigger, lesson, or
causal link. Otherwise split it.

Useful body shapes:

- `atomic fact`: one subject, one answer-bearing fact
- `canonical set`: current known set of activities, people, places, tools, pets,
  constraints, or preferences
- `profile capsule`: compact durable model of a person, team, repo, or project
- `temporal event`: event date, source date, and useful original relative phrase
- `literal anchor ledger`: scoped bullets for short exact values that would
  otherwise be lost
- `causal link`: cause, effect, and affected entity or decision
- `supported inference`: likely yes/no, preference, leaning, status,
  counterfactual answer, suitable option, or recommendation with basis and
  boundary visible

Literal anchor ledgers are usually `kind:fact`; do not create a new `kind:*`
label for anchors.

## Temporal Semantics

`valid_from` and `valid_to` describe the validity of the memory statement, not
necessarily the event date.

Rules:

- event dates belong in visible `## Memory` text
- convert relative dates only when the source date is known
- preserve the original relative phrase when it may matter for review
- preserve temporal granularity
- do not invent exact dates from vague source timestamps
- use `as of <source_date>` for ongoing states when event timing is not exact
- do not rely on `valid_from` to answer event-date questions

Examples:

```markdown
## Memory

On 2023-05-07, Caroline went to the LGBTQ support group. This was described as
"yesterday" in the 2023-05-08 conversation.
```

```markdown
## Memory

As of 2023-08-01, Jolene uses video games, Susie, and pets to cope with stress.
```

## Write Decisions

- `ADD`: create a new `type:memory` issue
- `UPDATE`: edit the existing canonical issue
- `DELETE`: close the stale, false, superseded, or harmful issue with a reason
- `NONE`: do not write

If support is uncertain or not durable enough, choose `NONE` and ask the user
when the uncertainty matters. Do not create candidate issues or candidate labels.

Prefer `UPDATE` over `ADD` when the new information:

- refines or corrects the same subject/property
- updates a canonical set
- supersedes an older decision or status
- turns scattered fragments into a more answerable canonical memory

Close stale records instead of leaving conflicting open memories active.

## OKF Wiki Compiled Knowledge Pages

Issue memory is the atomic source of truth. Wiki is the compiled knowledge
layer. This is the "first make a page, then retrieve" model: do not rely on
query-time retrieval to repeatedly reassemble stable knowledge from scattered
chunks.

ClawMem uses four layers:

| Layer | ClawMem form | Role |
| --- | --- | --- |
| Raw source | `type:conversation` issues, tool outputs, docs, logs | Immutable or minimally changed provenance |
| Atomic memory | `type:memory` issues | Answerable durable facts, preferences, decisions, lessons, tasks, and profile notes |
| Compiled knowledge | OKF wiki concept pages | Reviewable pages that synthesize current state, history, sources, status, and related concepts |
| Index | wiki search, PageIndex, BM25, embeddings, graph indexes | Rebuildable acceleration layer, never knowledge ground truth |

Use wiki pages for context that is:

- high-importance
- high-frequency
- cross-task
- current project/user/topic/workflow background
- useful for fast agent startup

Recommended page families:

- `users/{user}`
- `projects/{project}`
- `topics/{topic}`
- `decisions/{area}`
- `workflows/{workflow}`

Avoid default `sessions/*` wiki pages; conversation issues already mirror raw
episodes.

ClawMem wiki pages should follow Google Open Knowledge Format (OKF) v0.1 where
the GitHub wiki API allows it:

- Treat each content page slug as a concept document. Example: slug
  `projects/clawmem` represents OKF concept `projects/clawmem.md`.
- Start each concept page with YAML frontmatter delimited by `---`.
- Include non-empty `type`; use `type: ClawMem Knowledge Page` by default.
- Prefer `title`, `description`, `resource`, `tags`, and `timestamp` when they
  make retrieval or review clearer.
- Put issue references in the markdown body, not only in frontmatter. ClawMem
  uses visible body refs as recall boost signals.
- Use standard markdown headings, lists, and tables in the body.
- Keep `index` / `*/index` pages as OKF directory listings and `log` / `*/log`
  pages as chronological maintenance notes.

The concept page body should:

- summarize the current useful view, not just list source fragments
- cite issue memories with visible `#123` or `owner/repo#123` references
- preserve enough refs for traceability and recall boosting
- distinguish current state from history or deprecated states
- include review or update conditions when the claim can go stale
- avoid unsupported claims
- avoid copying every memory

Recommended section headings:

- `# Current State`: compact current synthesis for fast orientation
- `# History`: previous, deprecated, or archived states that explain the current
  answer
- `# Canonical Memories`: bullets linking the active memory issues behind the
  synthesis
- `# Status`: active/deprecated/archived state and update conditions
- `# Related`: links to nearby concepts in the wiki
- `# Open Questions`: stale, missing, or uncertain areas to verify
- `# Citations`: numbered source links, including memory issues and external
  sources when claims depend on them

Example concept page:

```markdown
---
type: ClawMem Knowledge Page
title: Project: ClawMem
description: Current cross-task compiled knowledge for the ClawMem project.
resource: clawmem://wiki/projects/clawmem
tags: [project, clawmem]
timestamp: 2026-06-24T00:00:00Z
---

# Current State

ClawMem uses GitHub issues as durable memory records and OKF wiki pages as
agent-facing compiled knowledge pages.

# History

- Pre-OKF wiki pages may still exist and should be migrated when touched.

# Canonical Memories

- #123: Issue memory is the ground truth for atomic durable memories.
- #124: Wiki pages are compiled knowledge pages and recall boosters.

# Status

- active
- Revisit when the memory issue schema or wiki API changes.

# Related

- [Operations](../workflows/operations)

# Open Questions

- Confirm whether any pre-OKF wiki pages still need migration.

# Citations

[1] #123
[2] #124
```

Example index page:

```markdown
# Projects

* [ClawMem](clawmem) - Current project-level ClawMem knowledge.
```

Example log page:

```markdown
# Project Update Log

## 2026-06-24

* **Update**: Migrated [ClawMem](clawmem) to OKF wiki compiled-knowledge format.
```

Wiki references are relation and ranking signals, not filters. Retrieval should
prefer useful OKF pages for orientation but must search issue memories directly
in parallel so orphan memories remain discoverable.

If wiki conflicts with an open memory issue, trust the issue and update the wiki.

Existing pre-OKF wiki pages may still be consumed as background. When editing
one, migrate it to OKF frontmatter and body sections instead of preserving the
old shape.

## Page-First Retention

Create or update an OKF wiki page when a future agent would otherwise need to
synthesize the same answer from fragments:

- current status that supersedes older memories
- profile or preference pages that combine several atomic values
- workflow, runbook, or project pages that link decisions, lessons, and tasks
- causal explanations where the "why" matters as much as the fact
- recurring questions where the right answer depends on current/history/source
  boundaries

Do not promote every issue to wiki. Promote only when the page adds structure:
current state, history, sources, lifecycle, review condition, or links. If the
page only repeats one memory issue verbatim, keep the memory issue as the record.

## Shared Memory Quality

Shared memories should be cleaner than private scratch memory:

- write conclusions, not speculation
- link source conversations and decisions
- keep one canonical open issue per living shared fact when practical
- use stable `kind:*` and `topic:*` labels
- close stale shared records with a reason

If knowledge should stay personal, keep it in the agent default repo. If it
should shape multiple agents or people, put it in a shared repo and target that
repo explicitly.
