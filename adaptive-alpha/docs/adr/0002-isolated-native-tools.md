# ADR 0002: Separate native engineering tools behind gVisor

Status: controller design accepted; target production runtime acceptance pending. Date: 2026-09-11. Refines ADR 0001's future sandbox boundary without changing strategy evaluation.

## Threat model and authority

Treat generated Python and its JSON output as hostile. A tool may try to read secrets, alter risk/evaluation code, contact services, stop its supervisor, spawn detached processes, fill storage, consume memory or forge success. The controller, Docker daemon, operator-selected image and configured runsc binary are trusted. A compromised operator/daemon/image supply chain is outside this boundary. Registering an executable under the name `runsc` is not proof of its integrity: deployment acceptance must inspect the installed runtime and host configuration.

The controller runs under a separate service identity on a dedicated Linux sandbox host. Only that trusted controller has Docker authority. Application, Ouroboros, research, evaluator and broker processes must not receive its socket. No application checkout, database, secret directory, hidden dataset, broker credential or host directory is mounted into a tool. Tool requests carry public, explicitly selected JSON data only. This increment supplies a controller library; authenticated dispatch and durable attempts are pending integration work.

## Decision

Production uses gVisor `runsc`; missing runtime fails before creating a container. gVisor's documented Docker integration supplies a userspace kernel isolation layer. Plain Docker resource settings alone are insufficient evidence for our hostile-code boundary. See the primary [gVisor Docker setup](https://gvisor.dev/docs/user_guide/quick_start/docker/) and [Docker runtime/resource settings](https://docs.docker.com/engine/containers/run/).

The separate image contains the pinned Python 3.12 base and a stdlib supervisor. Dependencies are built before execution; the initial profile installs none. Adding ML packages requires a separately reviewed locked image profile. Requests cannot install dependencies, access a package index or choose images, commands, environment, capabilities, network or mounts. The local image ID is recorded, as are request/source/input and resource-policy hashes. These hashes support identity, not authenticity or guaranteed deterministic output; native code can read clocks and randomness. Signed manifests and replay environment retention are later work.

PID 1 retains SETUID/SETGID to start UID/GID 65532 without supplementary groups, and KILL to terminate that different-UID child. The child loses these capabilities when privileges are dropped and cannot signal the supervisor. The trusted parent owns its own deadline and pipe readers; a tool cannot replace them. The container disables networking, drops other capabilities, uses no-new-privileges, read-only root, bounded tmpfs, one CPU, 192 MiB RAM without extra swap, 32 processes and bounded descriptors/files/logs/output. Docker's normal seccomp policy remains enabled. A child session is killed on completion, and full container removal covers detached descendants. Requests and results use JSON; neither host-side unpickling nor native imports occur. The controller speaks the versioned [Docker Engine API](https://docs.docker.com/reference/api/engine/version/v1.47/) over a local Unix socket.

The controller also applies an outer timeout and supports explicit cancellation. If container creation has an ambiguous response, deletion by its reserved name is attempted, but even DELETE 404 cannot rule out a delayed create. That outcome quarantines the controller. Failed cleanup also quarantines it. Recovery reaps expired protocol-owned containers; it never automatically clears quarantine. A single controller serializes local jobs. A process crash may leave a container until its watchdog exits or a recovery pass removes it; this increment does not claim an always-running external sweeper.

## Development acceptance and limitations

Docker Desktop here has no runsc. Its development interface accepts only fixed module-owned fixture programs, never caller source. Acceptance checks real process execution, inaccessible paths/network, UID separation, limits, cancellation and fresh workspaces; production refusal is exercised on the same daemon. This is not an escape-proof certification or production gVisor acceptance. Tests under runsc on the intended host, attack review, operational recovery and isolation-host monitoring remain required before dispatching generated native tools.

The controller returns an execution report. It does not adopt registry proposals, create new agent privileges, validate an economic hypothesis, grant capital or bypass risk/E1. Linking reviewed tools to Ouroboros, independent engineering benchmarks, durable provenance, budgets and UI is the next integration step.
