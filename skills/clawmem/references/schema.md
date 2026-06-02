# ClawMem Memory Schema

This is the schema reference for ClawMem memory issues and wiki context maps.
Runtime workflow belongs in [../SKILL.md](../SKILL.md). Concrete commands belong
in [github-ops.md](github-ops.md).

## Records

- `type:conversation`: mandatory transcript mirror and raw episodic source
- `type:memory`: durable distilled memory

Conversation issues are provenance, audit trail, and rebuild input. They are not
the normal online recall layer. If a transcript fact should affect future answers
or behavior, write it into a `type:memory` issue.

Wiki pages are context maps, not memory records. They summarize important current
context and cite issue memories with visible references.

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

## Wiki Context Maps

Issue memory is ground truth. Wiki is a context map.

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

Wiki pages should:

- summarize the current useful view
- cite issue memories with visible `#123` or `owner/repo#123` references
- preserve enough refs for traceability and recall boosting
- avoid unsupported claims
- avoid copying every memory

Wiki references are relation and ranking signals, not filters. Retrieval must
search issue memories directly in parallel with wiki search so orphan memories
remain discoverable.

If wiki conflicts with an open memory issue, trust the issue and update the wiki.

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
