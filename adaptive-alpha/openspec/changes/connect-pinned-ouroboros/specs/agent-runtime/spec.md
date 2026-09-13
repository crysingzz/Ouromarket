## ADDED Requirements

### Requirement: Pinned upstream source deployment

The platform SHALL retain the original Ouroboros source as a separate Git submodule pinned to a full upstream commit. Its Docker image SHALL use the upstream lock and SHALL NOT include Adaptive Alpha source, credentials, hidden datasets or a host Docker socket. Bootstrap protocol acceptance SHALL run the actual upstream task handlers and SHALL be labelled separately from model execution.

#### Scenario: Reproducible checkout

- **WHEN** a fresh checkout initializes submodules
- **THEN** it obtains the recorded upstream commit and bootstrap rejects modified or mismatched source

### Requirement: Authenticated frozen workspaces

Task transport SHALL carry a dedicated service credential. The runtime SHALL allocate a separate Git workspace per WorkOrder, validate the frozen spec hash and reject paths outside its workspace root. The alpha adapter SHALL verify the returned work identity, spec hash and workspace before task submission. The public integration surface SHALL NOT expose owner settings or provider changes.

#### Scenario: Wrong workspace returned

- **WHEN** provisioning returns a different path or identity
- **THEN** the adapter refuses to create the engineering task

#### Scenario: Unauthorized request

- **WHEN** a caller omits the service credential
- **THEN** all operations except health are denied, including loopback callers

### Requirement: Readiness before research spend

An ordinary campaign configured for the integrated runtime SHALL check execution readiness before invoking its researcher model. A healthy bootstrap server SHALL report execution unready and SHALL NOT be accepted as an available engineer.

#### Scenario: Protocol-only service

- **WHEN** the runtime has no admitted execution profile
- **THEN** the campaign fails before spending researcher tokens, while explicit protocol acceptance can exercise task admission and cancellation

### Requirement: Durable engineering attempt history

Every WorkOrder dispatch SHALL create an immutable engineering-attempt record before the
runtime call. State changes, budget, failure code, accepted bundle and benchmark identity
SHALL be append-only records. The operator API and UI SHALL expose the retained state without
receiving the runtime service credential. Provider exception text SHALL NOT be retained.

#### Scenario: Contract validation fails

- **WHEN** Ouroboros returns a strategy that fails the frozen acceptance cases
- **THEN** the engineering attempt ends as FAILED with a bounded reason code and remains auditable

#### Scenario: Runtime is protocol-only

- **WHEN** the worker probes a configured runtime whose execution profile is not admitted
- **THEN** the UI reports it as connected but unavailable without exposing credentials

### Requirement: Idempotent runtime task identity

Each WorkOrder SHALL map to one deterministic runtime task identifier. The gateway SHALL
reject a different identifier for that workspace. A repeated create that reports an existing
task MAY resume polling only when the retained task identifier and workspace both match;
otherwise the adapter SHALL fail closed.

#### Scenario: Delivery result is ambiguous

- **WHEN** a retry receives an already-exists response for the same WorkOrder task
- **THEN** it reads and resumes the bound task instead of creating a second model execution

#### Scenario: Existing task belongs to another workspace

- **WHEN** the retained runtime task reports a different workspace
- **THEN** the adapter rejects the result as an identity conflict

### Requirement: Separately leased engineering delivery

The research campaign SHALL enqueue a retained engineering attempt and wait for its immutable
result. A dedicated engineering worker SHALL claim that attempt under a lease which is distinct
from the campaign lease. An expired delivery SHALL be reclaimed using the same WorkOrder and
deterministic runtime task identity. Accepted bundles and server benchmarks SHALL be reused after
a worker restart. Queue completion and the terminal attempt event SHALL be committed atomically.

#### Scenario: Engineering worker stops after runtime completion

- **WHEN** its lease expires after the bundle was retained but before the attempt was completed
- **THEN** another worker reuses the bundle, completes the benchmark and does not invoke the model again

#### Scenario: Cancellation races with successful completion

- **WHEN** a campaign or operator requests cancellation while the engineering lease is active
- **THEN** the worker cannot commit success and propagates cancellation to the bound runtime task

### Requirement: Crash-safe campaign reconstruction

An expired research campaign SHALL resume only from retained generations whose result is terminal
and from at most one open generation whose engineering attempt is SUCCEEDED. The resumed generation
SHALL reuse the original candidate implementation, WorkOrder, accepted bundle, server benchmark and
recorded model usage without another researcher or Ouroboros call. Every retained identity, campaign
binding, spec hash, runtime digest, input digest and trusted benchmark producer SHALL match before
reconstruction. Ambiguous, incomplete, duplicated or conflicting state SHALL fail closed.

#### Scenario: Campaign worker stops after engineering completion

- **WHEN** its lease expires after a verified bundle and benchmark were retained but before candidate evaluation completed
- **THEN** another worker reconstructs the candidate and evaluates it once without another model or runtime call

#### Scenario: Recovery state is ambiguous

- **WHEN** an open generation has no verified engineering result or any retained identity or digest conflicts
- **THEN** the campaign becomes INTERRUPTED and no external call is replayed automatically

#### Scenario: All generations were already evaluated

- **WHEN** the campaign lease expires after every generation has a supported terminal result but before finalization
- **THEN** another worker rebuilds diagnostics and finalizes the campaign without generating another candidate
