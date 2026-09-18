# Design

A `PITDatasetImport` is an immutable vendor ledger rather than a ready-to-backtest table. Every observation carries the market event time, provider publication time, platform receipt time, a provider sequence, a one-based revision number and an exact predecessor for corrections. The top-level contract records provider dataset identity, license and research usage rights, calendar, timezone, and the versioned adjustment rule. The first supported profile is single-symbol XNYS daily data so its limits remain explicit.

Import validates aware timestamps and `event <= published <= received`, deterministic event/revision ordering, globally unique provider sequences, consecutive revisions, exact predecessor links and strictly increasing receipt time within an event. The server stores the ledger by content hash and emits a separate content-addressed verification report. A caller-supplied boolean cannot manufacture that report.

An as-of request re-reads and revalidates the immutable ledger and report. For every event it selects the highest revision whose receipt time is no later than the cutoff, then creates a standard dataset snapshot. The snapshot manifest binds the source ledger and report, cutoff, raw/adjusted choice, selected provider sequences and adjustment policy. Repeating the same request is idempotent. A future correction produces a different later snapshot but cannot mutate or change the data selected by an earlier cutoff.

Both the ledger and every snapshot remain research-only and capital-ineligible. Execution-aware backtesting, corporate-action verification, historical universes and vendor ingestion will build on this boundary in later leaves.
