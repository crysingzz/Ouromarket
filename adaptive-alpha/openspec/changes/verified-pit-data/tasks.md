## Contracts and verification

- [x] Add bounded provider, rights, adjustment-policy and revision-ledger contracts.
- [x] Validate timestamps, ordering, unique source sequences and exact correction lineage.
- [x] Reject point-in-time assertions on ordinary dataset uploads.

## As-of storage

- [x] Store content-addressed ledgers and server-generated verification reports.
- [x] Materialize idempotent raw and adjusted snapshots from revisions received by the cutoff.
- [x] Bind each snapshot to its exact ledger, report, cutoff, revision set and adjustment policy.

## Operations and acceptance

- [x] Add operator-only import/snapshot API routes and authenticated proof inspection.
- [x] Add future-revision, malformed-ledger, authority and idempotency tests.
- [x] Update status/roadmap/verification documentation and pass full quality, OpenSpec and dependency checks.
