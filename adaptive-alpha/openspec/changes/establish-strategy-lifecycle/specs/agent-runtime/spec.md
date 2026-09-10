## ADDED Requirements

### Requirement: Registered implementation artifacts

The platform SHALL register every Ouroboros-created strategy implementation, skill, subagent and harness as an immutable artifact with parent identities, source digest, runtime digest, declared input/output schema, explicit capability allowlist, creator identity, budget and evaluation evidence.

#### Scenario: Undeclared capability

- **WHEN** an implementation artifact requests an undeclared or protected capability
- **THEN** the platform rejects the artifact before it is usable by research workflows

### Requirement: Protected control-plane exclusion

An Ouroboros engineering workspace SHALL NOT receive credentials or write authority for hidden evaluation, risk policy, capital transitions, broker execution, production secrets or audit mutation.

#### Scenario: Generated risk change

- **WHEN** an Ouroboros work result contains a change targeting the risk control plane
- **THEN** the platform rejects the result from the engineering-artifact registry
