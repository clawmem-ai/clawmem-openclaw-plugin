# ClawMem Memory Schema

Use this reference when deciding how to label, write, update, or retire a
ClawMem memory issue.

## Records

ClawMem uses GitHub-native records:

- `type:conversation`: mandatory transcript mirror and raw episodic source
- `type:memory`: durable distilled memory

Do not add extra layer labels. The layer is represented by the record form:
conversation issues for episodes, memory issues for distilled knowledge, wiki
pages for context maps, and skills/docs/runbooks for executable procedure.

Conversation issues are provenance, audit trail, and rebuild input. They are
not the normal online recall layer. If a fact, date, preference, decision,
rule, skill trigger, lesson, profile note, or insight matters for future recall
or answering, write it into a `type:memory` issue.

## Wiki Context Maps

Issue memory carries atomic durable memory. Wiki pages carry context maps for
agents. A wiki page can summarize current project/user/topic/workflow context,
but it is not memory ground truth and must not become the only recall path.

Write issue memory first. Then update wiki only when the memory is important,
frequently reused, cross-task, current background, or useful for fast agent
startup.

Recommended wiki page families:

- `users/{user}`
- `projects/{project}`
- `topics/{topic}`
- `decisions/{area}`
- `workflows/{workflow}`

Avoid default `sessions/*` pages because `type:conversation` issues already
mirror raw sessions. Use `sessions/*` only for curated, important run summaries.

Wiki pages should cite the issue memories they summarize with visible Markdown
references:

```markdown
# Project: ClawMem Memory Architecture

## Current Position

ClawMem uses issue memories as atomic durable records and wiki pages as
agent-facing context maps.

## Stable Decisions

- Issue memory is the source of truth for atomic memory. refs: #12
- Wiki context provides orientation and recall boosting, not complete recall.
  refs: #18
- Retrieval searches issue memories directly in parallel with wiki search.
  refs: #24
```

Rules:

- wiki prose should summarize, not duplicate every memory
- important wiki claims should cite issue memories with visible `#123` or
  `owner/repo#123` references
- wiki references are relation and ranking signals, not filters
- if wiki conflicts with an open memory issue, trust the issue and update the
  wiki
- do not encode wiki truth in labels or hidden metadata
- wiki labels, when present, are optional search/routing hints only

## Labels

Use labels only for routing, filtering, and shared vocabulary.

Before recall or write, list labels from the selected repo. Do not assume that
the default repo's labels apply to another repo.

Required:

- `type:memory`

Optional:

- one `kind:*`
- a small number of `topic:*`

Lifecycle:

- open issue = active memory
- closed issue = inactive, stale, superseded, or archived

The inactive reason belongs in the closing comment, not in another lifecycle
label.

## Default Kinds

| Label | Use it for |
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

## Answerable Text

Memory issues are search and maintenance records, not just summaries. Preserve
the answer-bearing details inside `## Memory` so future agents should not need
to reopen raw transcript text during normal recall:

| Kind | Required detail shape |
| --- | --- |
| `kind:fact` | `<subject> <fact>`, with date/time and scope when known |
| `kind:preference` | `<person/team> prefers <choice> when <situation>` |
| `kind:convention` | `<scope> follows <rule>`, plus exception if known |
| `kind:decision` | `<scope> decided <choice>`, plus reason/effective time if useful |
| `kind:task` | `<actor/scope> needs <outcome>`, plus status/deadline when explicit |
| `kind:skill` | `Use/create/update <skill/doc> when <trigger>` |
| `kind:lesson` | `<failure/correction> taught <future rule>` |
| `kind:profile` | Compact, durable model of a person/team/project |
| `kind:insight` | Pattern or hypothesis plus boundary/uncertainty |

Do not make non-fact memories look like fact cards. Keep the kind-specific
meaning in natural language.

