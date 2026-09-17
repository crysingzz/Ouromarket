# Verify point-in-time revision ledgers

## Why

The generic dataset contract accepts an operator-supplied point-in-time flag and stores only one value per event. It cannot prove which vendor revision was available at an earlier decision time, so a corrected historical value can be mistaken for information that was known then. Stage 6 requires server-verifiable availability and revision history before execution-aware laboratory work can rely on real data.

## What Changes

- Replace the generic operator assertion with an explicit refusal: ordinary dataset uploads cannot claim point-in-time verification.
- Add an immutable single-symbol daily revision ledger with event, publication and receipt times, source sequence, revision chain, raw and adjusted values, provider identity, usage rights and adjustment-policy version.
- Produce a content-addressed server verification report only after timestamp, ordering, uniqueness, revision-chain and rights checks pass.
- Materialize immutable raw or adjusted `as-of` snapshots by selecting only the newest revision received by the requested cutoff.
- Bind each snapshot to the exact ledger, verification report, cutoff, selected revisions and adjustment policy.
- Expose operator-only creation and authenticated proof inspection through the API.

## Impact

This change establishes a verifiable revision and as-of foundation. It does not claim that a live vendor has been contracted, verify corporate actions or historical universe membership, model exchange calendars beyond the declared XNYS daily profile, or make a dataset or strategy eligible for capital.
