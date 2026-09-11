# Design

See [ADR 0002](../../../docs/adr/0002-isolated-native-tools.md) for the boundary and threat model, and [runner operation](../../../docs/RUNNER.md) for build, acceptance and recovery.

The trusted controller accepts source plus JSON values, snapshots and hashes the request, and chooses all container settings itself. A one-job image uses a root PID 1 supervisor solely to create an unprivileged child and enforce deadlines; the child runs without inherited secrets, groups, network or host mounts. Only a trusted operator supplies a pinned local image ID. An agent cannot select runtime, image, entrypoint, environment, mounts or resource ceilings.

The host also enforces time and cancellation, bounds and validates the supervisor result, then force-removes the container. Results are execution reports, not quality or investment approvals. Unknown creation and failed removal quarantine the controller. Recovery removes expired containers with this protocol's ownership labels; quarantine requires operator inspection and a fresh controller.

The library is not mounted into application services with a Docker socket. Connecting reviewed registry artifacts, task leases, durable attempt records and UI operations is a subsequent integration. CI's runc fixture acceptance exercises real process/resource mechanics but does not accept hostile generated Python for production.
