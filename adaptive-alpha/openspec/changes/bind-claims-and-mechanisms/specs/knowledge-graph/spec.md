## ADDED Requirements

### Requirement: Passage-bound research claims

Every evidence-backed ResearchSpec SHALL express at least one bounded claim whose `supports` or `contradicts` relation names an exact cited passage in its immutable evidence packet. WorkOrder admission SHALL revalidate the source version, passage identity and claim binding before retaining the claim.

#### Scenario: Researcher asserts support

- **WHEN** a ResearchSpec says a passage supports an economic proposition
- **THEN** the graph retains the proposition, relation, exact passage, source version, WorkOrder and spec hash

#### Scenario: Claim anchor is invented

- **WHEN** a claim names a passage or source absent from the frozen packet and citation set
- **THEN** WorkOrder creation fails before Ouroboros receives the specification

### Requirement: Anchor verification is distinct from semantic verification

The platform SHALL distinguish a verified extractive anchor from an independently verified scientific meaning. A retained model-authored claim SHALL have `semantic_status=researcher_asserted`, SHALL NOT be marked semantically verified and SHALL grant no authority.

#### Scenario: Exact passage is retained

- **WHEN** byte-level source and passage checks pass
- **THEN** the graph may mark the anchor verified but keeps the claim's semantic verification false
