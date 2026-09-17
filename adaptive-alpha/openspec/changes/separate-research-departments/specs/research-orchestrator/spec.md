## ADDED Requirements

### Requirement: Fixed department queues

Every research worker SHALL start with one fixed department identity and SHALL claim only campaigns whose immutable department policy matches that identity. A campaign SHALL freeze its department policy and campaign-local token budget before entering the queue.

#### Scenario: Both departments have queued work

- **WHEN** a replication worker and a novel worker claim work
- **THEN** each receives only its own department campaign and each lease retains the claiming department

#### Scenario: Legacy unbound campaign is encountered

- **WHEN** a queued campaign lacks a valid frozen department policy
- **THEN** neither fixed-department worker claims it

### Requirement: Department-scoped research memory

The orchestrator SHALL retain a bounded outcome summary for completed or rejected candidate attempts and SHALL provide a later campaign only summaries from the same department. Memory SHALL exclude source code, hidden evaluation output and executable instructions and SHALL remain research-only data.

#### Scenario: Novel work follows replication work

- **WHEN** a novel campaign builds its researcher context after replication outcomes were retained
- **THEN** its memory snapshot contains no replication records

### Requirement: Server-owned department result policy

Replication work SHALL remain bound to replication evidence states and explicit gaps. Novel work SHALL retain its search scope and reject an exact external mechanism match before laboratory evaluation. Candidate artifacts SHALL record the frozen policy and applied result criterion.

#### Scenario: Department label conflicts with evidence packet

- **WHEN** a campaign attempts to evaluate a packet admitted under the other department
- **THEN** the campaign fails before the candidate reaches laboratory evaluation

### Requirement: Independent operational readiness

The authenticated readiness response SHALL expose replication and novel worker heartbeats and queue counts separately. Neither readiness state SHALL imply capital eligibility.

#### Scenario: One worker is unavailable

- **WHEN** only one department heartbeat is fresh
- **THEN** the operator sees the available and unavailable departments independently
