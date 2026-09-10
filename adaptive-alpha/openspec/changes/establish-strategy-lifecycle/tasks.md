## 1. Contracts and persistence

- [x] 1.1 Add lifecycle-state contract, legal transition table and immutable transition evidence (internal-paper scope).
- [x] 1.2 Add implementation-artifact registry and source/runtime/capability provenance.
- [x] 1.3 Add active/challenger comparison record with fixed protocol identity.

## 2. Ouroboros engineering boundary

- [x] 2.1 Define isolated work-order/result contracts for strategy, skill, subagent and harness artifacts.
- [x] 2.2 Validate declared capabilities and reject any protected control-plane target.
- [x] 2.3 Add matched artifact contract benchmark and operator review workflow. Non-strategy artifacts remain inert proposals; runtime adoption is not implemented.

## 3. Research and evaluation workflow

- [x] 3.1 Connect lab validation to internal shadow/paper challenger admission, atomically with the simulation account.
- [x] 3.2 Add preregistered forward evidence windows, risk monitoring thresholds and automatic demotion events. Alpha-decay detection remains future work.
- [x] 3.3 Add rollback selection without mutation of historical strategy versions; selection never reactivates a strategy.

## 4. Execution readiness

- [ ] 4.1 Split internal test PaperBroker from external paper and future live execution services.
- [x] 4.2 Add signed, single-use, expiring risk approval and broker reconciliation library contract with controlled-transport tests; external service wiring remains under 4.1.
- [ ] 4.3 Add portfolio-level allocation to qualified strategy lifecycle states.

## 5. UI, audit and verification

- [x] 5.1 Show lifecycle, challenger comparison, artifact sources and transition evidence. Full lineage remains available through authenticated API records.
- [ ] 5.2 Add audit views for approvals, demotions, rollbacks and broker reconciliation.
- [x] 5.3 Add negative-path and state-machine integration tests; update deployment runbook in docs/LIFECYCLE.md.

## Remaining integration boundaries

- [ ] Connect reviewed skills/subagents/harnesses to an isolated executable research runtime and independently benchmark actual self-evolution.
- [ ] Configure and verify real OpenAI/Ouroboros calls and the external paper account; no credentials or paid calls were used in automated acceptance.
- [ ] Add alpha-decay monitoring and general multi-strategy portfolio execution. Live capital is unavailable in v0.3.
