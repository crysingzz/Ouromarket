# Design: controlled strategy lifecycle

## Authority model

The research agent owns hypothesis and StrategySpec creation. Ouroboros is an untrusted implementation engineer: it receives a frozen StrategySpec and creates only declared implementation artifacts inside an isolated workspace. The evaluator, risk service, broker credentials and production checkout are unavailable to that workspace.

The evaluator owns verification results; it cannot write candidate artifacts. The operator approves every capital-stage transition. Risk owns pre-trade admission and can halt, but cannot create a strategy. This prevents a strategy author from changing the rule that judges or executes it.

## State transitions

`RESEARCH → LAB_VALIDATED → SHADOW → PAPER → CHALLENGER → ACTIVE_LIMITED` requires retained evidence at each boundary. `ACTIVE_LIMITED → DEMOTED` is automatic for declared monitoring breaches and operator-confirmed for comparative underperformance. `DEMOTED → RETIRED` preserves all artifacts and evidence. A new candidate is always a child identity; no transition mutates a historical strategy version.

Promotion requires a matched active/challenger comparison: identical dataset identity, protocol, transaction-cost assumptions and evaluation window. It also requires a positive hidden evaluation and a completed forward period. The controller records metric values and the human decision; it cannot infer an approval from PASS alone.

## Implementation artifacts

An artifact contains `id`, `kind` (`strategy`, `skill`, `subagent`, `harness`), parent IDs, source digest, runtime digest, declared input/output schemas, explicit capability allowlist, budget, creator identity, test evidence and lifecycle state. It becomes usable only after static capability validation and a matched benchmark where applicable.

## Execution boundary

The production path receives a typed intent from an active strategy. Risk binds the intent to portfolio state, market-data snapshot and policy version. A successful check produces a signed, expiring approval consumed once by a dedicated broker outbox. Reconciliation treats uncertain submissions as UNKNOWN and halts further delivery. A live broker adapter is a future separate deployment from the existing paper-only adapter.
