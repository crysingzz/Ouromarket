# Design

See [ADR 0002](../../../docs/adr/0002-isolated-native-tools.md) for the boundary and threat model, and [runner operation](../../../docs/RUNNER.md) for build, acceptance and recovery.

The trusted controller accepts source plus JSON values, snapshots and hashes the request, and chooses all container settings itself. A one-job image uses a root PID 1 supervisor solely to create an unprivileged child and enforce deadlines; the child runs without inherited secrets, groups, network or host mounts. Only a trusted operator supplies a pinned local image ID. An agent cannot select runtime, image, entrypoint, environment, mounts or resource ceilings.

The host also enforces time and cancellation, bounds and validates the supervisor result, then force-removes the container. Results are execution reports, not quality or investment approvals. Unknown creation and failed removal quarantine the controller. Recovery removes expired containers with this protocol's ownership labels; quarantine requires operator inspection and a fresh controller.

The library is not mounted into application services with a Docker socket. The operator API snapshots a reviewed harness and bounded JSON input into a durable run. A separate trusted worker on the database-only network owns the Docker daemon socket, recovers the controller before claiming work, materializes the exact reviewed source, propagates cancellation and retains a provenance-checked result. Expired leases can be resumed, while lease fencing prevents a stale worker from publishing. Skills, subagent descriptions and strategy programs remain data; this workflow validates only harness tools and never grants capital authority.

CI's runc fixture acceptance exercises real process/resource mechanics but does not accept hostile generated Python for production. The native-tool worker is therefore an opt-in Compose profile and remains inactive until an operator supplies a pinned runner image on a host whose runsc boundary has passed independent acceptance.
