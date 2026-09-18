# Bind research claims and economic mechanisms

## Why

Evidence packets retain exact passages, but the current graph links those passages directly to a candidate without recording what the researcher says they support or contradict. Candidate similarity also relies on hypothesis words and program AST, so two implementations of the same economic idea can be relabelled as novel.

## What Changes

- Require evidence-backed ResearchSpecs to express bounded `supports` or `contradicts` claims against exact packet passages.
- Persist content-addressed claim records and graph edges whose anchor is verified while their economic meaning remains `researcher_asserted`.
- Require a structured economic-mechanism descriptor covering family, premise, inputs, formation horizon, holding horizon and direction.
- Derive deterministic exact and family fingerprints using server normalization.
- Treat an exact prior mechanism as a duplicate in the novel department while retaining it as explicit lineage for replication variants.
- Expose claims, mechanism family and related prior candidates in the authenticated operator API and UI.

## Impact

The researcher receives a stronger frozen contract and Ouroboros still only implements it. This change does not prove a paper's claim, verify formulas, establish scientific novelty, alter evaluation criteria or grant capital authority.
