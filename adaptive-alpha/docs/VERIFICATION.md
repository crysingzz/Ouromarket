# Verification record

Campaign reconstruction, 2026-09-13: **410 tests passed; 100.00% Adaptive Alpha statement coverage (4164/4164)**. An expired campaign now resumes only from a single completed engineering delivery whose campaign, attempt, WorkOrder, spec, runtime, input, bundle and trusted server benchmark bindings all match. It reconstructs the candidate and recorded model usage without repeating the researcher or Ouroboros call; a candidate already retained before evaluation is reused exactly. Fully evaluated generations are not regenerated, and final diagnostics are idempotent. Unknown, incomplete, duplicated or tampered state fails closed as INTERRUPTED. Ruff, Pyrefly, mypy and all 20 strict OpenSpec items pass. Tests use controlled transports; this does not admit model execution or gVisor.

Engineering delivery queue, 2026-09-12: **396 tests passed; 100.00% Adaptive Alpha statement coverage (4026/4026)**. Every dispatch is recorded before the runtime call with its requested token/time budget; append-only events retain running, contract-validation and terminal state. A dedicated worker owns a lease independent of the campaign, and the UI reports its heartbeat and delivery count. Expired delivery reuses the same WorkOrder and deterministic runtime task identity; if a bundle was retained before a crash, the next worker benchmarks it without a second model call. Cancellation or campaign lease loss reaches the queue checkpoint and the upstream cancel endpoint. Terminal queue state and the immutable attempt event commit together, so a cancellation race cannot publish success. Ruff, Pyrefly, mypy and all strict OpenSpec items pass. These tests use controlled providers; model execution remains closed until an OpenAI profile and gVisor are admitted.

Pinned source integration, 2026-09-11: **372 tests passed; 100.00% Adaptive Alpha statement coverage (3719/3719)**. Ruff, Pyrefly and mypy pass, including the integration gateway; strict OpenSpec validates 20 items. The 13 new cases test service authentication, readiness before paid research, workspace identity, real Git provisioning/idempotency, path/symlink/size rejection and denied settings access. Coverage is scoped to Adaptive Alpha; it does not claim full upstream or deployment-script coverage.

The actual Ouroboros 6.114.0 server builds from pinned submodule `b9bcc2da71e0bd51b6f5f906890b3b80265defed` with its own lock. Local protocol acceptance verifies upstream health, dedicated-token authentication, separate frozen Git workspaces, explicit task refusal with HTTP 503 `worker_pool_unavailable`, and 404 for absent task reads/cancels. The pool is unavailable because bootstrap deliberately has no model credentials. This is a real upstream negative-path test, not a successful model-generated strategy. Positive task completion remains controlled in adapter tests until executing-runtime admission. Container network and writable-state paths were corrected during local deployment; no finance source or model/broker keys enter the runtime image.

Three selected upstream `test_headless_cli.py` cases pass inside the actual pinned image: task admission with a child drive, rejection of unsafe IDs/system workspaces, and rejection of internal task types. They use upstream-controlled worker fixtures and do not call a model. The deployed alpha worker also passes authenticated runtime connectivity and readiness refusal; the updated application passes its API/lifecycle/audit/RBAC smoke. No existing secrets, provider vault or database volumes were replaced. The old checkout is retained; the canonical published structure lives in the `ouromarket-repository` worktree.

Native-tool controller foundation, 2026-09-11: **359 tests, 100.00% Python statement coverage (3697/3697)**; Ruff, Pyrefly, mypy and strict OpenSpec (19 items) pass. The 39 added test cases cover immutable request bounds, resource policy, mandatory runtime/image gates, cancellation before/during provisioning and execution, malformed/spoofed/oversized output, watchdog behavior, cleanup failures, ambiguous creation and ownership/lease-aware recovery. Host tests mock native spawning; no submitted Python runs on the application host.

