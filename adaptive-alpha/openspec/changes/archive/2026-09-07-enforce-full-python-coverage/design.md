## Decisions

Preserve the existing statement-coverage metric so the 82% baseline and 100% result use the same denominator. Instrument the entire adaptive_alpha package. Do not omit files or add no-cover pragmas.

Use real SQLite persistence and FastAPI request handling, controlled HTTP transports, injected process termination, and deterministic concurrent-state interleavings. PostgreSQL migration and locking tests validate emitted driver contracts using controlled connections; actual PostgreSQL permission probes remain a separate integration check. Tests do not contact live OpenAI, Ouroboros or brokers.

Exercise interpreter runtime guards with explicitly corrupted prevalidated AST objects as defense-in-depth tests. These cases do not claim that a validated program can create those ASTs.

Set coverage.report.fail_under to 100 and preserve an HTML/XML report. Statement coverage does not establish complete branch coverage, scientific strategy quality or live integration acceptance.
