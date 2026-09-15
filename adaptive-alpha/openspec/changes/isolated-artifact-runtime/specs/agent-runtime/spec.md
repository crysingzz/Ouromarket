## MODIFIED Requirements

### Requirement: Generated code confinement

The application SHALL execute trusted templates and interpret generated signal-python-v1 programs as bounded numeric AST data. Application, evaluator, research and broker processes MUST NOT import or execute generated source natively. Native engineering tools SHALL use the separate isolated-native-tools protocol with mandatory production sandbox gates. Default strategy evaluation SHALL NOT automatically adopt native tools or expand its interpreter capabilities.

#### Scenario: Arbitrary candidate code

- **WHEN** an agent submits unsupported source as a signal-python-v1 candidate
- **THEN** evaluation rejects it without importing or executing it natively

#### Scenario: Separate native tool

- **WHEN** a trusted controller receives an engineering tool request
- **THEN** it requires the native sandbox profile and does not give the tool access to application authority
