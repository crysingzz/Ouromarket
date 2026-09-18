## ADDED Requirements

### Requirement: Candidate mechanism lineage

A candidate created from a real WorkOrder SHALL retain the exact mechanism descriptor and fingerprints from its ResearchSpec. Related prior mechanism identities SHALL remain queryable and SHALL NOT be inferred as proof of equivalence or profitability.

#### Scenario: Candidate has a related predecessor

- **WHEN** its normalized mechanism matches a retained candidate
- **THEN** the candidate artifact exposes the prior candidate identity and the match type without changing either artifact
