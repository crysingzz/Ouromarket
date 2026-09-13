## Controller foundation

- [x] Specify the isolation boundary and JSON-only contract.
- [x] Implement pinned-image/runtime gates and fixed resource policy.
- [x] Implement a separate-UID supervisor with bounded output and wall time.
- [x] Handle cancellation, ambiguous create, cleanup quarantine and expired-container recovery.
- [x] Add fault-injection unit tests without running native source on the host.
- [x] Accept fixed fixtures in real Docker and add the same check to CI.
- [x] Complete full quality checks and record verification.

## Production acceptance and integration

- [ ] Provision and independently verify runsc on the target Linux sandbox host.
- [ ] Run the boundary/resource/cancellation suite under runsc and expand adversarial testing for that host.
- [x] Integrate reviewed harness artifacts, durable task leases, attempt journaling and operator visibility without exposing the Docker socket to agents/API.
- [ ] Add separately built, locked dependency profiles when an actual tool requires packages beyond stdlib.

The remaining production-host and dependency-profile items prevent declaring the full roadmap stage or self-creating Ouroboros integration complete.
