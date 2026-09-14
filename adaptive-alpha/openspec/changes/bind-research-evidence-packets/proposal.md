# Bind research departments to immutable evidence packets

## Why

Replication and novel campaigns previously shared the same abstract-only literature context and differed mainly by a prompt field. A frozen implementation specification needs exact source versions, extractive citation anchors and explicit evidence gaps before Ouroboros receives it.

## What Changes

- Assign deterministic identities to retrieved source versions and reuse their retained retrieval record.
- Persist one content-addressed evidence packet containing search scope, provider health, source hashes, bounded passages and department-specific gaps.
- Require real researcher specifications to cite exact packet passages and acknowledge every packet gap.
- Verify sources, passages, department and gaps again before creating a WorkOrder.
- Expose packets and candidate bindings through authenticated API and operator UI.

## Impact

This increment supports metadata, abstracts and explicitly imported full text. The current external connectors retrieve metadata and abstracts only, so replication status remains incomplete. It does not verify scientific novelty, equations, tables or parameter extraction and does not add capital authority.