Use `kind:profile` and `kind:insight` for strongly supported human-style
inferences, not just explicit facts: career direction, fields of study, values,
interests, personality traits, likely political/religious leaning, community
relation, allyship, likely dislikes, and negative boundaries. Include the basis
and uncertainty. For example, `Melanie is supportive as an ally, but the source
does not say she identifies as LGBTQ`.

Supported inferences should be answer-shaped when future questions are likely
to ask them directly. Use visible wording such as `likely yes`, `likely no`,
`would likely`, `would not likely`, `suitable option`, `good hobby/activity`,
or `would not cause discomfort`, followed by the basis and boundary. This is
especially important for counterfactual, suitability, recommendation, and
status questions.

### Answer-Complete Records

`## Memory` should preserve the exact values future questions may ask for:
person names, places, organizations, dates, quantities, list items,
relationship targets, causes, and reasons. Avoid lossy abstractions.
It should also carry likely query hooks. Preserve the source wording, but add
the wording future users or agents will probably search: `weakness` can become
`favorite snack/food`; `about to try`, `started`, or a concrete activity event
can become `new/fun activity`; `suggested` can become `recommendation` or
`advice`. Do not infer a favorite-food memory from generic enjoyment of a meal
or event; require a direct preference signal such as `weakness`, `craving`, or
`favorite`, or keep it as a diet/meal fact.
A value buried in a broad memory without likely query wording is not fully
covered; add or retitle a focused memory so recall can find it.
It is acceptable to add a short `Query hooks:` sentence inside `## Memory` when
the hook is retrieval vocabulary, not a new fact.

Bad:

```markdown
## Memory

Caroline moved from her home country and values her support network.
```

Good:

```markdown
## Memory

Caroline moved from Sweden. As of the source conversation, she has known her
close friends for 4 years, since that move, and their support helped her after a
tough breakup and throughout her transition.
```

Use these body patterns inside `## Memory` when they fit:

- `atomic fact`: one subject plus one answer-bearing fact.
- `canonical set`: the complete known set, such as hobbies, places, pets,
  family members, tools, or constraints.
- `profile capsule`: compact durable model of a person, team, repo, or project.
- `answer-shaped consolidation`: cross-session scoped record for a stable
  property, such as activities, books/media, pets, events, artifacts, status,
  or project decisions.
- `detail sweep`: source-only microfact record for exact values that broad
  summaries tend to hide, such as collected items, advice steps, photo/sign
  wording, one-off feelings, suitable pets, gift/tool recommendations, or
  project durations.
- `query-hook repair`: focused alias record when a value exists but likely
  future question wording is missing, such as `favorite snack/food`, `new/fun
  activity`, `recommendation`, or `exact item`.
- `answer-completeness audit`: final narrow pass for source values that are
  still not answerable from memory alone. Check image/artifact authorship,
  ordinal creative-work timing, favorite/preference canonical sets, and exact
  advice or purpose phrases. Scattered memories are not enough for a set
  question; add one canonical subject-property memory when values are split
  across records or buried under another person's title. Keep the boundary
  visible so adjacent recipes, events, or items from other contexts do not leak
  into the canonical set. Audit each subject independently; a memory titled
  around Joanna's desserts is not sufficient for Nate's favorite desserts even
  if Nate appears in the body. Run the whole checklist and add every missing
  audited shape instead of stopping after the first one. For cross-session
  sets, name the contributing dates in the body; do not attach earlier values
  to a later source date as if they were stated that day.
- `temporal event`: event date plus source date or original relative phrase.
- `literal anchor ledger`: scoped bullets for short answer-bearing values such
  as dates, months, years, durations, quantities, exact names, and
  first/last/current/planned facts.
- `causal link`: cause, effect, and affected person/project/decision.
- `image/artifact fact`: exact image-caption object or scene plus the speaker's
  deictic wording, such as `this`, `here is one`, or `they made this`.
