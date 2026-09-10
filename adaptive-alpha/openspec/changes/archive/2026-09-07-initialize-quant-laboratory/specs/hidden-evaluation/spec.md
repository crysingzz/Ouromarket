## ADDED Requirements

### Requirement: Minimal feedback
The hidden evaluation service SHALL return only PASS or FAIL and a bounded score to the research control plane.

#### Scenario: Hidden submission
- **WHEN** an authenticated candidate is evaluated
- **THEN** raw hidden data, gates, equity curves and detailed metrics stay in the private ledger

### Requirement: Persistent query budget
The hidden evaluator SHALL enforce a persistent global query budget and idempotent experiment identities.

#### Scenario: Adaptive querying exceeds budget
- **WHEN** the configured query limit has been reached
- **THEN** new experiment identities are rejected while identical retries return their original result

### Requirement: Deployment isolation
The hidden service MUST have no host-published port and its private volume and data seed MUST NOT be mounted into the API service.

#### Scenario: Research service compromise boundary
- **WHEN** a research API client attempts direct hidden storage access
- **THEN** no hidden filesystem or service credential is exposed by research endpoints
