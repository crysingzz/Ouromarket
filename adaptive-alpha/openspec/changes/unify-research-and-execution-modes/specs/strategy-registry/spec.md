## ADDED Requirements

### Requirement: Evidence-bound internal recovery

An operator SHALL be able to request diagnostic revalidation of an immutable candidate returned from DEMOTED to RESEARCH. The service SHALL bind the new public and hidden result to the source hash, dataset and current demotion epoch. A PASS SHALL NOT automatically transition or resume the strategy. Revalidation SHALL retain the existing data identity and SHALL NOT claim new independent market evidence.

#### Scenario: Repeat and interrupted evaluation

- **WHEN** the same request is repeated
- **THEN** the server returns its completed result or rejects concurrent work
- **AND** recovery after an expired lease reuses the hidden evaluation identity and fences late responses
- **AND** evaluation runs outside the journal transaction

#### Scenario: Changed lifecycle during evaluation

- **WHEN** the lifecycle version changes while revalidation runs
- **THEN** the result is retained as STALE and cannot authorize recovery

### Requirement: Preserve account and require fresh competition

Recovery SHALL require renewed public/hidden proof and an explicit operator SHADOW/PAPER transition. A global risk halt SHALL block recovery. Restoring the internal account SHALL preserve cash, positions, high watermark, day-start NAV and consumed bars; a retained recovery record SHALL include its previous state. Existing risk breaches SHALL remain enforceable after recovery. New challenger admission SHALL require observations after demotion, and promotion SHALL reject comparisons belonging to a prior episode of either participant.

#### Scenario: Renewed paper account

- **WHEN** an operator resumes a newly revalidated internal account
- **THEN** its historical losses and positions remain intact and normal risk checks still apply
- **AND** the previous account state is retained in the immutable journal

#### Scenario: Prior successful comparison reused

- **WHEN** a recovered challenger or reactivated baseline is paired with an old successful comparison
- **THEN** promotion is rejected with STALE_COMPARISON_EPISODE
