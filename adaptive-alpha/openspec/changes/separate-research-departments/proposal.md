# Separate research department workflows

## Why

Campaigns already carry a replication or novel label, but one undifferentiated worker claims both queues and publishes one shared readiness heartbeat. Department rules are spread across evidence and novelty code, while retained research context is not represented as a department-owned, auditable input. This falls short of the planned two-department laboratory and makes operational isolation hard to verify.

## What Changes

- Freeze a server-owned department policy and campaign-local token budget identity when a campaign is created.
- Run replication and novel workers with fixed identities that can claim only their own durable queue.
- Retain bounded outcome memory under the producing department and provide only same-department memory to later researcher contexts.
- Centralize department result checks: replication stays source-bound and records evidence gaps; novel work records its searched scope and rejects prior external mechanism identity.
- Expose both worker heartbeats, queue counts, policy identities and non-capital authority through the authenticated API and operator UI.
- Run two hardened Docker worker services with the same restricted service credentials and distinct department settings.

## Impact

This change separates research operations and evidence semantics. It does not create a second OpenAI authority, prove formulas or novelty, enable model execution, alter independent evaluation, or grant broker and capital permissions.
