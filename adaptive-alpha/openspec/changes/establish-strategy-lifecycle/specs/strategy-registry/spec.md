## ADDED Requirements

### Requirement: Explicit simulation scope

The v0.3 lifecycle SHALL use `scope=internal-paper` and `capital_eligible=false` for every state, including `ACTIVE_LIMITED`. These stages SHALL NOT enable real capital or a live broker endpoint. Live admission requires a separate future deployment and specification change.

#### Scenario: Active internal simulation

- **WHEN** a qualified challenger becomes ACTIVE_LIMITED
- **THEN** it becomes the active internal-paper baseline and receives no real-money authority

### Requirement: Versioned active and challenger lifecycle

The platform SHALL represent every strategy version using the lifecycle states `RESEARCH`, `LAB_VALIDATED`, `SHADOW`, `PAPER`, `CHALLENGER`, `ACTIVE_LIMITED`, `DEMOTED` and `RETIRED`. A transition SHALL create immutable evidence referencing the strategy version, parent lineage, protocol, evaluation evidence, actor and timestamp. Historical strategy artifacts SHALL NOT be mutated by a transition.

#### Scenario: Challenger becomes active

- **WHEN** an operator approves a challenger with completed matched comparison and forward evidence
- **THEN** the platform records an immutable `CHALLENGER → ACTIVE_LIMITED` transition and retains the formerly active version

#### Scenario: Active strategy degrades

- **WHEN** a declared monitoring breach occurs for an active strategy
- **THEN** the platform records a demotion event and prevents new capital allocation until a permitted transition occurs

### Requirement: Matched active-challenger comparison

Promotion from `CHALLENGER` to `ACTIVE_LIMITED` SHALL require a comparison that fixes dataset identity, code/runtime version, evaluation protocol, transaction-cost assumptions and observation period for both versions. A PASS verdict alone SHALL NOT imply capital admission.

#### Scenario: Incomparable benchmark

- **WHEN** a proposed challenger comparison uses a different dataset or protocol than its active baseline
- **THEN** the platform rejects the promotion evidence as incomparable

### Requirement: Operator-controlled capital transitions

Research agents and implementation agents SHALL NOT perform a transition into `PAPER`, `CHALLENGER` or `ACTIVE_LIMITED`. Only the operator control plane may approve those transitions after the required evidence exists.

#### Scenario: Ouroboros requests promotion

- **WHEN** an Ouroboros-created artifact requests transition to `ACTIVE_LIMITED`
- **THEN** the control plane denies the request and preserves the current lifecycle state
