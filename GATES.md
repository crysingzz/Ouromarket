# Gates: integrate reviewed Ouroboros harnesses with the isolated runner

OWNS: GATES.md, adaptive-alpha/src/adaptive_alpha/research/tool_execution.py, adaptive-alpha/src/adaptive_alpha/research/tool_worker.py, adaptive-alpha/src/adaptive_alpha/api/operations.py, adaptive-alpha/src/adaptive_alpha/config.py, adaptive-alpha/src/adaptive_alpha/ui/**, adaptive-alpha/tests/test_tool_execution.py, adaptive-alpha/compose.yaml, adaptive-alpha/docs/**, adaptive-alpha/openspec/**

Scope: durable operator-controlled validation of reviewed harness artifacts in the separate native-tool runner; production runsc host admission remains external

- [x] G1: a reviewed harness executes through the worker and an expired lease is safely resumed with one retained result
  CHECK: uv run pytest tests/test_tool_execution.py -k 'executes_reviewed_harness or resumes_expired_tool_lease'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=83b27a4b45f58c16199277ed7618547b92fce1949fba039afa2b2681e2d3413f; exit=0; EXPECT=matched; output-sha256=a75e4d09c2fae7b86030b496cd0d755c5f25bb433b300903214165a00b38ce99; output-bytes=1056; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G2: unreviewed or non-harness artifacts are rejected and cancellation fences a stale worker
  CHECK: uv run pytest tests/test_tool_execution.py -k 'rejects_unreviewed_or_wrong_artifact or cancellation_fences_stale_owner'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=39928711cf4a1356c7756ebc951bfd886f2bdb7d7079290d04a4770a295d1541; exit=0; EXPECT=matched; output-sha256=30699387b1d0c77608be0494d3e05bd9edd0e16e16b248c62caa3300cae713cd; output-bytes=1056; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G3: only the operator API can enqueue tool validation and UI/Compose expose the isolated worker without giving the API a Docker socket
  CHECK: uv run pytest tests/test_tool_execution.py -k 'operator_api_and_ui_visibility or compose_isolates_tool_worker'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=a3ece9aff68993d06b5164bd042f5463a006fa50bed997257b57f31c5505ecb9; exit=0; EXPECT=matched; output-sha256=4350950126feb57880cc8c2d5dc3a80c266576c8488f80d0812daa2b1ce9d8c8; output-bytes=1056; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G4: lint, typing, full statement coverage, and all strict OpenSpec items pass together
  CHECK: make check
  EXPECT: Totals: 20 passed, 0 failed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=59d96ea4695db9f7e605cf00c32deae22fb1aa642c1b15da1803226b0946210c; exit=0; EXPECT=matched; output-sha256=fc05f34fa267f391b45d072c374e20404a8e505236aa1c8bd52e4e1d5aa366b8; output-bytes=9165; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries
