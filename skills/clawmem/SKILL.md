---
name: clawmem
description: GitHub-native durable memory workflows for the ClawMem OpenClaw plugin. Use when ClawMem is installed and you need to recall, create, update, close, link, or maintain repo-backed memory issues; reason about transcript mirrors; choose the right memory repo; or operate ClawMem collaboration through GitHub-compatible `gh` / `gh api` commands.
---

# ClawMem

ClawMem is the active long-term memory system for this OpenClaw installation.
It uses a GitHub-compatible backend: issues are records, comments are history,
labels are schema, references are relations, and issue state is lifecycle.

The plugin is intentionally small. It provisions credentials, mirrors every
real user/assistant transcript into `type:conversation` issues, injects compact
recall context when available, and exposes only operational tools:

- `clawmem_status`
- `clawmem_sync`
- `clawmem_maintain`

Do not look for `memory_store`, `memory_update`, `memory_forget`, or broad
collaboration wrapper tools. Memory work is skill-driven through GitHub-native
operations.

## Operating Model

Use ClawMem the way a careful human uses GitHub:

- list accessible repos before memory work and choose the right owner/repo
- list labels in the selected repo before recall, write, update, or close
- search before acting
- inspect exact issues before deciding what is true
- update the canonical issue instead of creating duplicates
- close stale records with a reason
- link source conversations and related records with `#123` references
- respect repo, org, team, and collaborator boundaries
- leave an auditable trail for the next collaborator

The transcript mirror is mandatory episodic memory. Durable memories are
distilled `type:memory` issues derived from those conversations or other source
artifacts. The transcript mirror is provenance, audit trail, and rebuild input;
it is not the normal online recall layer.

## Turn Loop

On every user turn:

1. Ask whether prior memory could materially improve the answer.
2. Use auto-injected ClawMem context when it is enough, but never treat a miss
   as proof that no memory exists.
3. If any explicit ClawMem memory operation is needed, resolve the route, list
   repos, choose the repo, and list labels for that repo.
4. If explicit recall is still needed, search only the chosen repo and only
   `type:memory` issues.
5. After answering, ask whether the turn produced durable local alpha.
6. If it did, create, update, close, or deliberately skip self-contained memory
   issues through GitHub operations.

Local alpha means knowledge specific to this person, team, repo, environment,
decision, failure, preference, or procedure. Do not store generic public
knowledge unless it is tied to a local convention or decision.

## Repo And Label Preflight

Before any explicit recall, store, update, close, or schema-sensitive operation:

```sh
eval "$(python3 scripts/clawmem_exports.py)"
```

That exports:

- `CLAWMEM_AGENT_ID`
- `CLAWMEM_BASE_URL`
- `CLAWMEM_HOST`
- `CLAWMEM_DEFAULT_REPO`
- `CLAWMEM_REPO`
- `CLAWMEM_TOKEN`

Never print, store, or paste the token.

Then list accessible repos and choose the correct memory repo. Cache the result
within the task when you will do multiple operations:

```sh
cache_dir="${TMPDIR:-/tmp}/clawmem-${CLAWMEM_AGENT_ID}"
mkdir -p "$cache_dir"

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api user/repos --paginate \
    --jq '.[] | {full_name, description, updated_at}' \
    >"$cache_dir/repos.jsonl"
```

Choose `CLAWMEM_REPO` from that repo list. Prefer an explicit user-selected,
team-selected, or project-selected repo. Use the configured default repo only
when it is clearly the intended scope. If multiple repos are plausible and the
choice materially affects the answer or write, ask the user.

After choosing the repo, list labels before recall or write. Cache labels for
the chosen repo:

```sh
repo_slug="$(printf '%s' "$CLAWMEM_REPO" | tr '/:' '__')"
label_cache="$cache_dir/labels-$repo_slug.json"

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh label list --repo "$CLAWMEM_REPO" \
    --limit 200 \
    --json name,description,color \
    >"$label_cache"
```

If `type:memory` is absent, explicit recall should return no durable memories
for that repo. Before writing, create the required labels that are missing.

Use per-command environment prefixes for `gh`; do not export credentials
globally for unrelated GitHub work.

## Recall

Recall depends on the selected repo and its labels. Do the repo and label
preflight first. Then use focused searches:

Prefer focused searches:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue list --repo "$CLAWMEM_REPO" \
    --state open \
    --label "type:memory" \
    --search "<short query>" \
    --limit 20 \
    --json number,title,body,labels,updatedAt
