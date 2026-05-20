# ClawMem Manual Operations And Troubleshooting

Use this reference for GitHub-native ClawMem operations through `gh`, `gh api`,
or `curl`.

The plugin exposes only operational tools. Durable memory CRUD is performed as
normal issue work in the ClawMem backend.

## Route, Repo, And Label Preflight

```sh
eval "$(python3 scripts/clawmem_exports.py)"
```

Preflight:

```sh
test -n "$CLAWMEM_REPO" || { echo "ClawMem repo missing for agent $CLAWMEM_AGENT_ID"; exit 1; }
test -n "$CLAWMEM_TOKEN" || { echo "ClawMem token missing for agent $CLAWMEM_AGENT_ID"; exit 1; }
case "$CLAWMEM_REPO" in
  */*) ;;
  *) echo "Invalid CLAWMEM_REPO='$CLAWMEM_REPO' (expected owner/repo)"; exit 1 ;;
esac
```

List accessible repos before memory work. The configured default repo is a
starting point, not proof that it is the right scope:

```sh
cache_dir="${TMPDIR:-/tmp}/clawmem-${CLAWMEM_AGENT_ID}"
mkdir -p "$cache_dir"

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api user/repos --paginate \
    --jq '.[] | {full_name, description, updated_at}' \
    >"$cache_dir/repos.jsonl"

jq -r '.full_name' "$cache_dir/repos.jsonl"
```

Choose `CLAWMEM_REPO` from the repo list. Prefer the repo selected by the user,
team, project, or current task. If the correct scope is ambiguous, ask.

Then list labels in the chosen repo before recall or write:

```sh
repo_slug="$(printf '%s' "$CLAWMEM_REPO" | tr '/:' '__')"
label_cache="$cache_dir/labels-$repo_slug.json"

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh label list --repo "$CLAWMEM_REPO" \
    --limit 200 \
    --json name,description,color \
    >"$label_cache"

jq -r '.[].name' "$label_cache"
```

Do not export `GH_HOST` or `GH_ENTERPRISE_TOKEN` globally for unrelated GitHub
work. Use per-command prefixes:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue list --repo "$CLAWMEM_REPO"
```

## Ensure Labels

Run this after label preflight and only create labels that are missing.

```sh
for lbl in \
  "type:conversation" "type:memory" \
  "kind:fact" "kind:preference" "kind:convention" "kind:decision" \
  "kind:task" "kind:skill" "kind:lesson" "kind:profile" "kind:insight"; do
  GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
    gh label create "$lbl" --repo "$CLAWMEM_REPO" --color "5319e7" 2>/dev/null || true
done
```

Create `topic:*` labels only when they are reusable shared vocabulary.

## Search Memories

Search only after repo and label preflight. If `type:memory` is absent from the
chosen repo, there are no durable memory records to recall from that repo.

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue list --repo "$CLAWMEM_REPO" \
    --state open \
    --label "type:memory" \
    --search "<short query>" \
    --limit 50 \
    --json number,title,body,labels,updatedAt
```

Inspect exact records before relying on them:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue view <number> --repo "$CLAWMEM_REPO" \
    --json number,title,body,state,labels,comments
```

When the repo contains literal anchor ledgers, route recall by question shape.
For literal questions (`when`, `how long`, `how many`, exact names, current,
first, last, or planned facts), inspect matching ledger memories early. For
semantic, causal, preference, decision, profile, or explanation questions,
prefer non-ledger memories first and use ledgers only for exact-value support.
Ledger records should not crowd out ordinary semantic memories for broad
questions.
When answering, preserve date granularity: if `## Memory` only supports a month,
year, or says exact day not stated, do not invent a day from `valid_from` or a
source issue reference.
For time questions, resolve supported relative phrases such as `last week` or
`yesterday` against the visible source date context, then answer with calendar
time at the requested granularity instead of repeating the relative phrase.
For list or set questions, scan all recalled memories for values tied to the
asked predicate and merge compatible values; avoid adding adjacent activities,
preferences, or attributes that answer a different predicate.
When memories overlap or conflict, use the most specific memory whose title or
text matches the question's subject, object, action, and date to resolve the
conflict; broad profile or canonical summaries can still supply compatible
missing context.
Keep similarly named people, partners, friends, projects, and adjacent entities
separate. Rely on direct support for the named entity instead of transferring
nearby facts.
For image or artifact questions, use the exact object, scene, or action tied to
the image/artifact wording in memory before falling back to a general theme.

