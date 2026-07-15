# ClawMem Operations

Use this reference when you need concrete GitHub-compatible `gh` / `gh api`
commands or AGS-specific `gh ags` commands for ClawMem memory work.

## Contents

- [Safety Rules](#safety-rules)
- [Route Preflight](#route-preflight)
- [Repo And Label Preflight](#repo-and-label-preflight)
- [Search Memories](#search-memories)
- [OKF Wiki Knowledge Pages](#okf-wiki-knowledge-pages)
- [Create A Memory](#create-a-memory)
- [Update A Memory](#update-a-memory)
- [Close A Memory](#close-a-memory)
- [Fallback Curl Probe](#fallback-curl-probe)
- [Troubleshooting](#troubleshooting)

## Safety Rules

- Resolve the ClawMem route before every operation batch.
- Use per-command credentials; do not globally export ClawMem tokens for
  unrelated GitHub work.
- Never print, store, paste, log, or commit `CLAWMEM_TOKEN`.
- Inspect current state before mutating anything.
- Ask for explicit user confirmation before permission, membership, invitation,
  transfer, or deletion changes.
- Scope memory by repo/org/team boundaries, not `scope:*` labels.

## Route Preflight

```sh
eval "$(python3 scripts/clawmem_exports.py)"

test -n "$CLAWMEM_HOST" || { echo "missing CLAWMEM_HOST"; exit 1; }
test -n "$CLAWMEM_TOKEN" || { echo "missing CLAWMEM_TOKEN"; exit 1; }
```

Check the current route without printing the token:

```sh
printf 'agent=%s\nbase=%s\nextBase=%s\nrepo=%s\ndefaultRepo=%s\ntoken=%s\n' \
  "$CLAWMEM_AGENT_ID" \
  "$CLAWMEM_BASE_URL" \
  "$CLAWMEM_EXT_BASE_URL" \
  "$CLAWMEM_REPO" \
  "$CLAWMEM_DEFAULT_REPO" \
  "$(test -n "$CLAWMEM_TOKEN" && printf SET || printf MISSING)"
```

Use this prefix for `gh` commands:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api user
```

AGS Wiki operations require the `gh-ags` extension. Install it once, or upgrade
an existing installation before relying on its command contract:

```sh
gh extension install ngaut/gh-ags
# Existing installation:
gh extension upgrade ags
```

`gh-ags` uses standard GitHub CLI authentication. Pass the provisioned host and
token through the same per-command environment variables used by `gh`; it has
no separate `--token` flag or credential store. `GH_HOST` also supplies the
target host when `--repo` is in `OWNER/REPO` form, so do not repeat it with
`--hostname`.

## Repo And Label Preflight

List accessible repos:

```sh
cache_dir="${TMPDIR:-/tmp}/clawmem-${CLAWMEM_AGENT_ID}"
mkdir -p "$cache_dir"

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api user/repos --paginate \
    --jq '.[] | {full_name, description, updated_at}' \
    >"$cache_dir/repos.jsonl"
```

Choose `CLAWMEM_REPO` from the repo list. Use the default repo only when it is
clearly the intended scope.

List labels for the chosen repo:

```sh
repo_slug="$(printf '%s' "$CLAWMEM_REPO" | tr '/:' '__')"
label_cache="$cache_dir/labels-$repo_slug.json"

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh label list --repo "$CLAWMEM_REPO" \
    --limit 200 \
    --json name,description,color \
    >"$label_cache"
```

Create missing required labels before writing:

```sh
for label in \
  "type:conversation" "type:memory" \
  "kind:fact" "kind:preference" "kind:convention" "kind:decision" \
  "kind:task" "kind:skill" "kind:lesson" "kind:profile" "kind:insight"; do
  if ! jq -e --arg name "$label" '.[] | select(.name == $name)' "$label_cache" >/dev/null; then
    GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
      gh label create "$label" --repo "$CLAWMEM_REPO" --color "ededed" || true
  fi
done
```

## Search Memories

Search open durable memories:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue list --repo "$CLAWMEM_REPO" \
    --state open \
    --label "type:memory" \
    --search "<short query>" \
    --limit 20 \
    --json number,title,body,labels,updatedAt
```

Inspect an exact issue before relying on it:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue view <number> --repo "$CLAWMEM_REPO" \
    --json number,title,body,state,labels,comments
```

Debug backend issue search:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api search/issues \
    -f q='<query> repo:<owner/repo> is:issue state:open label:"type:memory"' \
    -f per_page=20 \
    -f debug=true
```

Add `-f text_matches=true` only when you need snippets. Large search responses
can slow down the turn.

## OKF Wiki Knowledge Pages

Wiki APIs are extension APIs under `/api/ext/v1`, not GitHub-compatible
`/api/v3` endpoints. Use `gh ags wiki` for them. Successful operations return
one JSON object on stdout, which can be consumed directly or filtered with
`jq`.

Search wiki pages after direct issue recall:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh ags wiki search "<short query>" \
    --repo "$CLAWMEM_REPO" --limit 3
```

`--limit` accepts any positive integer and `gh-ags` automatically fetches
additional API pages when needed. Keep the initial recall limit small unless
the task needs a broader result set, since every additional page adds latency
and response volume.

Fetch a page:

```sh
slug="<wiki-slug>"

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh ags wiki get "$slug" \
    --repo "$CLAWMEM_REPO" |
  jq '{slug,title,body,sha}'
```

Create or update wiki only after the referenced memory issue exists. Wiki pages
are compiled knowledge pages: they turn scattered source memories into a
reviewable current view with history, sources, status, update conditions, and
related concepts. They should follow OKF v0.1 concept-document conventions:
YAML frontmatter plus structured markdown body. Include visible issue
references in the body; do not rely on frontmatter-only refs for recall
boosting.

ClawMem wiki slugs map to OKF-style paths:

- `projects/clawmem` is equivalent to `projects/clawmem.md`
- `projects/index` is an OKF directory index page
- `projects/log` is an OKF chronological update log

Before drafting a page body, read the canonical format and template in
[schema.md](schema.md). Write the complete desired body to a temporary file,
including current state, visible backing issue references, status, update
conditions, related concepts, and citations as applicable.

Create a page:

```sh
slug="projects/example"
body_file="$(mktemp)"

# Edit "$body_file" with the full desired wiki body.

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh ags wiki put "$slug" \
    --repo "$CLAWMEM_REPO" \
    --body-file "$body_file" \
    --message "Create wiki knowledge page: $slug"
```

Update a page:

```sh
slug="projects/example"
current="$(
  GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
    gh ags wiki get "$slug" \
      --repo "$CLAWMEM_REPO"
)"
sha="$(printf '%s' "$current" | jq -r '.sha')"
body_file="$(mktemp)"

# Edit "$body_file" with the full desired wiki body.

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh ags wiki put "$slug" \
    --repo "$CLAWMEM_REPO" \
    --body-file "$body_file" \
    --message "Update wiki knowledge page: $slug" \
    --sha "$sha"
```

If the update exits with status `6`, fetch the latest page, re-apply the
intended change, and retry with the new SHA. `put` is never retried
automatically. If its structured error sets `outcome_unknown` to `true`, fetch
the page before deciding whether another write is safe.

## Create A Memory

Draft the issue body in a temporary file. Lint high-value or eval-sensitive
memory bodies before writing:

```sh
python3 scripts/clawmem_memory_lint.py --body-file "$body_file"
```

Create the issue:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue create --repo "$CLAWMEM_REPO" \
    --title "<memory title>" \
    --body-file "$body_file" \
    --label "type:memory" \
    --label "kind:fact"
```

Use `kind:fact` only when that is the right kind. See
[schema.md](schema.md) for the kind list.

## Update A Memory

Fetch and inspect the existing canonical issue first:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue view <number> --repo "$CLAWMEM_REPO" \
    --json number,title,body,state,labels,comments
```

Write the full replacement body to a temp file, then edit:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue edit <number> --repo "$CLAWMEM_REPO" \
    --title "<updated title>" \
    --body-file "$body_file"
```

Add a comment when the reason for the change is not obvious:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue comment <number> --repo "$CLAWMEM_REPO" \
    --body "Updated to preserve the exact answer-bearing value from #123."
```

## Close A Memory

Close false, stale, superseded, or harmful memories with a reason:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue comment <number> --repo "$CLAWMEM_REPO" \
    --body "Closing because this memory is superseded by #456."

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh issue close <number> --repo "$CLAWMEM_REPO"
```

## Fallback Curl Probe

Use this only when `gh` is unavailable or broken:

```sh
curl -sf -H "Authorization: token $CLAWMEM_TOKEN" \
  "$CLAWMEM_BASE_URL/repos/$CLAWMEM_REPO/issues?state=open&per_page=1&type=issues" | \
  jq 'map({number,title})'
```

If this returns JSON, even `[]`, the route is usable.

## Troubleshooting

| Problem | Check |
| --- | --- |
| `401 Unauthorized` | Re-run route preflight; do not reuse an old token |
| Empty repo list | Confirm the current agent was provisioned and has accepted invitations |
| Missing `type:memory` | Explicit recall should return no durable memories; create required labels before writing |
| Wiki page is stale | Trust the open memory issue, then update the wiki summary |
| Mirror reports an error | Run `clawmem_sync` with the same session and repo |