```

If recall matters, inspect exact issues before relying on them:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue view <number> --repo "$CLAWMEM_REPO" \
    --json number,title,body,state,labels,comments
```

When debugging recall quality, ask the backend for search observability:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api search/issues \
    -f q='<query> repo:<owner/repo> is:issue state:open label:"type:memory"' \
    -f per_page=20 \
    -f debug=true
```

Use each item's `debug` payload to inspect `search_path`, `lexical_rank`,
`semantic_rank`, `matched_fields`, `semantic_distance`, and final `score`.
Add `-f text_matches=true` only when you need title/body/comment snippets; it
can make search responses much larger. Do not read `matched_fields` or
`text_matches` as proof that lexical rank contributed to ordering;
semantic-only results can still include snippets for individual query terms.

Backend issue search is GitHub-compatible rather than a question-answering
retriever. Long natural-language questions can miss because lexical search is
strict about free-text terms, and semantic ranking may not always rescue a broad
question. For normal online recall, start with one focused query made of stable
entities plus durable nouns or anchors, such as `Melanie charity race`, `Joanna
third screenplay`, or `Evan Sam passion advice`. Avoid unstable verb forms such
as `run`, `take`, `buy`, `begin`, or `give` unless that exact word is part of a
known title/body hook. When debugging a miss, run one second compact variant,
then, if needed, a narrower core variant that drops weak words such as
`friend`, `item`, `photo`, or `memory` and keeps the entity plus durable nouns,
for example `Sam kayaking` or `John gear deal`. Repair the memory title/body if
that query finds the right issue below top-k. Do not make many-query recall the
default unless local eval shows it improves answer quality under the latency
budget.

When an auto-recalled memory includes `source: #123`, treat that issue reference
as provenance for audit, repair, or rebuilding memories. Do not use source
conversation issues as the normal answer path. If information is needed for
future recall or answering, update the memory issue so `## Memory` contains it
directly.

Use question-aware recall when literal anchor ledgers exist:

- for literal questions such as `when`, `how long`, `how many`, `what date`,
  `what year`, exact names, current/first/last/planned facts, include matching
  literal anchor ledger memories early in the context
- for semantic, causal, preference, profile, decision, or `why/how would`
  questions, prefer ordinary semantic memories first and include ledger memories
  only when they add necessary exact values
- do not let ledger memories crowd out semantic memories for broad explanation
  questions
- if a literal value is useful but only appears in a conversation issue, repair
  the durable memory by adding the value to `## Memory`; do not rely on raw
  transcript recall as the normal path
- when answering from recalled memories, preserve date granularity. If
  `## Memory` only supports a month, year, or says exact day not stated, do
  not invent a specific day from `valid_from` or source refs.
- for time questions, resolve supported relative phrases such as `last week` or
  `yesterday` against the visible source date context, then answer with calendar
  time at the requested granularity instead of repeating the relative phrase.
- for list or set questions, scan all recalled memories for values tied to the
  asked predicate and merge compatible values; avoid adding adjacent activities,
  preferences, or attributes that answer a different predicate.
- when memories overlap or conflict, use the most specific memory whose title or
  text matches the question's subject, object, action, and date to resolve the
  conflict; broad profile or canonical summaries can still supply compatible
  missing context.
- keep similarly named people, partners, friends, projects, and adjacent
  entities separate. Rely on direct support for the named entity instead of
  transferring nearby facts.
- for image or artifact questions, use the exact object, scene, or action tied
  to the image/artifact wording in memory before falling back to a general theme.

## Retention

Choose one write decision:

- `ADD`: create a new memory issue.
- `UPDATE`: edit the existing canonical issue.
- `DELETE`: close a false, stale, superseded, or harmful issue; leave a comment
  and link a replacement when one exists.
- `NONE`: do not write.

If support is not strong enough for a durable write, choose `NONE` and ask the
user when the uncertainty matters. Do not create candidate issues, candidate
labels, or half-committed memory records.

Before writing, search for duplicates and conflicts. Keep one canonical open
issue per living fact when practical. Always use the selected repo and its
observed label vocabulary; create missing required labels before creating or
editing memory issues.

Use answerable retention. The visible memory text must be sufficient for future
recall and answering without going back to raw transcript text. This does not
mean every memory needs an `## Evidence` section. It means `## Memory` must keep
the details future agents need to search, answer, judge, and maintain it:

