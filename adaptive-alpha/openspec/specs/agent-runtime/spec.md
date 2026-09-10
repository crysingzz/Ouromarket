# Agent Runtime and Engineering Isolation

## Purpose

Platform contract for agent runtime and engineering isolation. Initial implementation and target-only requirements are distinguished in docs/STATUS.md.

## Requirements

### Requirement: Replaceable engineering adapters
The platform SHALL define a provider-independent engineering contract and label deterministic reference agents separately from connected LLM runtimes.

#### Scenario: Reference mode
- **WHEN** no external provider is connected
- **THEN** the UI identifies the reference agent and records zero LLM usage

### Requirement: Generated code confinement
The platform SHALL execute trusted templates and interpret generated signal-python-v1 programs as bounded numeric AST data. It MUST NOT import or execute generated source natively. A future arbitrary Python runtime MUST use a separately hardened sandbox.

#### Scenario: Arbitrary candidate code
- **WHEN** an agent proposes source code
- **THEN** the validator rejects unsupported capabilities before evaluation and never imports the candidate
