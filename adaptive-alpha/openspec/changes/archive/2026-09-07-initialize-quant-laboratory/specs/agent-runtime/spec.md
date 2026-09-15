## ADDED Requirements

### Requirement: Replaceable engineering adapters
The platform SHALL define a provider-independent engineering contract and label deterministic reference agents separately from connected LLM runtimes.

#### Scenario: Reference mode
- **WHEN** no external provider is connected
- **THEN** the UI identifies the reference agent and records zero LLM usage

### Requirement: Generated code confinement
The platform SHALL execute only trusted built-in templates in the initial release. The target generated-code runtime MUST be a separately hardened sandbox.

#### Scenario: Arbitrary candidate code
- **WHEN** an agent proposes source code
- **THEN** the initial API rejects unsupported execution and never imports the candidate