| Kind | Preserve in the memory text |
| --- | --- |
| `kind:fact` | subject, fact, date/time if known, condition or scope |
| `kind:preference` | whose preference, situation where it applies, default behavior |
| `kind:convention` | rule, team/repo/project scope, exception if known |
| `kind:decision` | chosen direction, scope, effective time, reason if useful |
| `kind:task` | desired outcome, owner/status/deadline when explicit |
| `kind:skill` | when to use/create/update the skill/doc/runbook |
| `kind:lesson` | failure/correction, cause, future rule |
| `kind:profile` | compact model of the person/team/project, not a transcript summary |
| `kind:insight` | synthesized pattern plus boundary or uncertainty |

For supported inference records, especially likely/counterfactual/status or
suitability memories, make the answer shape explicit. Include the likely answer
or recommendation, the basis, and the uncertainty boundary in visible text:
`likely yes`, `likely no`, `would likely`, `would not likely`,
`suitable option`, `good hobby/activity`, or `would not cause discomfort`.
Do not leave these as broad profile summaries. A future agent should not have
to reopen the transcript to infer that an ally is likely not a community member,
that a career choice depends on received support, or that a pet/activity would
fit a constraint.

Titles should include the main entity and action. For temporal memories, keep
the concrete date in the title or first sentence when it is known.
Also include likely query hooks that future agents or users will search for,
while preserving the original source wording. For example, if the source says
`ginger snaps are his weakness`, write `favorite snack/food: ginger snaps` in
the title or first sentence and note that the source wording was `weakness`.
If the source says someone is about to try kayaking, write `new activity:
kayaking` with the supported time anchor. If the source says someone went
skiing in Banff in July 2023, write a focused `fun activity: skiing in Banff`
memory rather than burying it inside a broad trip or sports profile.
Do not infer a favorite food from generic enjoyment of a meal or event; require
a direct preference signal such as `weakness`, `craving`, or `favorite`, or keep
it as a diet/meal fact instead.
A value buried in a broad memory without the likely query wording is still a
retention gap. Add or retitle a focused memory rather than assuming the value is
covered.
It is acceptable to add a short `Query hooks:` sentence inside `## Memory` when
the hook is for retrieval vocabulary, not a new fact.
Do not combine unrelated facts to reduce issue count. A title like `Sweden
necklace, birthday bowl, and counseling workshop` is a split signal: those are
separate query intents unless they are part of one event or canonical set.

### Answer-Complete Retention

Do not write lossy summaries when the source contains answer-bearing values.
Preserve exact names, places, organizations, dates, quantities, list items,
relationship targets, causes, and stated reasons. If the source says
`Sweden`, do not store only `home country`. If the source lists `pottery,
camping, painting, and swimming`, do not store only `hobbies` or one example.

Before writing or updating, run this self-check:

- Could a future agent answer likely `who`, `what`, `when`, `where`, `why`,
  `how many`, or `which items` questions from `## Memory` alone?
- Are concrete values preserved instead of generalized away?
- For dates, is the event date in visible text, and is the original relative
  phrase kept when useful for review?
- For lists, is the current canonical set explicit?
- For relations, is the target entity named, not just implied?

If the answer is no, enrich `## Memory`, split the record, or update the
canonical issue before saving.

Use these body shapes inside `## Memory` when they fit; these are writing
patterns, not extra labels:

- `atomic fact`: one subject, one answer-bearing fact, concrete date/scope when
  known.
- `canonical set`: the current known set of activities, places, people, tools,
  pets, skills, constraints, or preferences.
- `profile capsule`: durable compact model of a person, team, repo, or project,
  including exact stable identifiers and relationships.
- `answer-shaped consolidation`: a scoped cross-session record for a stable
  property future questions are likely to ask about, such as `<person>
  activities`, `<person> books and media`, `<person> pets`, `<person> events`,
  `<person> artifacts and symbols`, or `<project> decisions`.
- `detail sweep`: source-only microfacts that broad summaries often compress
  away, such as exact collected items, advice steps, photo/sign/poster wording,
  one-off feelings, suitable pets, gift/tool recommendations, or project
  durations. Add these as answer-complete memories when they are not already
  visible in existing memory text.
