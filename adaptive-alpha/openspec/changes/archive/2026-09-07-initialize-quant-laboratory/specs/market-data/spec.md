## ADDED Requirements

### Requirement: Point-in-time availability
The platform SHALL validate symbol-time uniqueness, finite positive prices, sorted observations and availability metadata before supported evaluation.

#### Scenario: Late feature input
- **WHEN** a bar is available later than the supported close-time signal
- **THEN** evaluation rejects the unsupported look-ahead input

### Requirement: Dataset identity
Each dataset SHALL have content hash, schema hash, source and version, and synthetic data MUST be visibly labelled.

#### Scenario: Dataset content changes
- **WHEN** a bar changes while the schema stays the same
- **THEN** the content hash changes
