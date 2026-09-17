# Gates: verified point-in-time revision ledgers

OWNS: GATES.md, adaptive-alpha/src/adaptive_alpha/research/contracts.py, adaptive-alpha/src/adaptive_alpha/research/datasets.py, adaptive-alpha/src/adaptive_alpha/research/pit.py, adaptive-alpha/src/adaptive_alpha/api/app.py, adaptive-alpha/tests/test_pit_data.py, adaptive-alpha/docs/**, adaptive-alpha/openspec/**

Scope: immutable single-symbol daily revision ledgers, server-produced verification reports and as-of snapshots; vendor acquisition, historical universe membership, corporate actions and execution-aware laboratory behavior remain outside this leaf

- [x] G1: a late correction is invisible before its receipt time and cannot change an earlier immutable as-of snapshot
  CHECK: uv run pytest tests/test_pit_data.py -k 'as_of_snapshots_hide_future_revisions'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=51caaf9851649981e782e1559e8ebcd8bc18b5ba7f1a8fd809cca9c3e1368a04; exit=0; EXPECT=matched; output-sha256=4a211e2ead2c2903df6eac9fbd48a7e10824bb0ed365f224e72c95ed430e13e2; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G2: malformed provenance, time order and revision chains fail closed while only the operator can create a verified ledger through the API
  CHECK: uv run pytest tests/test_pit_data.py -k 'invalid_ledgers_fail_closed or pit_api_requires_operator_and_exposes_proof'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=42a2fbc45ae73828a0239bb3e0b93f0c743bc493f788a415e3811b085f942d94; exit=0; EXPECT=matched; output-sha256=048ed1443dfe412d295103c48e83f51f038f485b67a35e0b1292e0e0778a2504; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G3: lint, typing, full statement coverage, dependency audit and every strict OpenSpec item pass together
  CHECK: make check && uv run pip-audit
  EXPECT: No known vulnerabilities found
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=dd2342b679ba84dc0c8c0fdeebfe637599ce34c8cbdacafb34c0a081ea482b7e; exit=0; EXPECT=matched; output-sha256=1e5aa9c9934377d21ba3e6d3bf6e8b74bdb704c479ff1c7462aecb56f76ced86; output-bytes=10050; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries
