# Unify research and execution modes

## Why

Campaigns can still default to a combined OpenAI hypothesis/code generator. That conflicts with the agreed separation: research freezes the economic specification, and Ouroboros implements it. Demoted internal accounts also need a complete, evidence-bound recovery path.

## What Changes

- Make ResearchSpec-to-Ouroboros the only ordinary campaign generation path.
- Reject retired queued request types without rewriting their immutable history.
- Label injected test generation explicitly and preserve internal-paper/no-capital scope.
- Complete independent revalidation and controlled internal-account recovery in a subsequent increment of this change.

## Impact

Affected capabilities: autonomous-research and strategy-registry. No external paper or live execution is enabled. Legacy provider helpers remain available for controlled reference tests but are not worker routes.