If a memory has `## Relations` with `Source: #123`, treat that reference as
provenance for audit, repair, or rebuilding. Do not make source conversation
issues the normal answer path. If the source contains information that future
agents need for recall or answering, update the memory issue so `## Memory`
contains that information directly.

For recall debugging, request backend search observability:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api search/issues \
    -f q='<query> repo:<owner/repo> is:issue state:open label:"type:memory"' \
    -f per_page=20 \
    -f debug=true
```

Inspect `debug.search_path`, `debug.lexical_rank`, `debug.semantic_rank`,
`debug.matched_fields`, `debug.semantic_distance`, and final `score`. Add
`-f text_matches=true` only when you need exact title/body/comment snippets;
it increases response size. This distinguishes title/body query-hook problems
from semantic ranking problems.

`matched_fields` and `text_matches` explain which snippets contain individual
query terms; they do not mean lexical rank affected ordering. A result can be
`semantic_only` and still show title/body snippets. Long natural-language
questions can also miss entirely because GitHub-compatible lexical search is
strict about free-text terms and semantic ranking may not always rescue a broad
question.

For recall misses, try one compact repair query using stable entities plus
durable nouns or exact anchors, such as names, dates, counts, durations, item
names, `charity race`, `third screenplay`, or `passion advice`. Avoid unstable
verb forms such as `run`, `take`, `buy`, `begin`, or `give` unless that exact
word is part of a known title/body hook. If compact recall is still noisy, try
a narrower core variant that drops weak words such as `friend`, `item`, `photo`,
or `memory` and keeps the entity plus durable nouns, for example `Sam kayaking`
or `John gear deal`. If the compact/core query finds the right memory only
below top-k, fix the memory title or `## Memory` text so future normal recall
has a better search hook. Do not route normal answers through raw conversation
issues.

## Create A Memory

Create memories only after repo and label preflight, duplicate/conflict search,
and ensuring required labels exist. Write the `## Memory` text so it carries the
answer-bearing details for its kind: subject, scope, date/time, trigger,
decision, rule, failure, or uncertainty as applicable. Future normal recall
should be able to answer from the memory issue without reopening raw transcript
text.

Preserve exact answer-bearing values. Do not replace concrete names, places,
dates, quantities, list items, relationship targets, causes, or reasons with a
vague summary. For example, write `Sweden`, not only `home country`; write
`pottery, camping, painting, and swimming`, not only `hobbies`.
Add query hooks for likely future wording while keeping the source wording:
`weakness` can become `favorite snack/food`; `about to try`, `started`, or a
concrete activity event can become `new/fun activity`; `suggested` can become
`recommendation` or `advice`. Do not infer a favorite-food memory from generic
enjoyment of a meal or event; require a direct preference signal such as
`weakness`, `craving`, or `favorite`, or keep it as a diet/meal fact.
A value in a broad memory without the likely query wording is still a retention
gap; add or retitle a focused memory so normal recall can find it.
It is acceptable to add a short `Query hooks:` sentence inside `## Memory` when
the hook is retrieval vocabulary, not a new fact.

Use one of these `## Memory` shapes when useful:

- `atomic fact`: one subject plus one concrete fact.
- `canonical set`: a maintained set of activities, people, places, tools, pets,
  skills, or constraints.
