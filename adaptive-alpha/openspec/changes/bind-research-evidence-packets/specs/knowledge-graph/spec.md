## ADDED Requirements

### Requirement: Tamper-evident extractive evidence

The knowledge service SHALL retain deterministic source-version identities and bounded passages whose identity covers the source hash, field, exact offsets and text. Retrying the same source version SHALL reuse the retained retrieval record. A changed source version SHALL receive a different identity or fail on an identity conflict.

#### Scenario: Passage or source changes

- **WHEN** a retained passage text, source hash, provider identity or content level no longer matches its packet
- **THEN** packet verification fails and the source cannot support a WorkOrder

### Requirement: Evidence text has no authority

Retrieved titles, abstracts, full text and passages SHALL remain untrusted evidence data. They SHALL NOT grant permissions, alter system instructions, select capabilities or obtain evaluator, risk, capital or broker authority.

#### Scenario: Publication contains an instruction

- **WHEN** retrieved text asks the agent to ignore instructions or submit an order
- **THEN** the text remains a quoted passage and grants no authority