Real Docker acceptance runs 12 fixed jobs including stderr overflow, secret/socket/control-code path denial, root-readonly, zero child capabilities, denied root recovery and watchdog signalling, network denial, CPU loop timeout, detached descendants, memory exhaustion, invalid JSON, controlled error, two clean workspaces and cancellation. Reports retain provenance and confirm deletion. The first Docker attempt exposed a missing KILL capability in the different-UID supervisor; the controller now grants it only to the parent and acceptance checks that the child retains no effective/permitted capabilities. Docker Desktop has no runsc, and the actual production gate refuses execution before creation. This is development fixture acceptance, not gVisor hostile-code acceptance or integration with Ouroboros. See RUNNER.md and ADR 0002. CI runs this fixture suite in a separate job and publishes its report.

The recovery increment passes **320 tests, 100.00% Python statement coverage (3474/3474)**, Ruff, Pyrefly, mypy and strict OpenSpec (18 items). Tests exercise operator-only HTTP revalidation, preserved account balances/positions/loss watermarks, global-halt rollback, rejected prior-episode proofs and comparisons, evaluator error redaction, concurrent retries, expired leases and stale lifecycle results. External evaluator responses are controlled in these tests; revalidation does not claim a new independent dataset.

Local Docker build, deployed API smoke and offline campaign acceptance pass for the recovery increment. Campaign `6e2c4df9-d063-44a6-9f07-1a5b98ffc195` completed three controlled generations with a real isolated evaluator; all three results replay exactly and the audit chain verifies. Browser desktop/mobile acceptance passes without JavaScript errors. The recovery button sequence uses explicitly intercepted fixture API responses, while the Python HTTP tests exercise the actual recovery service and journal; it does not submit synthetic recovery proof to the deployed database. The browser also verifies that the campaign UI offers only Ouroboros.

The fixed-spec generation increment passes **304 tests, 100.00% Python statement coverage (3386/3386)**, Ruff, Pyrefly, mypy and strict OpenSpec (18 items). New HTTP/worker tests verify the default Ouroboros route, rejection of retired or caller-forged modes, preserved immutable legacy requests, explicit fixture provenance and no combined-generator fallback. This increment removes the obsolete worker branch; coverage remains complete with fewer production statements.

## v0.3 — 2026-09-10

Post-activation performance monitoring adds 11 test cases: **298 tests passed; 100.00% statement coverage (3392/3392)**. Ruff, Pyrefly, mypy and strict OpenSpec (17 items) pass. Controlled retained observations verify two disjoint loss windows, atomic demotion, immutable policy/evidence replay, daily sealing, retries, recovery, mixed-origin/gap rejection and risk precedence. This is empirical simulation monitoring, not a validated scientific alpha detector.

The initial v0.3 foundation verification follows.

The performance-monitoring Docker build and deployed API smoke also pass. Browser acceptance in system Chrome covers the new desktop/mobile panel and authenticated report dialog, including restoration of experiment export after closing the dialog. The first browser attempt exposed a timing-sensitive immediate assertion; it now waits for the dialog close event using Playwright's retried property assertion. The subsequent complete browser run passes without JavaScript errors.

Local Python verification: **287 tests passed; 100.00% statement coverage (3330/3330)**. Ruff lint/format, Pyrefly 1.2.0, mypy, strict OpenSpec (16 items) and dependency audit pass. New tests cover lifecycle permissions and atomic transitions, matched forward windows, automatic risk demotion, researcher-to-engineer contracts, inert artifact review, signed paper approvals and delivery interleavings. Real OpenAI, Ouroboros and Alpaca calls are not part of these controlled-transport tests.

GitHub CI passed for commit `57a4515f`: both quality and full laboratory workflows, including Docker integration and exact offline campaign reproduction. Local Docker API, evaluator and PostgreSQL are healthy; the research worker is running. The v0.3 browser smoke passed in system Chrome (`ALPHA_BROWSER_CHANNEL=chrome`), including lifecycle/artifact panels on desktop and mobile, evidence export, audit verification, and no JavaScript errors. Screenshots are retained locally under `.state/ui`. No external provider credentials were used.

The remaining v0.2 acceptance record below is historical, including its statements about publication and remote CI.

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
