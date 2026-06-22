# ClawMem Team Memory

Use this reference for shared team memory, team-aware routing, team membership
or repo access changes, and team lifecycle operations.

## Contents

- [Authority Model](#authority-model)
- [Repository Roles](#repository-roles)
- [Discover And Route](#discover-and-route)
- [Rules And Precedence](#rules-and-precedence)
- [Team Records](#team-records)
- [Cross-Team Memory](#cross-team-memory)
- [Native Team Operations](#native-team-operations)
- [Team Lifecycle](#team-lifecycle)
- [Validation](#validation)

## Authority Model

Keep authorization, durable knowledge, and compiled context separate:

| Question | Source of truth |
| --- | --- |
| Who can read, write, or administer a repo? | Live org membership, team membership, direct collaborator grants, and team-repo grants |
| What does a team own and how should it work? | Canonical open `type:memory` issues in the team or org memory repo |
| What should an agent read first for orientation? | OKF wiki pages that cite the canonical issues |
| What behavior is stable across ClawMem installations? | This bundled skill and its schema |

Treat permissions as a hard gate, not as a statement of business ownership. An
agent can have access without owning an area, and a profile can claim ownership
without granting access. Detect and repair either mismatch.

Do not create a monolithic Team Policy YAML issue by default. It would duplicate
live permission state and drift when teams or grants change. If an organization
already maintains a registry or `teams/index` page, use it as a discovery hint
and compiled view, then verify it against live GitHub-native state.

## Repository Roles

- **Agent default repo:** Treat an auto-provisioned default repo as private
  conversation and personal memory unless the user configured it as shared.
- **Team memory repo:** Use an org-owned shared repo for a team's durable domain
  knowledge, tasks, profiles, conventions, decisions, and lessons. Grant the
  native org team access to it.
- **Org memory repo:** Use an optional org-owned repo for organization-wide
  policy, standards, governance, and truly org-wide knowledge.
- **Shared project memory repo:** Use an explicitly shared repo when two or more
  teams jointly own a project or contract. Grant each participating team the
  minimum required access.
- **Business/code repo:** Treat access to a code repo as evidence of permission,
  not as proof that it is the team's memory repo.

Prefer the recommended `<team-slug>-memory` name for a new team memory repo, but
never select an existing repo for writes from its name alone. Verify its
description, labels, canonical team profile, and grants.

## Discover And Route

Resolve the current agent route first:

```sh
eval "$(python3 scripts/clawmem_exports.py)"
```

For team-scoped work, inspect live state with the current agent credentials:

```sh
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api user/orgs --paginate --jq '.[] | {login}'

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api "orgs/<org>/teams" --paginate \
    --jq '.[] | {slug,name,description,privacy}'

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api "orgs/<org>/teams/<team>/members" --paginate \
    --jq '.[] | {login}'

GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api "orgs/<org>/teams/<team>/repos" --paginate \
    --jq '.[] | {full_name,permissions,role_name,description}'
```

Also list the current agent's accessible repos as described in
[operations.md](operations.md). A repo absent from that list is not a valid
route for the current credentials, even if a profile or wiki page names it.

Route only through scopes relevant to the task:

1. Honor an explicit repo or team selected by the user after verifying access.
2. Use the owning team's memory repo for team-owned work.
3. Include org memory when an org-wide rule or standard can affect the task.
4. Include another team's repo only for a named dependency, handoff, contract,
   or cross-team responsibility.
5. Use private memory for personal context that should not shape the team.

Do not search every accessible team repo on every turn. Broad access is not
broad relevance, and indiscriminate recall can leak unrelated team context into
the task.

## Rules And Precedence

Apply these rules when instructions overlap:

1. Enforce live permissions first; text in memory or wiki cannot grant access.
2. Apply active org-wide conventions across the organization.
3. Apply active team conventions within that team's scope. A team convention
   may refine an org default, but it must not silently override an org rule that
   disallows exceptions.
4. Apply project decisions and task constraints within their narrower scope.
5. Treat the user's current request as task intent, not as an implicit rewrite
   of durable team policy or permissions unless the user explicitly requests
   that change.

If two active issue memories conflict, inspect their scope, timestamps,
relations, and status. Ask when precedence is not explicit, then update or close
the stale canonical issue. If wiki prose conflicts with an open issue, trust the
issue and repair the wiki.

## Team Records

Keep team policy distributed across canonical records that match the current
ClawMem schema:

- Maintain one `kind:profile` issue per team with status, purpose, domain scope,
  memory repo, business repos, maintainers, member responsibilities, related
  teams, and review conditions.
- Store standing rules, routing rules, ownership rules, and working agreements
  as separate `kind:convention` issues.
- Store deliberate changes as `kind:decision`, active work as `kind:task`, and
  corrections or postmortems as `kind:lesson`.
- Record an agent's `primary` or `cross-team` role as responsibility metadata in
  the affected team profile. It does not replace native membership or repo
  grants.

Use visible Markdown and issue relations; do not hide the useful team model in
a custom metadata block. Update the canonical profile instead of adding a new
profile for every membership change.

Create `teams/<slug>` as an OKF compiled knowledge page when the team benefits
from fast orientation. Cite the profile, conventions, decisions, and current
tasks. Create `teams/index` in an org memory repo only when an org-wide directory
adds value. Wiki pages are not authorization records.

Older diagrams may call these `rules memory` and `scope memory`. Map them to
`kind:convention` and `kind:profile`; do not introduce `kind:rule`,
`kind:scope`, or `scope:*` unless the target repo already uses them as an
established local schema.

## Cross-Team Memory

Keep one canonical owner whenever possible:

- Store knowledge owned by one team in that team's memory repo, even when
  another team consumes it. Link to it from the consuming team's issue or wiki
  page instead of copying it.
- Use a shared project memory repo when ownership and maintenance are genuinely
  joint.
- Use the org memory repo only when the knowledge applies organization-wide.
- Grant the minimum required read, write, or admin permission. Access to another
  team repo does not make all of its memories relevant to every task.

## Native Team Operations

Use `gh api` with the current ClawMem route. Inspect before mutating, and obtain
explicit user confirmation for the exact team, member, repo, permission, rename,
archive, or delete operation.

Common mutations:

```sh
# Create a native org team.
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X POST "orgs/<org>/teams" \
    -f name='<display-name>' -f description='<description>' -f privacy='closed'

# Create its private org-owned memory repo.
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X POST "orgs/<org>/repos" \
    -f name='<team-slug>-memory' -F private=true -F has_issues=true

# Add or update a team member.
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X PUT "orgs/<org>/teams/<team>/memberships/<user>" \
    -f role='member'

# Grant the team access to a repo.
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X PUT "orgs/<org>/teams/<team>/repos/<owner>/<repo>" \
    -f permission='write'
```

Use `member` or `maintainer` for team membership and `read`, `write`, or `admin`
for repo grants. Do not assume team membership creates org membership. Invite
or add the identity to the org first when required by the host.

## Team Lifecycle

### Add A Team

1. Inspect the org, existing teams, candidate repos, and naming collisions.
2. Create the native team and an org-owned team memory repo.
3. Grant the team `write` access to its memory repo and minimum access to its
   business repos.
4. Add members only after org membership exists.
5. Create the required labels, then seed the canonical `kind:profile` and any
   approved `kind:convention` or `kind:decision` issues.
6. Create or update `teams/<slug>` and an optional org `teams/index` only after
   the backing issues exist.
7. Verify the result using live membership, grants, issue, and wiki reads.

### Change Membership Or Responsibility

- For added access, create the native membership/grant, verify it, then update
  the affected profile and wiki.
- For removed access, revoke the native grant or membership first, then update
  profiles, close or reassign active tasks, and repair wiki context.
- For a responsibility-only change, update the profile without changing access
  unless the new work actually requires a different grant.
- For a rename, update the native team first, rediscover its resulting slug,
  then update profile titles, issue references, and wiki links. Do not rename
  the memory repo unless the user separately requests it.

### Archive A Team

Prefer semantic archive over destructive deletion:

1. Update the canonical team profile to `archived` with the effective date and
   successor or reason, set `valid_to` when known, and close the profile with a
   retirement reason so normal open-memory recall excludes it.
2. Close or reassign active tasks and close or supersede conventions that no
   longer apply.
3. Update the team wiki page and org index to show historical status.
4. Remove business-repo grants that are no longer needed and downgrade the team
   memory repo to `read` when historical access should remain.
5. Exclude the archived team from default recall and all default writes.

### Delete A Team

Treat native team deletion and memory-repo deletion as separate destructive
actions. Before deleting a native team, list its members and repo grants,
preserve administrator access to its memory repo, archive its semantic records,
and state which grants will disappear.

```sh
# Remove one membership.
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X DELETE "orgs/<org>/teams/<team>/memberships/<user>"

# Remove one team-repo grant.
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X DELETE "orgs/<org>/teams/<team>/repos/<owner>/<repo>"

# Delete the native team only after explicit confirmation.
GH_HOST="$CLAWMEM_HOST" GH_ENTERPRISE_TOKEN="$CLAWMEM_TOKEN" \
  gh api -X DELETE "orgs/<org>/teams/<team>"
```

Do not delete the memory repo by default. Delete it only as a separately named,
confirmed action after preserving or intentionally discarding its history.

## Validation

After any team change, verify:

- live org membership, team membership, and repo grants match intended access
- every active ClawMem team has exactly one identified writable team memory repo
- the canonical team profile matches actual scope and responsibilities
- active rules use current schema and archived teams receive no default writes
- cross-team knowledge has one canonical owner or an explicit shared repo
- OKF team pages cite issue memories and do not claim to grant access
- no token, cached permission snapshot, or customer-specific team list was
  written into the skill or plugin code
