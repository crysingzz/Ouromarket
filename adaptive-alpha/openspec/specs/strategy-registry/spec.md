# Strategy Artifacts and Admission

## Purpose

Platform contract for strategy artifacts and admission. Initial implementation and target-only requirements are distinguished in docs/STATUS.md.

## Requirements

### Requirement: Immutable lineage
Each strategy artifact SHALL have a host identity, version, specification and explicit parent identities.

#### Scenario: Strategy mutation
- **WHEN** a child is created
- **THEN** the parent stays unchanged and the child references its parents

### Requirement: Controlled capital stages
The initial platform SHALL expose only synthetic demo-paper admission; live, shadow, canary and own-capital transitions are unavailable.

#### Scenario: Agent requests admission
- **WHEN** research identity requests paper admission
- **THEN** the API denies the operation

### Requirement: Validation before paper
The platform MUST require a successful trusted evaluation before operator paper admission.

#### Scenario: Failed strategy admission
- **WHEN** the operator requests paper for a rejected candidate
- **THEN** admission is denied
