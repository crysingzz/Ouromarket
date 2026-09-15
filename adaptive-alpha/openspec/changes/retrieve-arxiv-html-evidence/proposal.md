# Retrieve bounded arXiv HTML evidence

## Why

Replication campaigns previously stopped at abstracts even when arXiv exposed an HTML version of a paper. The operator needs an explicit way to request available full text while preserving fixed-origin retrieval, bounded inputs and honest evidence gaps.

## What Changes

- Add an immutable campaign policy choosing abstract-only search or available arXiv HTML.
- Derive the HTML endpoint only from a validated arXiv identity and refuse redirects, other origins, non-HTML responses and oversized bodies.
- Convert HTML to bounded inert plain text and retain its exact source URL and reported license.
- Discard invalid publication identities and fall back to the abstract per valid paper when its HTML is absent or invalid.
- Mark replication evidence available only when every retained source has full text; keep formulas, tables and parameters unverified.
- Expose the chosen policy and actual acquisition level through API and UI.

## Impact

This change improves the evidence supplied to the researcher and Ouroboros. It does not interpret equations, verify claims, prove reproducibility or grant any trading authority.
