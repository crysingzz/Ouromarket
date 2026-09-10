## Context

A self-modifying general-purpose agent is an untrusted research proposer with respect to finance. A package import is not an isolation boundary. The platform therefore has its own dependency graph and never imports the parent Ouroboros runtime. User-attached architectural prescriptions inform platform requirements, while conversational recommendations inside the attached document are source material rather than instructions to the coding assistant.

## Goals / Non-Goals

Goals: executable local laboratory, reproducible reference runs, correct authority boundaries, independently deployed hidden evaluator, observable paper workflow, explicit coverage of the master specification.

Non-goals of this change: real trading, empirical alpha claims, external API keys, autonomous generated-code execution, full DSR/PBO, distributed worker infrastructure, self-evolution of agent code.

## Decisions

1. Modular monolith for trusted public services, private process/container for hidden evaluation. External agents interact through authenticated research HTTP only. API is trusted orchestration, not an agent process.
2. FastAPI serves static UI assets on the same origin. Bearer token stays in browser memory; no remote scripts, persistent browser storage or cookie authentication.
3. Immutable SQL records + separate mutable projections. DB triggers reject UPDATE/DELETE and PostgreSQL TRUNCATE. An application-wide transaction mutex serializes journal chaining, paper execution and kill-switch changes. This is intentionally low-throughput daily-research infrastructure.
4. Each attempt is admitted before expensive work. Terminal results are additional records, never edits. A process crash leaves an inspectable unresolved attempt; there is no claim of automatic worker crash recovery in v0.1.
5. The only executable strategy language is a bounded trusted template contract. TemplateEngineer produces inspectable metadata/source constants. That artifact is never evaluated as arbitrary Python. Provider and engineering protocols are integration seams, not fake adapters.
6. Synthetic generator v1 creates deterministic daily-like bars; PIT validation is limited to synchronous close data. Backtests lag signals one bar, charge 10 bps turnover, split public periods and examine three sequential fixed-strategy folds. These are not a train/retrain walk-forward system. DSR/PBO remain null; multiplicity penalty is named honestly.
7. Hidden evaluator owns its seed and SQLite ledger; network is internal, no published port, no detailed diagnostics endpoint. Global query budget survives restarts. API authenticates using a service token never issued to research identities.
8. Internal PaperBroker fills immediately inside the same DB transaction as risk. Prices are server-owned fixed synthetic snapshots with a 60-second freshness lease. Operator refresh explicitly refreshes this demo snapshot; it is not market data ingestion.
9. Policy v1 is frozen Python configuration inside a read-only image. Operator can halt/resume and admit validated synthetic strategies to demo paper. No HTTP policy editing or higher capital states.
10. PostgreSQL bootstrapping is schema v1, not a migration framework. The database owner is trusted deployment infrastructure. Hash chaining detects inconsistent edits, not a malicious database administrator recomputing or truncating the chain.

## Risks / Trade-offs

- This is a foundation/demo: synthetic PASS has no economic meaning and is structurally ineligible for real capital.
- Reference agents run in trusted process because they only return typed templates; connecting arbitrary Ouroboros to host checkout would violate the deployment contract.
- Coarse DB serialization favours correctness over throughput; audit verification scans the journal. Read scaling, role-specific DB grants and external WORM checkpoints are future work.
- Compute budget currently bounds admission of subsequent experiments; one admitted synchronous evaluation can consume its bounded network timeout. Container CPU/RAM/PID limits are additional boundaries.
- API worker crash preserves attempts but requires operator investigation before a new job; automatic leasing/retry is deferred.
- Portfolio allocator, ADV/sector/factor gates, real feed, partial fills and live brokers are intentionally unavailable.

## Migration Plan

Add a standalone package; initialize new empty DB volumes. Existing Ouroboros data is not migrated or read. Deploy via Docker Compose bound to loopback. Stop with `docker compose down` to preserve volumes. Any future schema/protocol change must carry an OpenSpec change, migration and negative-path tests.

## Verification

Unit and property tests cover no look-ahead, reproducibility, immutability, authorization, query bounds, state persistence, kill, stale quotes, reconciliation and order idempotency. Docker smoke exercises actual PostgreSQL and private evaluator. Inspect UI on desktop and mobile. Record executed checks in docs/VERIFICATION.md.
