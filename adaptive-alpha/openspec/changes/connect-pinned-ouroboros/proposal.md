# Connect the pinned upstream Ouroboros runtime

## Why

The engineering HTTP adapter has only been accepted against controlled responses. The user requires the actual source runtime to become a reproducible sibling dependency, with task workspaces separate from the financial application.

## What Changes

- Pin Ouroboros 6.114.0 as a Git submodule; build the headless server using its own uv lock.
- Add an authenticated, network-isolated protocol bootstrap deployment with the real upstream task handlers.
- Provision one Git workspace per frozen WorkOrder and reject scope widening.
- Add service credentials and workspace response binding to the existing adapter.
- Check runtime readiness before invoking the paid researcher.
- Test actual upstream health/workspaces and the unconfigured-pool refusal; test task contracts with selected upstream fixtures without a model.

## Impact

The bootstrap profile deliberately has no execution readiness, model credentials or external network. Model execution, gVisor acceptance and actual generated artifacts remain pending. Existing native-tool runner and financial authority separation are preserved.
