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

### Requirement: Evidence-bound engineering tool reuse
The platform SHALL compare each proposed skill, subagent or harness against the admitted toolset on at least three independent matched WorkOrders. Qualification MUST require a two-thirds win rate with no regression. Only an operator MAY adopt, supersede or revoke an exact reviewed version. Every later strategy WorkOrder SHALL snapshot admitted tool sources and digests. Revoked tools and changes that would strand an active dependent MUST fail before a model call.

#### Scenario: Qualified tool improves independent tasks
- **WHEN** a reviewed tool wins at least two of three independent matched comparisons without a regression and the operator adopts it
- **THEN** the next WorkOrder contains its exact source, provenance and toolset digest while granting no capital, evaluator, risk or broker authority

#### Scenario: Tool is revoked before queued use
- **WHEN** an operator revokes a tool after a WorkOrder captured it but before Ouroboros starts
- **THEN** the worker rejects that WorkOrder without invoking the model