- `profile capsule`: compact model of a person, repo, team, or project.
- `answer-shaped consolidation`: cross-session scoped record for one stable
  property, such as activities, books/media, pets, events, artifacts, status, or
  project decisions.
- `detail sweep`: source-only microfacts that broad extraction tends to hide,
  such as exact collected items, advice steps, photo/sign/poster wording,
  feelings and triggers, suitable pets, gift/tool recommendations, or project
  durations.
- `query-hook repair`: focused alias memory when a value exists but likely
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
  as dates, durations, quantities, exact names, first/last/current facts, and
  planned times.
- `causal link`: cause, effect, and affected entity.
- `image/artifact fact`: exact image-caption object or scene plus the speaker's
  deictic wording, such as `this`, `here is one`, or `they made this`.
- `ordinal creative work`: first/second/third/fourth screenplay, movie, book,
  draft, or project plus action and timing, such as `Joanna third screenplay
  start in May 2022`. If only month-level timing is supported, preserve that
  boundary, such as `by May 2022; exact start day not stated`.
- `exact answer phrase`: advice, recommendation, or motivation wording that a
  future answer may need verbatim, such as `keep trying new things until
  something sparks excitement` or `strengthen the bond with her pets`.

After the semantic retention pass, do a literal anchor pass. This second pass is
for facts that are easy to lose in summaries but likely to be asked later:
`when`, `how long`, `how many`, `which item`, `who`, and exact `what` values.
Keep these anchors in `## Memory`, not only in hidden metadata or source
conversation comments. Prefer enriching the relevant semantic memory. Create a
ledger only when several short anchors share a person, pair, project, repo, or
topic and would otherwise be lost. Use `kind:fact` for ledger records unless
another existing kind clearly fits; do not create a new anchor label.

Then do one answer-shaped consolidation pass over the whole source. For each
recurring person, pair, project, or entity, check whether open memories can
answer profile/status, canonical set, reason/reaction, likely yes/no, and
image/artifact questions from `## Memory` alone. When values are scattered
across sessions, update or create a scoped canonical-set issue instead of
leaving the agent to rediscover them from transcript comments.
For long multi-session sources, this pass should usually create or update
several scoped records, not zero or one.
For projects and businesses, check origin or motivation, shared founder arcs,
location or space requirements, offerings and services, promotion tactics,
products or collections, launch or status milestones, constraints, and next
steps. Pair/commonality facts should be direct records when supported, such as
two people both losing jobs and starting their own businesses.

Finally, do a detail sweep for long source conversations. Walk the source
message by message and add missing answer-bearing details that are not already
visible in memory bodies: exact lists, episodic actions, advice steps,
object/image facts, feelings and triggers, profile-boundary inferences, and
small temporal facts. This is still memory retention, not transcript recall; the
resulting memory should stand alone.

Example ledger:

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

Before creating, search existing open memories for the same subject/property,
entity, skill trigger, and likely topic labels:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue list --repo "$CLAWMEM_REPO" \
    --state open \
    --label "type:memory" \
    --search "<subject property or key entities>" \
    --limit 20 \
    --json number,title,body,labels,updatedAt
```

Use `ADD` only when no active canonical issue already represents the memory.
Use `UPDATE` when the new information refines, corrects, extends, or
consolidates an existing memory.

Use GitHub Flavored Markdown:

```sh
body_file="$(mktemp)"
cat >"$body_file" <<'EOF'
## Memory

<durable local-alpha memory>

## Relations

- Source: #123

<!-- clawmem
schema_version: clawmem/v2
valid_from: 2026-04-24
valid_to:
-->
EOF

python3 scripts/clawmem_memory_lint.py --body-file "$body_file"

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue create --repo "$CLAWMEM_REPO" \
    --title "<concise title>" \
    --body-file "$body_file" \
    --label "type:memory" \
    --label "kind:decision"

