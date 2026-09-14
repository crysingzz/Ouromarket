## Source and transport foundation

- [x] Pin the original upstream source as a sibling Git submodule.
- [x] Build a headless Docker image with the upstream uv lock and separate state/workspace volumes.
- [x] Add authenticated scoped task access and frozen per-WorkOrder Git workspaces.
- [x] Extend the alpha adapter with service authentication, workspace identity checks and readiness gating.
- [x] Accept real upstream health/workspace and unconfigured-pool refusal locally; add the same acceptance to CI.
- [x] Verify worker connectivity and retained application behavior on the local stand.

## Executing engineering loop

- [ ] Configure the chosen OpenAI model and a secret-backed credential path in a separately admitted execution profile.
- [ ] Accept the executing Ouroboros and native tools under gVisor with inherited limits.
- [ ] Run an actual frozen WorkOrder through the model and collect versioned strategy/skill/subagent/harness artifacts.
- [x] Retain append-only engineering attempts, budgets, terminal state, audit and operator UI.
- [x] Bind one deterministic upstream task identity to each WorkOrder and safely resume an already-created matching task.
- [x] Propagate campaign cancellation and lease loss through polling to the upstream task cancel endpoint.
- [x] Add a separately leased engineering queue with crash-safe task resumption and explicit cancellation propagation.
- [x] Reconstruct an expired campaign from verified retained engineering and candidate results without repeating model work.
- [x] Add independent matched qualification, operator adoption/revocation and immutable admitted-tool snapshots in future WorkOrders.
- [ ] Benchmark and admit reusable tools and self-improvement against independent engineering tasks.

These pending tasks retain the distinction between a running source server and a completed self-creating engineering loop.
