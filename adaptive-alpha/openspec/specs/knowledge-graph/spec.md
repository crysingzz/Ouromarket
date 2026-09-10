# Scientific Knowledge and Provenance

## Purpose

Platform contract for scientific knowledge and provenance. Initial implementation and target-only requirements are distinguished in docs/STATUS.md.

## Requirements

### Requirement: Evidence provenance
The target platform SHALL link papers, claims, hypotheses, strategies, experiments and evidence using source identities and versions.

#### Scenario: Contradictory literature
- **WHEN** two sources disagree about a claim
- **THEN** both claims and their supporting sources remain queryable

### Requirement: Untrusted research documents
Research components SHALL treat retrieved text as evidence data and SHALL NOT derive service permissions from document instructions.

#### Scenario: Document attempts to override policy
- **WHEN** a paper contains instructions to expose hidden data
- **THEN** the instructions do not grant access or alter control policy
