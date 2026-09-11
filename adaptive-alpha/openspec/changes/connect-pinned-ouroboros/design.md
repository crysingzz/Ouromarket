# Design

The repository contains sibling `adaptive-alpha`, pinned `ouroboros-runtime` and `integration` directories. Upstream source remains unmodified; the Git submodule pins its exact commit. The container installs the upstream package with its separate lock and a source-snapshot Git repository. Its synthetic snapshot commit is not presented as the upstream commit; the latter is recorded explicitly in the manifest and image label.

A narrow ASGI wrapper invokes the actual upstream server. Authentication applies even on loopback. It permits health, readiness, WorkOrder workspace provisioning and scoped create/read/cancel task operations; settings, provider configuration and general runtime tools are not exposed. The runtime joins only an internal Docker network. A separate ingress proxy publishes the local API; it has no credentials or application storage. The alpha worker can join the internal network through an explicit Compose override.

Workspaces contain a committed frozen work order and live on their own volume outside the runtime repository and state directory. Repeated provisioning verifies the same work identity, spec hash and manifest; symlink and scope widening attempts fail. These are separate workspaces within one trusted bootstrap service, not accepted hostile-code tenant sandboxes. A failed Git initialization remains a conflict requiring operator inspection; it is not silently reused.

The protocol bootstrap profile cannot call a model and reports ready=false. Ordinary research checks this before spending researcher tokens. The next executing deployment requires model configuration, gVisor and budget/cancellation enforcement. A successful admission/cancellation test proves protocol interoperability, not generation, learning or investment performance.
