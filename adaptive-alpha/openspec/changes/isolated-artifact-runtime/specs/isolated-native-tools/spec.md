## ADDED Requirements

### Requirement: Fixed isolation policy

Submitted native source SHALL require a pinned image ID and a configured runsc runtime. The trusted controller SHALL select a read-only root filesystem, private bounded tmpfs, no network, no host mounts, no inherited secrets, unprivileged child UID, process/CPU/memory/file/output/time ceilings and no restart. Caller fields outside the source/JSON/resource-within-ceilings contract SHALL be rejected. Development runc SHALL expose only fixed trusted fixtures through its public interface.

#### Scenario: Missing production runtime

- **WHEN** runsc is unavailable
- **THEN** submitted source is rejected before container creation without fallback

#### Scenario: Attempted authority access

- **WHEN** a fixed acceptance tool tries sensitive paths, root writes, network access or signalling its watchdog
- **THEN** the checks report denied access and the watchdog remains effective

### Requirement: Bounded execution and complete cleanup

The supervisor SHALL bound stdout and stderr together and parse only a JSON result. The controller SHALL bind the envelope to the request and protocol, enforce cancellation/deadline and force-remove the complete container. Failed deletion or ambiguous creation SHALL quarantine further work. Expired-container recovery SHALL select only this protocol's containers and SHALL NOT silently clear quarantine.

#### Scenario: Forking or hanging tool

- **WHEN** a tool exhausts time or cancellation arrives with child processes running
- **THEN** the job terminates and container removal is confirmed, otherwise new work is blocked

#### Scenario: Lost create response

- **WHEN** Docker may have created a container but its response is lost
- **THEN** the controller attempts deletion by the reserved name and remains quarantined even after a not-found response

### Requirement: Honest execution provenance

Results SHALL carry source/input/request/image/policy identity, runtime, fixture provenance, cleanup outcome and capital_eligible=false. Fixture acceptance SHALL NOT be described as production sandbox acceptance, strategy validation or real Ouroboros tool adoption.

#### Scenario: Development acceptance

- **WHEN** acceptance runs on Docker without gVisor
- **THEN** its report identifies development-fixed-fixtures and records the production refusal

### Requirement: Reviewed harness delivery

Only an operator SHALL enqueue a harness that has exactly one retained operator review bound to a passing server benchmark and the current engineering runtime. The application SHALL snapshot the source, input, schemas, request, review and runtime identities before execution. A separate worker SHALL own the Docker socket and SHALL NOT receive application, model, evaluator or broker secrets. Skills, subagents and strategy programs SHALL NOT become native tools through this workflow.

#### Scenario: Unreviewed artifact

- **WHEN** an agent, an unreviewed artifact or an artifact of another kind is submitted for native validation
- **THEN** the request is rejected before a runner job is claimed

#### Scenario: Reviewed harness

- **WHEN** an operator submits a reviewed harness with schema-valid JSON input
- **THEN** a durable run is retained and only the isolated worker can materialize the exact bound request

### Requirement: Durable native-tool lifecycle

The platform SHALL retain queue, claim, resume, cancellation and terminal events. Claims SHALL use bounded leases, an expired claim MAY be resumed with a new owner, and a stale owner SHALL NOT publish a result. Cancellation SHALL reach the running controller and SHALL prevent later success. A successful result SHALL be retained once and accepted only when its request provenance, pinned image, policy, runsc runtime, cleanup and non-capital status match the queued run.

#### Scenario: Worker interruption

- **WHEN** a worker lease expires before a terminal result is committed
- **THEN** another worker resumes the same run and the stale owner cannot append a result

#### Scenario: Operator cancellation

- **WHEN** the operator cancels a queued or running harness validation
- **THEN** the run becomes or finishes CANCELLED and cannot later become successful