- `ordinal creative work`: first/second/third/fourth screenplay, movie, book,
  draft, or project plus action and timing, such as `Joanna third screenplay
  start in May 2022`. If only month-level timing is supported, preserve that
  boundary, such as `by May 2022; exact start day not stated`.
- `exact answer phrase`: advice, recommendation, or motivation wording that a
  future answer may need verbatim, such as `keep trying new things until
  something sparks excitement` or `strengthen the bond with her pets`.

Before saving, ask whether likely `who`, `what`, `when`, `where`, `why`,
`how many`, or `which items` questions can be answered from `## Memory` alone.
If not, enrich the issue or split the memory.

After semantic and literal-anchor passes, consolidate scattered values into
scoped records when future recall would otherwise need several transcript
comments. Check recurring people/entities for profile/status, canonical sets,
reasons/reactions, supported likely answers, and image/artifact facts.
For long multi-session sources, this should usually create or update several
scoped records, not zero or one.

Do not hide unrelated facts in one issue to reduce count. One issue can carry a
canonical set or a coherent event, but mixed titles such as `necklace, birthday
bowl, and counseling workshop` should be split into searchable records.

### Literal Anchor Ledgers

Use a ledger when a session or source contains many related short answers that
would be lost in a normal narrative summary. Ledgers are not a new memory kind
or label; they are usually `kind:fact` records with a scoped title. Do not make
a generic ledger for every session. If the exact value belongs naturally in a
semantic fact, profile, preference, decision, task, skill, lesson, or insight,
put it there instead.

Good:

```markdown
## Memory

Caroline and Melanie literal anchors:
- 2023-05-07: Caroline went to the LGBTQ support group. Source wording:
  "yesterday" in the 2023-05-08 conversation.
- 2022: Melanie painted a sunrise.
- The Sunday before 2023-05-25: Melanie ran a charity race for mental health.
- June 2023: Melanie planned to go camping.
- 4 years: Caroline had had her current group of friends for 4 years.
```

Bad:

```markdown
## Memory

Caroline and Melanie discussed recent events, hobbies, and future plans.
```

For high-value or benchmark writes, use `scripts/clawmem_memory_lint.py` on the
draft body before creating or editing the issue. The helper checks schema
mistakes and optional exact-value coverage; it does not decide whether a memory
should be written.
Use `--require-query-hooks` when evaluating source-derived memories whose
wording may differ from future questions, and `--require-frontloaded-expect`
when exact values should appear in titles or first sentences rather than being
buried deep in a long body.

### Recall With Ledgers

Literal anchor ledgers improve exact-value coverage, but they should not compete
equally with semantic memories for every question. Recall should be
question-aware:

- literal questions should include relevant ledger memories early
- semantic, causal, preference, decision, profile, and explanation questions
  should prefer ordinary semantic memories first
- ledgers can still support semantic answers when exact dates, quantities, or
  names matter, but they should not crowd out the main semantic record
- list or set answers should scan for all values tied to the asked predicate,
  merge compatible values, and avoid adjacent values that answer a different
  predicate
- favorite/current-favorite answers should prefer direct favorite wording over
  adjacent played/watched/read/tried activity records
- activity-in-month answers should prefer memories whose subject, activity
  predicate, and event month all match the question over later broad hobby
  summaries
- when recalled memories overlap or conflict, use the most specific memory whose
  title or text matches the question's subject, object, action, and date to
  resolve the conflict; broad summaries can still supply compatible context
- answerers should preserve date granularity from `## Memory`; month/year-only
  memories should not become day-specific answers unless the day is visible in
  the memory text
- answerers should resolve supported relative phrases such as `last week`
  against visible source date context and answer with calendar time instead of
  repeating the relative phrase

If evals show many `recall_miss` cases after adding ledgers, reduce generic
ledger creation and improve titles/body query hooks. More memory records are not
automatically better when they dilute retrieval.

## Temporal Semantics

