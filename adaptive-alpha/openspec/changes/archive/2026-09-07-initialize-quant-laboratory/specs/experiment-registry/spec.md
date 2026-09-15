## ADDED Requirements

### Requirement: Attempt retention
The platform SHALL persist each attempt before evaluation, including failed, duplicate, cancelled and interrupted attempts.

#### Scenario: Evaluator outage
- **WHEN** evaluation is unavailable after attempt admission
- **THEN** the attempt remains stored and an ERROR terminal result is retained when the orchestrator remains alive

### Requirement: Reproducible metadata
Every terminal experiment SHALL reference strategy, dataset, feature, evaluator, seed, code and dependency versions.

#### Scenario: Reproduction request
- **WHEN** an operator inspects an experiment
- **THEN** the public data content hash and template artifact are available

### Requirement: Database immutability
Records and audit events MUST reject UPDATE and DELETE through database triggers.

#### Scenario: Rewrite attempted
- **WHEN** a writer tries to delete a failed experiment
- **THEN** the database aborts the mutation
