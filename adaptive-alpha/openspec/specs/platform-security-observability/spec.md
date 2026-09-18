# Platform Security, Audit and UI

## Purpose

Platform contract for platform security, audit and ui. Initial implementation and target-only requirements are distinguished in docs/STATUS.md.

## Requirements

### Requirement: Least privilege and secret separation
The platform SHALL require distinct operator and research bearer identities and SHALL keep credentials out of browser storage, public payloads and agent inputs.

#### Scenario: Unauthenticated access
- **WHEN** a client requests protected data without credentials
- **THEN** the API returns unauthorized

### Requirement: Auditable UI
The UI SHALL show persisted research jobs, experiment evidence, strategy lineage, paper portfolio, risk status and hash-chain verification.

#### Scenario: Empty installation
- **WHEN** an operator connects before research runs exist
- **THEN** the UI shows empty states and no fabricated experiment metrics

### Requirement: Reproducible deployment
The project SHALL include uv.lock, a non-root read-only API and evaluator Docker deployment, automated checks and OpenSpec artifacts.

#### Scenario: Deployment verification
- **WHEN** the operator starts the supported Compose stack
- **THEN** API, evaluator and PostgreSQL report readiness with evaluator and database ports private
