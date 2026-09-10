# Establish strategy lifecycle and Ouroboros implementation boundary

## Why

v0.2 validates generated candidates and can run internal/external paper components, but it has no controlled lifecycle for an active strategy and its challengers. It also labels an Ouroboros HTTP engineering seam without an artifact registry for skills, subagents and implementation harnesses. The accepted product objective requires these boundaries before any live-capital work.

## What changes

- Define versioned lifecycle stages: `RESEARCH`, `LAB_VALIDATED`, `SHADOW`, `PAPER`, `CHALLENGER`, `ACTIVE_LIMITED`, `DEMOTED`, `RETIRED`.
- Define an immutable implementation-artifact registry for Ouroboros-created strategy code, skills, subagents and harnesses, including authority, declared capabilities, parent and evaluation evidence.
- Define independent promotion, demotion and rollback evidence for active/challenger comparison.
- Define a separate production execution boundary: risk-approved intent, short-lived approval, broker outbox and mandatory reconciliation. It does not enable live trading in this change.
- Retire demo-only concepts from operator-facing production workflow after equivalent lifecycle views exist; preserve deterministic fixtures and internal PaperBroker solely as test/reference infrastructure.

## Impact

Affected specs: `strategy-registry`, `agent-runtime`, `evaluation-engine`, `portfolio-risk`, `execution-engine`, `platform-security-observability`.

Affected implementation areas: strategy state projection, research campaign records, agent revision/benchmark registry, forward worker, UI and broker-outbox service. No live credentials, live endpoint or direct broker authority will be added until a later separately approved change.
