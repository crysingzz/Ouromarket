# Budgeted Research Orchestration

## Purpose

Platform contract for budgeted research orchestration. Initial implementation and target-only requirements are distinguished in docs/STATUS.md.

## Requirements

### Requirement: Bounded research jobs
The platform SHALL persist research objectives, immutable budgets, identities and lifecycle events before running experiments.

#### Scenario: A job is started
- **WHEN** a CREATED job is submitted
- **THEN** the job becomes RUNNING and every admitted attempt consumes its experiment budget

### Requirement: Cancellation and interrupted attempts
The platform SHALL preserve attempts when work is cancelled or a process fails.

#### Scenario: Cancellation during a run
- **WHEN** a running job is cancelled
- **THEN** the current attempt is retained and no next generation is admitted
