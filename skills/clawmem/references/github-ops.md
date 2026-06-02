# ClawMem GitHub Operations

Use this reference when you need concrete GitHub-compatible `gh`, `gh api`, or
`curl` commands for ClawMem memory work.

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
printf 'agent=%s\nbase=%s\nrepo=%s\ndefaultRepo=%s\ntoken=%s\n' \
  "$CLAWMEM_AGENT_ID" \
  "$CLAWMEM_BASE_URL" \
  "$CLAWMEM_REPO" \
  "$CLAWMEM_DEFAULT_REPO" \
  "$(test -n "$CLAWMEM_TOKEN" && printf SET || printf MISSING)"
```

Use this prefix for `gh` commands:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api user
```

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

## Wiki Context

Search wiki pages after direct issue recall:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X GET "repos/$CLAWMEM_REPO/wiki/search" \
    -f q="<short query>" \
    -f limit=3
```

Fetch a page:

```sh
slug="<wiki-slug>"
encoded_slug="$(jq -rn --arg s "$slug" '$s|@uri')"

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api "repos/$CLAWMEM_REPO/wiki/pages/$encoded_slug" \
    --jq '{slug,title,body,sha}'
```

Create or update wiki only after the referenced memory issue exists. Include
visible issue references in the body.

Create a page:

```sh
slug="projects/example"
body_file="$(mktemp)"

# Edit "$body_file" with the full desired wiki body.

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X POST "repos/$CLAWMEM_REPO/wiki/pages" \
    -f slug="$slug" \
    -f title="$slug" \
    -f body="$(cat "$body_file")"
```

Update a page:

```sh
slug="projects/example"
encoded_slug="$(jq -rn --arg s "$slug" '$s|@uri')"
current="$(GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api "repos/$CLAWMEM_REPO/wiki/pages/$encoded_slug")"
sha="$(printf '%s' "$current" | jq -r '.sha')"
body_file="$(mktemp)"

# Edit "$body_file" with the full desired wiki body.

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X PUT "repos/$CLAWMEM_REPO/wiki/pages/$encoded_slug" \
    -f title="$slug" \
    -f body="$(cat "$body_file")" \
    -f sha="$sha"
```

If the update reports a SHA conflict, fetch the latest page, re-apply the
intended change, and retry with the new SHA.

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
