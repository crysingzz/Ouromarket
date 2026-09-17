## ADDED Requirements

### Requirement: Department outcome memory provenance

Every retained department memory record SHALL identify its campaign, candidate, department, frozen policy, evidence status and mechanism identity. It SHALL declare `research-only` authority and SHALL NOT contain hidden evaluation values, strategy source or model instructions.

#### Scenario: Memory is reused by a later generation

- **WHEN** a researcher context includes prior department outcomes
- **THEN** the attempt retains the exact ordered memory record identifiers used to build that context
