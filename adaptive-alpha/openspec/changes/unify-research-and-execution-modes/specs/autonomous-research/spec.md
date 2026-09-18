## ADDED Requirements

### Requirement: Fixed-specification engineering route

Ordinary campaigns and benchmark arms SHALL use the research-spec-ouroboros-v1 generation path. The researcher SHALL freeze the economic specification before the separate Ouroboros engineer implements it. The API SHALL reject selection of the former combined OpenAI hypothesis/code path. Existing immutable campaigns SHALL remain readable; a queued request selecting a retired path SHALL terminate explicitly before invoking generation or literature providers.

#### Scenario: Default campaign

- **WHEN** an operator omits the engineer field
- **THEN** the request selects Ouroboros and generates an implementation through a frozen ResearchSpec

#### Scenario: Retired execution route

- **WHEN** an old queued request selects the combined generator
- **THEN** the worker records RETIRED_GENERATION_PATH without rewriting the original request or calling a provider

### Requirement: Controlled fixture provenance

Injected in-process generators SHALL label their attempts and candidate artifacts controlled-fixture. The production worker SHALL NOT supply such a generator, and the public API SHALL NOT accept a generator or caller-selected generation provenance. New campaigns and candidates SHALL explicitly retain internal-paper scope and capital_eligible=false.

#### Scenario: Offline integration fixture

- **WHEN** a trusted acceptance script supplies a controlled generator
- **THEN** the retained attempt and candidate identify fixture generation and cannot claim an actual Ouroboros implementation
