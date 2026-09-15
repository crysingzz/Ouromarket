## ADDED Requirements

### Requirement: Explicit bounded full-text acquisition

A campaign SHALL default to abstract-only literature retrieval. An operator MAY request available arXiv HTML. Under that policy, the platform SHALL derive a fixed arXiv HTML endpoint from a validated arXiv identity, refuse redirects and other origins, require HTML, bound the response and retain only inert plain text. An invalid publication identity SHALL be discarded. An HTML retrieval failure for a valid publication SHALL retain its abstract without claiming full-text acquisition.

#### Scenario: arXiv HTML is available

- **WHEN** an opted-in arXiv result has a valid identity and a bounded HTML response
- **THEN** its Evidence records full-text level, bounded plain text, exact derived source URL and reported license

#### Scenario: full text cannot be trusted

- **WHEN** status, content type, response size or extracted text validation fails for a valid publication
- **THEN** the publication remains abstract-level evidence and no full-text origin is asserted

#### Scenario: publication identity is invalid

- **WHEN** an arXiv result does not identify an allowed arXiv abstract URL
- **THEN** it is discarded before any derived full-text request or Evidence record is created

### Requirement: Truthful replication coverage

The evidence packet SHALL bind the full-text policy in its content-addressed identity. A replication packet SHALL report available evidence only when every retained source contains full text and SHALL continue to report unverified formulas, tables and parameters.

#### Scenario: only some sources have full text

- **WHEN** a replication packet contains both full-text and abstract-only evidence
- **THEN** it reports `REPLICATION_EVIDENCE_INCOMPLETE` with `FULL_TEXT_INCOMPLETE`