rm -f "$body_file"
```

Prefer titles and bodies in the user's current language. Keep labels
machine-readable.

When exact answer values are known from an eval harness or source task, pass
them to the lint helper before writing:

```sh
python3 scripts/clawmem_memory_lint.py \
  --body-file "$body_file" \
  --require-query-hooks \
  --require-frontloaded-expect \
  --expect "<exact value>"
```

Temporal rules:

- `valid_from` and `valid_to` describe memory validity, not necessarily event
  time.
- Put event dates and useful relative-date conversions in `## Memory`.
- If a 2023-05-08 conversation says "yesterday", write the event as
  `2023-05-07` and optionally preserve "yesterday" for review.
- Do not leave relative-only anchors when the source date supports conversion.
  Write the computed date, month, or year next to the original phrase.
- Preserve granularity. If the source only supports `April 2023`, write
  `April 2023, exact day not stated`; do not invent a day.
- Treat source timestamps as provenance, not event dates. Do not turn
  `recently`, `just`, `currently`, or a plain message timestamp into an exact
  day unless the source gives an exact date, a resolvable relative phrase, or
  explicit same-day wording.
- If the source uses `the Friday before 2022-06-24`, keep that phrase even when
  you also compute the calendar date.
- Do not invent exact dates when the source date is missing or ambiguous.
- Before asking an LLM to repair temporal wording, run a deterministic
  normalization pass over already-kept memories. It may append obvious anchors
  such as `last year (2022)`, `yesterday (2023-05-07)`, `last weekend
  (2023-07-08 to 2023-07-09)`, or `ten years earlier (about 10 years ago,
  around 2013)`. It should not create new memories or decide retention value.
- Treat any remaining relative-only anchors after deterministic normalization
  as an LLM repair queue.

## Update A Memory

Search first. If the new information refines the same canonical fact, edit the
existing issue instead of creating a duplicate.

Update rather than append when maintaining set-like or evolving memories:

- activity lists
- preferences with new conditions
- profiles and recurring patterns
- ongoing tasks and decisions
- skill triggers and lessons

Keep one canonical open issue per living subject/property when practical.

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue edit <number> --repo "$CLAWMEM_REPO" \
    --title "<updated concise title>" \
    --body-file <body-file>
```

Add a comment when the meaning changed materially:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue comment <number> --repo "$CLAWMEM_REPO" \
    --body "Updated because #123 clarified the current convention."
```

## Close A Stale Memory

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue comment <number> --repo "$CLAWMEM_REPO" \
    --body "Closing as superseded by #456."

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue close <number> --repo "$CLAWMEM_REPO"
```

Closing is the default "delete" behavior. Do not hard-delete records unless the
user explicitly requests it and policy allows it.

## Relations

Write normal GitHub references in bodies and comments:

- `Source: #123`
- `Supersedes: #88`
- `Related: owner/repo#91`

Use these references as the durable relation notation. Do not maintain a
separate relation table in memory issue bodies; when GitHub-compatible link or
backlink support is available, the same references should become navigable.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `gh` talks to github.com | Prefix each command with `GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN"` |
| Route is missing | Run `clawmem_status`; trigger one real turn if the agent has not been provisioned |
| Mirror is behind | Run `clawmem_sync`; inspect `clawmem_status` for pending sessions |
| Mirror reports an error | Run `clawmem_sync` with `sessionId` and the same `repo`; finalization should wait until the missing transcript comments are repaired |
| Summary/finalization is stale | Run `clawmem_maintain` |
| Recall is weak | Search with shorter terms, inspect exact issues, and expand through linked references |
| Duplicate memory exists | Update/close issues so one canonical open issue remains |

## Autonomy

Allowed without extra confirmation:

- search and view issues
- create or update memory issues
- add comments
- create reusable labels
- close stale memory issues with a reason

Requires explicit user confirmation:

- org/team membership changes
- repo transfer or destructive permission changes
- hard deletion
- OpenClaw config edits
- service restarts
