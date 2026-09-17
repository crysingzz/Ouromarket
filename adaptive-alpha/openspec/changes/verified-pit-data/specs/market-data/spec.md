## MODIFIED Requirements

### Requirement: Point-in-time availability

The platform SHALL refuse caller assertions of point-in-time verification. It SHALL grant a verified status only to a server-validated immutable revision ledger that records event, publication and receipt times and exact correction lineage. Every derived snapshot SHALL select only revisions received by its declared cutoff and SHALL bind the exact selected revision identities.

#### Scenario: Late correction arrives

- **WHEN** an observation is corrected after an earlier snapshot cutoff
- **THEN** the earlier snapshot retains the original revision and a later snapshot may select the correction without mutating the earlier record

#### Scenario: Generic upload claims verification

- **WHEN** an ordinary dataset upload sets its point-in-time flag
- **THEN** the server rejects it and requires a verified revision ledger

#### Scenario: Late feature input

- **WHEN** a bar is available later than the supported close-time signal
- **THEN** evaluation rejects the unsupported look-ahead input

### Requirement: Dataset identity

Each verified revision ledger SHALL have content identity, provider dataset identity, declared usage rights, calendar and timezone, and a versioned adjustment policy. Each materialized dataset SHALL bind its source ledger, verification report, cutoff and selected revision identities, and synthetic data MUST remain visibly labelled.

#### Scenario: Revision or adjustment rule changes

- **WHEN** a source value, source sequence or adjustment-policy version changes
- **THEN** the ledger or derived dataset identity changes

#### Scenario: Dataset content changes

- **WHEN** a bar changes while the schema stays the same
- **THEN** the content hash changes

## ADDED Requirements

### Requirement: Revision-chain integrity

For one event, revisions SHALL be consecutively numbered, SHALL have strictly increasing receipt times and SHALL identify the exact immediately preceding source sequence. Source sequences SHALL be unique within a ledger.

#### Scenario: Correction skips or names the wrong predecessor

- **WHEN** a revision is missing, duplicated or points to a different predecessor
- **THEN** import fails before a verification report or dataset snapshot is created
