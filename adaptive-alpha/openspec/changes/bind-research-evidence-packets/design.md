# Design

The controller converts each bounded fixed-origin search result into an immutable Evidence record. Its identity is derived from provider, external identity and content hash; retrieval time remains historical metadata and is reused on retry. The campaign then creates a content-addressed ResearchEvidencePacket whose identity covers the campaign, department, query, requested providers, exact provider health, source bindings, bounded extractive passages, status and gaps.

Passages carry exact field offsets and a digest over their source identity, source hash, field, offsets and text. Packet validation checks the complete binding graph. WorkOrder registration loads the packet and every retained Evidence record again, verifies the exact text slices, and requires each model-provided citation and evidence gap to match the packet. A document can appear inside a quoted passage but cannot change the fixed system instructions, capabilities or authority.

Replication packets are marked incomplete unless a source version is explicitly stored as full text. Even with full text, formulas, tables and parameters remain unverified in this increment. Novel packets describe the finite search scope and retain that scientific novelty is unverified. These states are evidence quality labels, not evaluation verdicts or trading permissions.