- `query-hook repair`: focused alias memory when a value exists but likely
  future question wording is missing, such as `favorite snack/food`, `new/fun
  activity`, `recommendation`, or `exact item`.
- `answer-completeness audit`: final narrow pass for values that are present in
  the source but still not answerable from memory alone. Check image/artifact
  authorship, ordinal creative-work timing, favorite/preference canonical sets,
  exact advice or purpose phrases, supported likely/counterfactual answers, and
  suitability or recommendation answers. Scattered memories are not enough for a
  set question; add one canonical subject-property memory when values are split
  across records or buried under another person's title. Keep the boundary
  visible so adjacent recipes, events, or items from other contexts do not leak
  into the canonical set. Audit each subject independently; a memory titled
  around Joanna's desserts is not sufficient for Nate's favorite desserts even
  if Nate appears in the body. Run the whole checklist and add every missing
  audited shape instead of stopping after the first one. For cross-session
  sets, name the contributing dates in the body; do not attach earlier values
  to a later source date as if they were stated that day.
- `temporal event`: event date, source date, and useful original relative phrase.
- `literal anchor ledger`: compact bullets for short answer-bearing anchors
  such as dates, months, years, durations, quantities, first/last/current facts,
  names, projects, places, and planned times.
- `causal link`: cause, effect, and the entity or decision it affected.
- `supported inference`: likely yes/no, likely preference, likely leaning,
  likely status, counterfactual answer, suitable option, or recommended hobby,
  with basis and boundary visible. Use this for questions shaped like `would`,
  `likely`, `wouldn't cause`, `good hobby`, or `what would fit`.
- `image/artifact fact`: exact image-caption object or scene plus the speaker's
  deictic wording, such as `this`, `that`, `here is one`, or `they made this`.
  Make authorship or ownership yes/no-ready when supported, for example
  `Melanie made the black and white bowl in the photo`.
- `ordinal creative work`: first/second/third/fourth screenplay, movie, book,
  draft, or project plus action and timing, for example `Joanna third
  screenplay start in May 2022`. If the source only supports month-level timing
  from a dated session, write the month and boundary explicitly: `by May 2022;
  exact start day not stated`.
- `exact answer phrase`: advice, recommendation, or motivation wording that a
  future answer may need verbatim, such as `keep trying new things until
  something sparks excitement` or `strengthen the bond with her pets`.

For human-style memory, do not store only explicit facts. When strongly
supported by the source, store answerable profile and insight memories too:
career direction, fields of study, values, interests, personality traits,
political or religious leaning, community relation, allyship, likely dislikes,
and likely negative answers. Keep the support and boundary in the text instead
of pretending an inference is a bare fact.

Examples:

- `Caroline is oriented toward psychology, counseling certification, and mental
  health work for transgender people; her support network and transition
  experience are part of that motivation.`
- `Melanie appears supportive of Caroline and the transgender community as an
  ally, but the source does not say Melanie identifies as LGBTQ.`
- `Melanie is more likely to enjoy a national park than a theme park because
  her recurring interests include camping, running, swimming, and nature
  painting.`
- `Caroline would likely have Dr. Seuss books because she says she stocks
  classic children's books; the source does not say she owns Dr. Seuss.`
- `Melanie's kids made a cup with a dog face on it in the pottery workshop; the
  image caption names the cup, and Melanie said "they made this".`

One memory may contain several details only when they support the same
subject-property, canonical set, event, decision, skill trigger, lesson, or
causal link. Otherwise split it.

### Answer-Shaped Consolidation

After the semantic and literal-anchor passes, do one consolidation pass over the
whole source. This is not transcript recall and not a benchmark shortcut; it is
the step a careful human would do when turning many GitHub comments into durable
issues.

For each recurring person, pair, project, or entity, ask whether existing memory
issues can answer these shapes from `## Memory` alone:

- profile/status: relationship status, family role, origin or move history,
  job or business status, education/field, community role, political or
  religious leaning, and important personal symbols
- canonical sets: activities, hobbies, books/media/games, pets, places, events
  attended, volunteering/community actions, objects made/bought/received, foods,
  tools, and recurring plans
- reasons and reactions: why someone acted, how they felt, what another person
  thought about it, and what the event meant to them
- supported likely answers: likely yes/no, likely preference, likely future
  action, or likely boundary, with the basis and uncertainty visible
- suitability/recommendation answers: what would be a good fit, what would not
  cause discomfort, what indoor/outdoor activity would satisfy both constraints,
  and why
