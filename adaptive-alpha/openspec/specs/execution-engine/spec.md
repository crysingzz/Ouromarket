# Paper Execution and Reconciliation

## Purpose

Platform contract for paper execution and reconciliation. Initial implementation and target-only requirements are distinguished in docs/STATUS.md.

## Requirements

### Requirement: Risk and execution atomicity
The initial internal PaperBroker SHALL commit risk approval, fill, positions and audit within one serialized database transaction.

#### Scenario: Concurrent order retries
- **WHEN** the same intent is delivered concurrently
- **THEN** exactly one fill and one position change are committed

### Requirement: Intent identity conflict
The platform SHALL reject reuse of an intent identity with different contents.

#### Scenario: Changed retry
- **WHEN** quantity changes under an existing intent ID
- **THEN** the request is rejected as an idempotency conflict

### Requirement: Reconciliation before recovery
An operator MUST reconcile internal and broker paper states before resuming a halted account.

#### Scenario: Mismatch remains
- **WHEN** operator requests resume with mismatched positions or cash
- **THEN** execution remains halted
