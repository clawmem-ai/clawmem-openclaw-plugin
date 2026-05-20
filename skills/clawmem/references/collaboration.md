# ClawMem Collaboration

Use this reference when memory should live in a shared repo, or when multiple
agents/people need access to the same ClawMem memory space.

The vNext plugin does not expose broad `collaboration_*` wrapper tools. Use
GitHub-compatible `gh api` / `curl` operations after resolving the ClawMem route.

## Default Style

- Inspect current state before mutating anything.
- Require explicit user confirmation for permission, membership, invitation,
  transfer, or deletion changes.
- Think in GitHub-native objects: orgs, teams, repos, collaborators,
  invitations, issue labels, issue state.
- Never paste raw tokens into chat, memory issues, files, logs, or commits.

Resolve the route first:

```sh
eval "$(python3 scripts/clawmem_exports.py)"
```

Use per-command prefixes:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api "/user"
```

## Repo Routing

Choose the memory repo deliberately:

- personal memory: the agent's `CLAWMEM_DEFAULT_REPO`
- project memory: the project repo
- shared/team memory: the shared repo for that team or org

Do not mix scopes inside one repo unless the user explicitly wants that. In the
current design, scope is represented by repo/org/team boundaries, not `scope:*`
labels.

## Collaboration Model

- An organization is a governance boundary.
- Org membership is separate from team membership.
- Teams are org-scoped authorization groups.
- Effective repo access is the maximum of owner/admin rights, org base
  permission, direct collaborator grant, and team grant.
- Direct collaborator grants may create pending repo invitations.
- Accepting a repo invitation makes the repo visible to the invitee.
- Accepting an org invitation creates org membership and joins invited teams.
- Outside collaborators are non-members with direct access to at least one
  org-owned repo.

## Common Operations

List orgs:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api "/user/orgs"
```

List teams:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api "/orgs/<org>/teams"
```

Create an org-owned memory repo:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X POST "/orgs/<org>/repos" \
    -f name='team-memory' \
    -F private=true \
    -F has_issues=true
```

Grant a team repo access:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X PUT "/orgs/<org>/teams/<team-slug>/repos/<owner>/<repo>" \
    -f permission='write'
```

List direct collaborators:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api "/repos/<owner>/<repo>/collaborators"
```

Add a direct collaborator:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X PUT "/repos/<owner>/<repo>/collaborators/<username>" \
    -f permission='read'
```

List pending repo invitations for the current identity:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api "/user/repository_invitations"
```

Accept a repo invitation:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X PATCH "/user/repository_invitations/<invitation-id>"
```

## Quality Bar

Shared memories should be cleaner than private scratch memory:

- write conclusions, not speculation
- link source conversations and decisions
- keep one canonical open issue per living shared fact
- use stable `kind:*` and `topic:*` labels
- close stale shared records with a reason

If knowledge should stay personal, keep it in the agent default repo. If it
should shape multiple agents or people, put it in a shared repo and target that
repo explicitly.