`valid_from` and `valid_to` describe the validity of the memory statement. They
do not replace event dates in the visible memory text.

Use this distinction:

- `event date`: when the remembered event happened; write it in `## Memory`
- `valid_from`: when the memory statement becomes valid for future use
- `valid_to`: when the statement stops being valid, if known

Example:

```markdown
## Memory

On 2023-05-07, Caroline went to the LGBTQ support group. This was described in
the 2023-05-08 conversation as "yesterday".

<!-- clawmem
schema_version: clawmem/v2
valid_from: 2023-05-08
valid_to:
-->
```

For ongoing states, preferences, conventions, or profiles, `valid_from` may be
the best available temporal anchor:

```markdown
## Memory

As of 2023-08-01, Jolene uses video games, Susie, and pets to cope with stress.
```

Rules:

- Convert relative dates only when the source date is known.
- Keep the original relative phrase when it may help review or answering.
- Do not leave relative-only anchors when the source date supports conversion;
  write the computed date, month, or year next to the original phrase.
- Do not invent exact dates.
- Preserve granularity. If the source only supports `April 2023`, do not write
  a specific day.
- Treat the source timestamp as provenance, not the event date. `recently`,
  `just`, `currently`, or a plain message timestamp do not by themselves
  justify a day-level event date; write `as of <source_date>` or the supported
  month/year unless the source gives an exact date, a resolvable relative
  phrase, or explicit same-day wording.
- Never rely on hidden metadata alone to answer event-date questions.
- Deterministic normalization may append obvious anchors to already-kept
  memory text, such as `last year (2022)`, `yesterday (2023-05-07)`, or
  `ten years earlier (about 10 years ago, around 2013)`. It should not create
  new memories or decide retention value.

## Canonicalization

Before writing, search for existing open `type:memory` issues about the same
subject/property, entity, skill trigger, or canonical set.

Prefer `UPDATE` over `ADD` when the new information:

- extends a list or set
- refines a profile or preference
- corrects an event date or condition
- advances the same task or decision
- turns scattered fragments into a more answerable canonical memory

For set-like facts, keep one current issue when practical:

```markdown
## Memory

Melanie's known recurring activities include pottery, camping, painting, and
swimming.
```

## Body Format

Visible issue bodies are GitHub Flavored Markdown:

```markdown
## Memory

The durable memory in human-readable language.

## Relations

- Source: #123
- Supersedes: #88
- Related: #91

## Notes

Optional caveats, review notes, or short maintenance context.

<!-- clawmem
schema_version: clawmem/v2
valid_from: 2026-04-24
valid_to:
-->
```

Rules:

- `## Memory` is the canonical human-facing record.
- `## Relations` uses normal GitHub issue references so humans and agents can
  follow relationships through GitHub-compatible issue views.
- `## Evidence` is optional and only for synthesized, uncertain, or multi-source
  memories that need a short justification.
- Do not duplicate labels or lifecycle state inside the body.
- Do not put event-date details only in hidden metadata.
- Do not add `memory_id`, `confidence`, or author fields by default. GitHub
  issue numbers, issue authors, and comment authors already carry that history.

## Write Decisions

- `ADD`: create a new `type:memory` issue.
- `UPDATE`: edit the existing canonical issue.
- `DELETE`: close the stale/false/superseded issue, add a closing comment, and
  link a replacement when one exists.
- `NONE`: do not write.

Before writing, search for duplicates and conflicts. If support is not strong
enough for a durable record, choose `NONE` and ask the user when the uncertainty
matters. Do not create candidate issues or candidate labels.

## Local Alpha Filter

Prefer retaining knowledge that public pretraining would not already provide:

- user or team preferences
- repo/project decisions
- conventions and policies
- environment-specific facts
- recurring failures and lessons
- procedural knowledge that should become a skill/doc/runbook

Skip generic public facts unless they are tied to a local decision,
convention, or failure.
