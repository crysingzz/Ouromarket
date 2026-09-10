# Security model and operator boundaries

The initial distribution is a local synthetic paper laboratory. No real broker credentials, external capital or arbitrary agent-generated code are supported.

- Operator and research tokens must differ and contain at least 32 characters. Secrets are generated randomly once. Never provide an operator token to an agent runtime.
- Research tokens can create research jobs/hypotheses/specifications and inspect public research outcomes/risk limits. They cannot place orders, admit to paper, halt/resume, read operator portfolio/audit or access the evaluator directly.
- Evaluator seed/ledger are mounted only into its private container. The evaluator service credential is available to trusted orchestration, not research agents. Hidden response is exactly `{verdict, score}` with rounded score and a persistent global query cap.
- Docker API/evaluator containers are non-root, read-only, without capabilities or privilege escalation, and have memory/CPU/PID limits. No source checkout or Docker socket is mounted. No generated code is run by this application.
- Host `.secrets/` is mode 0700. Leaf secret files are 0444 for non-root container mounting; host users cannot traverse the parent. `.env` is 0600. Docker administrators are trusted and can read container secrets.
- Browser bearer stays in memory only. CSP forbids remote scripts, framing and inline code. User/model strings are escaped or rendered with textContent. No remote fonts or analytics.
- API publication is loopback-only. Do not expose it to a network without TLS, robust authentication, ingress request limits and monitoring. HTTP bearer on a public interface is not a supported deployment.
- Record and event triggers reject mutation. Journal hashes detect inconsistent edits; they do not prevent a trusted DB owner from rebuilding or deleting the chain. Future production requires separate migration/runtime DB roles, signed receipts and external append-only checkpoints.
- SQL errors return generic failure; raw provider errors and tokens are not included in results. Access logging is disabled by default. No public evaluation diagnostics contain hidden data.

## Future generated-code runtime

Before enabling Ouroboros output, implement a separately operated sandbox with pinned image digest, no broker/production secrets, no unrestricted network, a read-only candidate input mount, bounded writable output, CPU/RAM/PID limits and a hard wall-clock deadline including descendant cleanup. Do not mount Docker socket into an agent. Do not mistake AST scanning, prompt instructions or Pydantic validation for a Python execution sandbox. The current API has no endpoint for executing arbitrary Python.

## Recovery

Kill state persists across restarts. Operator resume refuses mismatched internal/broker cash or positions. A stale quote activates halt on the next order; refreshing the fixed demo quote does not clear a halt. Review the cause, refresh when appropriate, then explicitly resume. Pending/open orders do not exist in this internal immediate-fill broker; external broker cancellation is a future capability.

If a worker crashes during research, preserve both public and hidden volumes. Inspect `/api/attempts`, `/api/experiments` and audit. An incomplete attempt is still part of trial accounting. Do not delete records or reset hidden query budget to improve scores.

## Generated research boundary (v0.2)

Generated source is **not native Python execution**. `signal-python-v1` parses a bounded AST and interprets an explicit numeric grammar. Imports, attributes, recursion, loops, comprehensions, strings, nested sequences and sequence comparisons are rejected. Only prior available closes enter a signal call. Host-owned code calculates costs, returns and evaluation. This intentionally limits strategy expressiveness; full arbitrary-Python Docker sandboxing remains a separate capability.

OpenAI credentials can be configured from the operator UI. The API writes a 0600 file atomically to a dedicated Docker volume; the research worker mounts it read-only and reloads configuration. Hidden evaluation does not mount that volume. HTTP validation errors omit request input, and provider failures never include raw upstream responses or credentials in public records. The UI retains session credentials only in memory. The localhost deployment has no claim of OIDC/TLS production hardening.

A one-shot migration container owns PostgreSQL schema changes. `alpha_runtime` can select/append records and events and update mutable projections; it cannot alter the append-only journals or their triggers. The host administrator and trusted controller processes remain in the trust boundary.

The external Alpaca adapter has a hardcoded paper origin. An unknown submission outcome is reconciled by client ID; it is never blindly resubmitted. This adapter is not exposed as an unrestricted research API. The optional forward worker uses live market data with **internal** paper execution, in separate per-strategy test accounts. It does not submit external broker orders.
