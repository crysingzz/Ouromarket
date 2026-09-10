# Verification record

## v0.3 — 2026-09-10

Local Python verification: **287 tests passed; 100.00% statement coverage (3330/3330)**. Ruff lint/format, Pyrefly 1.2.0, mypy, strict OpenSpec (16 items) and dependency audit pass. New tests cover lifecycle permissions and atomic transitions, matched forward windows, automatic risk demotion, researcher-to-engineer contracts, inert artifact review, signed paper approvals and delivery interleavings. Real OpenAI, Ouroboros and Alpaca calls are not part of these controlled-transport tests.

Docker and browser validation for v0.3 are recorded separately after their runs. The table below is the historical v0.2 acceptance record.

Verified locally on 2026-09-07 for Adaptive Alpha v0.2. The running Docker stack includes this implementation. Upstream Ouroboros code and unrelated containers were not changed.

| Check | Result |
|---|---|
| uv lock, lint and formatting | PASS — reproducible lock, ruff clean |
| Strict type checking | PASS — 43 source files |
| Automated tests | PASS — 175 tests, 100.00% statement coverage (2575/2575 executable statements) |
| Dependency audit | PASS — no known vulnerabilities reported; local editable package skipped |
| OpenSpec strict validation | PASS — 14 capabilities + 1 active change, zero failures; completed foundation archived with previously applied canonical specs |
| Docker build/migration | PASS — v0.2 built and started; migration service completed; API, evaluator and PostgreSQL healthy, research worker running |
| Research integration mock | PASS — real OpenAlex metadata/abstract search, controlled generator, real isolated E1; 3 generations completed |
| Exact campaign reproduction | PASS — all 3 public results match in the original Docker runtime; audit hash chain verified |
| UI browser smoke | PASS — login, legacy research, evidence/export, halt/resume, audit, autonomous panels, masked OpenAI setup, synthetic dataset creation, desktop/mobile, no JavaScript errors |
| Runtime database privileges | PASS — alpha_runtime cannot UPDATE/DELETE/TRUNCATE records or CREATE schema objects; audit verifies |
| Hidden-data isolation | PASS — API UID 10001; no hidden seed or ledger visible; separate evaluator volume/network and secrets |
| Artifact delivery | PASS — Docker Parquet download SHA256 matches manifest; unauthenticated download rejected |
| Fault handling | PASS — unknown external submission never blindly resends; queued cancellation makes no broker call; cancellation/fill race reconciles; invalid broker observations halt |
| Forward monitoring | PASS with controlled market fixtures — repeated-bar stale quote halts; held-position loss halts without a new signal; no duplicate fill |
| Research recovery | PASS — expired reflection lease closes once; reserved budget retained; invented citations retained as INVALID without invented graph edges |

The real-OpenAlex mock campaign is `efe7efb0-4429-4685-90d2-509e25f951b9`; local report: `.state/mock-autonomous.json`. It uses synthetic SPY data and a controlled generator, not a paid model. Its completion does not imply the candidates are profitable or approved for capital.

The CI workflow also runs the container integration mock with `--offline-literature`: deterministic evidence and generator fixtures, actual database and isolated evaluator. This avoids reliance on public search availability during CI. Remote CI has not been run in this session.

## External acceptance still pending

OpenAI key/model and isolated Ouroboros runtime remain unconfigured. No paid OpenAI call was made. Alpaca market/broker transports have controlled-response tests but no configured-account acceptance. The optional forward worker is not running without data credentials. No external broker orders or real-money trades were submitted.

Production OIDC/TLS, universal native-Python sandbox escape testing, independent real PIT datasets, extended forward soak, consolidated external portfolio execution and repeated scientific static-versus-evolving benchmarks remain outside this verified slice. Full details: STATUS.md.

## Environment and warnings

Builds used the existing Docker daemon through a task-local client configuration under `.state/docker-client` because the host credential helper hung for public images. Global Docker settings were not changed. Runtime secrets were never printed.

Two upstream deprecation warnings remain in the test transport: FastAPI/Starlette httpx support and AnyIO BlockingPortal alias. They do not fail the checks.

Exact reproduction requires the recorded runtime (Python/OS/architecture/NumPy/source hash). Historical Linux/macOS floating-point hash differences are rejected, not silently relaxed. Full upstream Ouroboros tests were not rerun because that runtime was unchanged. No commit, push, public release or public deployment was performed.

The earlier v0.1 verification contained 24 tests at 90% coverage. The initial v0.2 suite had 60 tests at 82%. The expanded suite now has 175 tests and covers all 2575 executable statements without production-code changes or new exclusions.

## Coverage completion

`make test` enforces `fail_under = 100` from pyproject.toml and writes `.state/coverage-html/index.html` and `.state/coverage.xml`. CI uses the same command and uploads only these report paths, not secrets or the full state directory.

This is Python statement coverage for `src/adaptive_alpha`, not JavaScript/browser coverage or a claim of complete branch coverage. New tests use real SQLite/FastAPI behavior, mocked external transports and deterministic fault injection. PostgreSQL migration/locking tests inspect driver contracts using controlled connections; they do not replace real PostgreSQL acceptance. Actual PostgreSQL privilege probes are recorded separately above. The suite includes corrupted-AST defense checks and exact CLI replay; no new `omit` or `pragma: no cover` rules were introduced.
