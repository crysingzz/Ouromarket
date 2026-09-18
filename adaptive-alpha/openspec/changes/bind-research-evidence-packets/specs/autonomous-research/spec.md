## ADDED Requirements

### Requirement: Department-specific immutable evidence packet

Every admitted campaign SHALL persist a content-addressed evidence packet before candidate generation. The packet SHALL bind the department, query, requested source set, exact source health, immutable source hashes, bounded extractive passages and explicit evidence gaps. A replication campaign without retained full text SHALL report incomplete replication evidence. A novel campaign SHALL report a scoped search and SHALL NOT claim verified scientific novelty.

#### Scenario: Abstract-only replication search

- **WHEN** the replication department retrieves only metadata and abstracts
- **THEN** the packet records `REPLICATION_EVIDENCE_INCOMPLETE` and the missing full text and unverified parameter gaps

#### Scenario: Novel search

- **WHEN** the novel department searches a finite set of configured providers
- **THEN** the packet records `NOVELTY_SEARCH_SCOPED`, the exact provider health and that scientific novelty remains unverified

### Requirement: Exact citation binding before implementation

A real researcher SHALL cite exact passage identities from its campaign evidence packet and acknowledge every retained packet gap. Before creating a WorkOrder, the platform SHALL revalidate the packet identity, underlying Evidence records, exact text offsets, source hashes, department, citations and gaps.

#### Scenario: Researcher invents a citation

- **WHEN** a ResearchSpec cites a passage identity absent from the frozen packet
- **THEN** WorkOrder creation fails before Ouroboros receives the specification

#### Scenario: Researcher omits a limitation

- **WHEN** a ResearchSpec does not retain every evidence gap declared by the packet
- **THEN** WorkOrder creation fails before implementation