- image/artifact facts: what an image caption identifies when the message says
  `this`, `that`, `here is one`, `check them out`, or `they made this`

When the same property is spread across sessions, update or create one scoped
canonical-set memory instead of leaving the values scattered. For example,
`Melanie activities` should name the observed activities directly, not only the
latest routine.

For long multi-session sources, this pass should usually create or update
several scoped records, not zero or one. At minimum, check each major recurring
person/entity for activities, books/media, pets/family, events/community,
artifacts/symbols, relationship/status, likely inferences, reasons/reactions,
and project or business milestones.

For projects and businesses, canonical records should cover more than status.
Check origin or motivation, shared founder arcs, location or space requirements,
offerings and services, promotion tactics, products or collections, launch or
status milestones, constraints, and next steps. If two people share a meaningful
arc, write it directly, such as `Jon and Gina both lost jobs and started their
own businesses`.

Do not trade literal coverage for consolidation. Keep answer-bearing dates,
years, durations, counts, exact names, and relative-time conversions visible in
the relevant memory text while adding scoped consolidation records.

### Literal Anchor Pass

After the semantic retention pass, do a second pass for literal anchors. This is
especially important for future `when`, `how long`, `how many`, `which`, `who`,
and `what was the exact item` questions. The second pass is a repair pass, not a
quota. Prefer putting exact values into the relevant semantic memory. Create a
ledger only when several short anchors share a person, pair, project, repo, or
topic and would otherwise be lost.

Look for:

- dates, months, years, weekdays, holidays, and relative time phrases
- durations and ages, such as `4 years`, `10 years ago`, or `a few days`
- counts and quantities, such as `2 strikes`, `three dogs`, or `one pendant`
- exact project, event, game, book, organization, place, and pet names
- first, last, current, planned, previous, next, and recently changed facts

Use `kind:fact` for literal anchor ledgers unless the record is clearly a
profile, preference, convention, decision, task, skill, lesson, or insight. Do
not create a new `kind:*` label for anchors.

Example:

```markdown
## Memory

Caroline and Melanie literal anchors:
- 2023-05-07: Caroline went to the LGBTQ support group. Source wording:
  "yesterday" in the 2023-05-08 conversation.
- 2022: Melanie painted a sunrise.
- The Sunday before 2023-05-25: Melanie ran a charity race for mental health.
- June 2023: Melanie planned to go camping.
- 4 years: Caroline had had her current group of friends for 4 years.
- 10 years ago: Caroline's 18th birthday was described as 10 years ago.
```

Ledger memories should stay scoped: one person, pair, project, repo, or source
thread. Prefer one to a few dense ledger records over dozens of tiny records
when the values are related and likely to be recalled together. Avoid generic
session ledgers whose titles only say `literal anchors`; they compete with
semantic memories during recall without giving the search index a useful hook.

### Search-Before-Write

Before creating a memory, search open `type:memory` issues for the subject,
property, key entities, and likely topic labels. Then decide:

- `ADD` only when no active canonical issue already represents the memory.
- `UPDATE` when the new information refines, corrects, extends, or consolidates
  an existing canonical memory.
- `DELETE` when an active memory is false, stale, or superseded; close it with a
  comment and link the replacement when one exists.
- `NONE` when the memory is already represented accurately or is not durable.

When the right action is uncertain, inspect more issues, ask the user, or choose
`NONE`. A memory issue should only exist when it is ready to be maintained as a
durable record.

Prefer one canonical issue per living subject/property when practical. For
set-like facts, update the canonical set instead of appending fragments:

- good: `Melanie's known recurring activities include pottery, camping,
  painting, and swimming.`
- poor: `Melanie mentioned pottery.`

For profile, preference, convention, and skill memories, update the existing
issue that represents the same entity or trigger instead of scattering small
duplicates.

### Temporal Semantics

`valid_from` and `valid_to` describe the validity of the memory statement, not
necessarily the event date. Event dates, relative-date conversions, and original
relative phrases that matter for answering belong in `## Memory`.

Examples:

- `On 2023-05-07, Caroline went to the LGBTQ support group. This was described
  in the 2023-05-08 conversation as "yesterday".`
- `As of 2023-08-01, Jolene uses video games, Susie, and pets to cope with
  stress.`

Rules:

