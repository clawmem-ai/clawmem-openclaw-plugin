# Implementation Addendum

This document is retained only as a migration note. The first rewrite contract has been superseded by [skill-driven-redesign.md](./skill-driven-redesign.md).

Current vNext rules:

- transcript mirror is mandatory
- one normalized user/assistant message maps to one conversation issue comment by default
- conversation issues are provenance, audit trail, and rebuild input
- durable memory retention is skill-driven through GitHub-native issue operations, not plugin-owned finalize logic
- normal recall searches open `type:memory` issues only
- memory lifecycle is represented by issue state: open means active, closed means stale or retired
- scope is represented by repo/team routing, not scope labels
- event dates that matter for answering belong in the visible memory text
- `valid_from` and `valid_to` describe memory validity metadata
- retention should include a literal anchor pass for dates, durations,
  quantities, exact names, and first/last/current/planned facts that normal
  summaries tend to lose

Legacy implementations used flat YAML memory bodies plus lifecycle/date labels. The runtime may still recognize enough legacy data for recall and label cleanup, but new memory records should follow the schema documented by the ClawMem skill.
