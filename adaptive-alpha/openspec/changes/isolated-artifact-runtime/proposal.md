# Isolated engineering artifact runtime

## Why

Ouroboros currently stores skills, subagents and harness as inert proposals. Executing engineering tools requires a separate enforced boundary before any adoption workflow can use them.

## What Changes

- Add a bounded JSON-in/JSON-out native Python tool protocol and trusted Docker controller outside application services.
- Require a pinned image and gVisor runtime for submitted source; expose only built-in acceptance fixtures on development runc.
- Bound resources, protect the watchdog, clean up complete containers and quarantine ambiguous outcomes.
- Record execution provenance and add unit/fault tests plus real Docker fixture acceptance.
- Add an operator-controlled durable queue for reviewed harnesses and a separate worker with cancellation, lease recovery, audit and UI visibility.
- Keep production runsc-host acceptance and automatic tool adoption explicitly pending.

## Impact

Affected capabilities: agent-runtime and isolated-native-tools. Default strategy evaluation remains the bounded signal DSL. No broker access, capital admission, package installation or model/network calls are added.
