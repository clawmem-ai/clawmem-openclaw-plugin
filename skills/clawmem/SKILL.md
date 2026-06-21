---
name: clawmem
description: "GitHub-native durable memory workflows for the ClawMem OpenClaw plugin. Use when ClawMem is installed and you need to recall, create, update, close, link, or maintain repo-backed memory issues; reason about transcript mirrors or wiki context maps; choose the right memory repo; or operate ClawMem through GitHub-compatible gh / gh api commands."
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

> Issue memory carries atomic durable memory. Wiki pages carry context maps.

Wiki context can restore background and boost recall, but it is not memory
ground truth. When wiki prose conflicts with an open memory issue, trust the
issue and repair the wiki.

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
4. Recall direct `type:memory` issues first. Search wiki pages only in parallel
   as orientation and ranking hints.
5. Answer from open memory issues when available. Use wiki context as background,
   not as the sole source of truth.
6. After answering, ask whether the turn produced durable local alpha.
7. If yes, create, update, close, or deliberately skip memory issues through
   GitHub operations.
8. If an important memory should be fast to recover on future starts, update the
   relevant wiki context page after the issue memory exists.

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

Wiki recall is a booster, not a gate:

- search issue memories directly even when wiki search is available
- include relevant wiki pages as compact background context
- follow visible `#123` / `owner/repo#123` refs to in-scope `type:memory` issues
- treat wiki-referenced memories as boosted candidates, not the only candidates
- ignore unsupported wiki prose when it would materially affect the answer

For debugging recall quality, use backend search observability with
`debug=true`. Do not treat snippets or matched fields alone as proof of final
ranking contribution.

For exact recall, wiki, and debug commands, read
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

Write durable information to issue memory first. Promote to wiki only when the
memory is high-importance, high-frequency, cross-task, current project/user/topic
background, or useful for fast agent startup.

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

## Wiki Context

Wiki pages are context maps for agents, not a third memory record layer. They
should summarize the current useful view and cite issue memories with visible
references.

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
- update wiki only for important or frequently reused context
- summarize, do not copy every memory
- keep visible issue refs
- if wiki is stale, repair the wiki rather than changing the answer source

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

- For memory schema, kinds, body format, wiki context maps, write decisions, and
  temporal rules, read [references/schema.md](references/schema.md).
- For concrete GitHub-compatible `gh` / `gh api` commands, read
  [references/github-ops.md](references/github-ops.md).
- For activation repair and route verification, read
  [references/repair.md](references/repair.md).