- Convert relative dates only when the conversation or source date is known.
- Preserve the original relative phrase when it may matter, such as "the
  previous day" or "the Sunday before 2023-05-25".
- Do not leave relative-only anchors. If `last week` can be converted from a
  known source date, write the computed date, month, or year next to the
  original phrase.
- Preserve temporal granularity. If the source only supports `April 2023`, write
  `April 2023, exact day not stated`; do not invent `2023-04-03`.
- Treat the source timestamp as provenance, not the event date. Do not turn
  `recently`, `just`, `currently`, or a plain message timestamp into an exact
  event date unless the source gives an exact date, a resolvable relative
  phrase, or explicit same-day wording. Otherwise write `as of <source_date>` or
  the supported month/year in `## Memory`.
- If the source asks for or states a relative expression such as `the Friday
  before 2022-06-24`, keep that expression even when you also compute the
  calendar date.
- Do not invent exact dates when the source does not support them.
- Keep date-bearing facts in the memory body; do not rely on `valid_from` to
  answer event-date questions.
- After writing or updating date-bearing memories, run a deterministic temporal
  normalization pass before any expensive LLM repair. This pass may add obvious
  calendar anchors to already-kept phrases, such as `last year (2022)`,
  `yesterday (2023-05-07)`, `last weekend (2023-07-08 to 2023-07-09)`, or
  `ten years earlier (about 10 years ago, around 2013)`. It must not decide
  whether a new fact is worth storing; that decision belongs to the retention
  pass.
- Use LLM temporal repair only as a fallback for memories that still contain
  relative-only anchors after deterministic normalization.

### Answerable Body Checklist

Before writing or updating, check that `## Memory` answers these questions when
they are relevant:

- Who or what is the subject?
- What durable fact, preference, decision, rule, task, skill trigger, lesson,
  profile note, or insight should future agents use?
- What exact answer-bearing values did the source provide: names, dates, places,
  quantities, list items, relation targets, causes, or reasons?
- When did the event happen, or from when is the state valid?
- What literal anchors did the turn add: dates, durations, quantities,
  first/last/current/planned facts, and exact item names?
- What scope, condition, trigger, exception, or uncertainty bounds it?
- For lists or collections, what is the current canonical set?
- For causal or counterfactual questions, what relationship or rationale should
  future agents remember?

### Retention Quality Gate

For benchmark runs, high-value memories, or any write where exact answers matter,
draft the body first and lint it before creating or editing the issue:

```sh
python3 scripts/clawmem_memory_lint.py --body-file "$body_file"
```

When an eval harness or source task has known answer-bearing values, pass them
explicitly so lossy drafts fail before they are written:

```sh
python3 scripts/clawmem_memory_lint.py \
  --body-file "$body_file" \
  --require-query-hooks \
  --require-frontloaded-expect \
  --expect "Sweden" \
  --expect "pottery" \
  --expect "camping" \
  --expect "painting" \
  --expect "swimming"
```

## Memory Shape

Use GitHub Flavored Markdown as the visible body:

```markdown
## Memory

The durable fact, preference, decision, lesson, profile note, or skill note.

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

Good `## Memory` examples preserve the value that a future answer may need:

```markdown
## Memory

As of the 2023-07-20 conversation, Melanie's known recurring activities are
pottery, camping, painting, and swimming.
```

```markdown
## Memory

On 2023-06-09, Caroline gave a school event talk about her transgender journey.
The source conversation described this as "last week" relative to 2023-06-16.
```

Poor memories generalize away the answer: `Melanie has hobbies.` or `Caroline
gave a talk recently.`

Labels:

- always include `type:memory`
- choose one `kind:*` when helpful
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
stale, superseded, or archived. Put the inactive reason in the closing comment.

## Skill Memories

Procedural knowledge should usually become a skill, repo doc, or runbook.
Use `kind:skill` issues to remember when to use, create, or update that
procedure and to link the conversations or failures that caused the change.

Do not bury long executable workflows inside memory issues.

## References

- For schema details, read [references/schema.md](references/schema.md).
- For raw `gh` / `curl` flows and troubleshooting, read [references/manual-ops.md](references/manual-ops.md).
- For activation repair and route verification, read [references/repair.md](references/repair.md).
- For user-facing messaging, read [references/communication.md](references/communication.md).
- For collaboration, use GitHub-compatible org/team/repo operations and read [references/collaboration.md](references/collaboration.md).
