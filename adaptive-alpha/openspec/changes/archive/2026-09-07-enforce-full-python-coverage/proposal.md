## Why

The v0.2 Python package had 82% statement coverage, leaving worker lifecycle, transport failures and recovery paths unverified by the default automated suite. The user requested 100% coverage.

## What Changes

- Add offline tests for public HTTP workflows, persistence, process shutdown, transport bounds, strategy interpretation and recovery interleavings.
- Require 100% statement coverage for the complete adaptive_alpha Python package without new coverage exclusions.
- Publish HTML/XML coverage reports locally and in CI.

## Impact

- Affected specs: test-quality
- Affected code: tests, pyproject.toml, Makefile, CI configuration and verification documentation.
- No production runtime logic or dependency changes.
