## ADDED Requirements

### Requirement: Lagged after-cost evaluation
The initial evaluator SHALL calculate daily lagged template returns with explicit costs, public OOS, time folds and a declared multiplicity penalty.

#### Scenario: Future prices changed
- **WHEN** prices after time t are modified
- **THEN** returns through time t remain identical

### Requirement: Transparent statistical limits
The initial protocol SHALL identify synthetic data and SHALL report DSR and PBO as unavailable rather than substituting another statistic.

#### Scenario: Synthetic candidate passes
- **WHEN** all demo gates pass
- **THEN** the result remains ineligible for real capital

### Requirement: Protocol identity
Every evaluation SHALL reference an immutable protocol version.

#### Scenario: Evaluation repeated
- **WHEN** the same dataset, specification, protocol and trial count are used
- **THEN** the public result is identical
