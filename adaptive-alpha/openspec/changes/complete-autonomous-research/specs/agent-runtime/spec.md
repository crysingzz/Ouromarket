## MODIFIED Requirements

### Requirement: Generated code confinement
The platform SHALL execute trusted templates and interpret generated signal-python-v1 programs as bounded numeric AST data. It MUST NOT import or execute generated source natively. A future arbitrary Python runtime MUST use a separately hardened sandbox.

#### Scenario: Arbitrary candidate code
- **WHEN** an agent proposes source code
- **THEN** the validator rejects unsupported capabilities before evaluation and never imports the candidate
