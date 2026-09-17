## ADDED Requirements

### Requirement: Structured economic-mechanism identity

Every real researcher specification SHALL describe its economic mechanism using a closed family and input vocabulary, bounded formation and holding horizons, direction and a premise. The server SHALL derive deterministic exact and family fingerprints from that descriptor.

#### Scenario: Cosmetic wording changes

- **WHEN** two descriptors differ only by Unicode form, capitalization, whitespace or punctuation
- **THEN** their exact mechanism fingerprints are identical

### Requirement: Department-aware mechanism reuse

The novel department SHALL treat an exact mechanism fingerprint retained outside the current campaign lineage as a duplicate. Iterations inside one campaign and replication variants MAY test another implementation of the same mechanism but SHALL retain the prior candidate identities as lineage. Program AST identity remains a separate duplicate control.

#### Scenario: Existing mechanism is relabelled as novel

- **WHEN** a novel candidate's exact mechanism fingerprint matches a retained candidate
- **THEN** evaluation records `DUPLICATE_MECHANISM` before backtesting it as a new hypothesis

#### Scenario: Publication implementation is revised

- **WHEN** a replication candidate matches an earlier mechanism but uses another implementation
- **THEN** it remains eligible for laboratory testing and records the related mechanism lineage
