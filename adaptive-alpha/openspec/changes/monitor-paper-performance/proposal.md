# Monitor active paper performance

## Why

Risk limits stop abrupt losses but do not separately record persistent deterioration after qualification. Active internal simulations need a fixed, reproducible monitoring policy, independent of researcher and engineer output.

## What Changes

- Freeze a performance admission at operator activation, referencing the exact qualifying comparison and a server-owned policy.
- Consume retained post-activation observations in sealed daily windows; warn on one qualifying loss window and demote on two consecutive windows.
- Retain reports and audit links; expose authenticated read-only evidence in the operator UI.

## Impact

Affected capability: strategy-registry. Internal paper only; no live capital, broker orders, automatic replacement, scientific alpha estimate, regime classifier or general portfolio sizing is added.
