# ADR 0001: Keep research proposals outside financial authority

Status: accepted for initial implementation. The subsequent native-tool boundary is specified in [ADR 0002](0002-isolated-native-tools.md); its production acceptance and registry integration remain pending.

The existing Ouroboros runtime can modify files and invoke tools. Importing it into an investment service would share privileges with risk, audit and broker execution. The platform is a separate package with a provider-independent EngineeringAgent contract. Future agents receive only research HTTP identity and candidate workspace access, never the host repository, database, Docker socket, hidden service credential or operator token.

The trusted API orchestrates bounded template evaluation; a separate container owns hidden data and query accounting. Real generated Python remains unsupported until an independently enforced sandbox is implemented. Production execution must only load reviewed versioned artifacts; source code returned by an agent is not an authorization object.

Consequences: more explicit integration work; fewer accidental privilege paths; the demo remains runnable without third-party credentials. A host operator still has administrative power. No software declaration of immutability can defend against an owner with Docker and DB administrator access.
