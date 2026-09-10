# Autonomous Research

## Purpose

Bounded literature-to-program research with truthful external integration readiness.

## Requirements
### Requirement: Bounded autonomous research
The system SHALL persist the evidence, generated program, provider usage, dataset identity and terminal outcome of every admitted autonomous attempt.

#### Scenario: Provider refuses or a worker is interrupted
- **WHEN** generation fails or a lease expires
- **THEN** the attempt is retained with an explicit failure outcome and no capital admission

### Requirement: Generated source confinement
The system SHALL reject source outside the versioned strategy grammar and SHALL expose only historical input to each signal computation.

#### Scenario: Source requests host capabilities
- **WHEN** a program contains an import, attribute access, dynamic execution or unsupported control flow
- **THEN** validation rejects it before any signal is evaluated

### Requirement: Truthful integration readiness
The system SHALL distinguish installed capabilities, configured external connections and observed successful runs.

#### Scenario: OpenAI credentials absent
- **WHEN** an operator views readiness or requests a campaign
- **THEN** the missing configuration is reported without substituting a deterministic candidate

### Requirement: Continuous paper risk monitoring
The forward simulator SHALL monitor held positions and quote freshness even if a daily bar has already been consumed. A risk breach SHALL persist an execution halt.

#### Scenario: Stale quote without a new bar
- **WHEN** a repeated bar is accompanied by an expired quote
- **THEN** the simulator records a halt before returning an idempotency result

### Requirement: External cancellation reconciliation
The paper outbox SHALL cancel an unsent order locally and reconcile submitted orders without resubmitting them. Every observation MUST match the immutable original intent.

#### Scenario: Fill races with cancellation
- **WHEN** the broker acknowledges cancellation but reports a completed fill
- **THEN** the outbox records the fill and does not assume cancellation prevented execution

### Requirement: Controlled research revision adoption
The system SHALL retain proposed research instructions and matched-budget benchmarks. Only an operator SHALL adopt a revision after the preregistered comparison rule is satisfied.

#### Scenario: Reflection worker is lost
- **WHEN** a worker lease expires during an instruction proposal
- **THEN** the reserved attempt is closed as interrupted without an automatic paid retry or promotion
