# Gates: qualify and reuse Ouroboros engineering tools

OWNS: GATES.md, adaptive-alpha/src/adaptive_alpha/research/engineering.py, adaptive-alpha/src/adaptive_alpha/research/tool_catalog.py, adaptive-alpha/src/adaptive_alpha/research/engineering_worker.py, adaptive-alpha/src/adaptive_alpha/research/ouroboros.py, adaptive-alpha/src/adaptive_alpha/api/operations.py, adaptive-alpha/src/adaptive_alpha/ui/**, adaptive-alpha/tests/test_tool_catalog.py, adaptive-alpha/docs/**, adaptive-alpha/openspec/**

Scope: matched independent qualification, operator adoption/revocation and immutable reuse of engineering tools in future WorkOrders; real model and runsc host admission remain external

- [x] G1: the operator can prepare three idempotent matched benchmark pairs while unreviewed or non-independent inputs fail closed
  CHECK: uv run pytest tests/test_tool_catalog.py -k 'prepares_idempotent_paired_benchmark_plans or rejects_unreviewed_or_nonindependent_benchmark_inputs'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=2ad4665343931eb0d090904944b3118f4c3693cd7607afbf5f7d73d9856012a4; exit=0; EXPECT=matched; output-sha256=8d89f59c25586b5636544d4540e78625c526d008a5f1feddc3654e5de8d813fc; output-bytes=1056; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G2: independent wins qualify a reusable tool and an adopted tool is snapshotted into the next Ouroboros WorkOrder
  CHECK: uv run pytest tests/test_tool_catalog.py -k 'qualifies_and_adopts_reusable_tool or active_tool_is_snapshotted_for_ouroboros'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=92a08824d154762b36f65f1179839d08a14c9e19ed57e706c1227ce1dcc96915; exit=0; EXPECT=matched; output-sha256=7f89cda89a8caba017a55f7bdcf5853f886014db9c62b2af956716fcb5477b6d; output-bytes=1056; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G3: regressions and revocation block reuse, and only the operator API can control the lifecycle exposed in the UI
  CHECK: uv run pytest tests/test_tool_catalog.py -k 'regression_and_revocation_fail_closed or operator_api_and_ui_show_tool_lifecycle'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=e51862a2a29969772bcf381a53f3702db5596a014a84cfe45464565e7183cbb5; exit=0; EXPECT=matched; output-sha256=0f36677c16eed5ac8a431cd850aef3cd5d607be2fbc0a235225600b9ccd32542; output-bytes=1056; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G4: lint, typing, full statement coverage, and all strict OpenSpec items pass together
  CHECK: make check
  EXPECT: Totals: 20 passed, 0 failed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=59d96ea4695db9f7e605cf00c32deae22fb1aa642c1b15da1803226b0946210c; exit=0; EXPECT=matched; output-sha256=d1aac536f68bd0b66ae1b8a473d636ba42afba0e165d2a281b34e1886dbd9376; output-bytes=9319; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries
