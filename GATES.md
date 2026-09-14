# Gates: bind research departments to evidence packets

OWNS: GATES.md, adaptive-alpha/src/adaptive_alpha/research/contracts.py, adaptive-alpha/src/adaptive_alpha/research/evidence.py, adaptive-alpha/src/adaptive_alpha/research/literature.py, adaptive-alpha/src/adaptive_alpha/research/roles.py, adaptive-alpha/src/adaptive_alpha/research/campaigns.py, adaptive-alpha/src/adaptive_alpha/research/engineering.py, adaptive-alpha/src/adaptive_alpha/research/workflow.py, adaptive-alpha/src/adaptive_alpha/api/app.py, adaptive-alpha/src/adaptive_alpha/ui/**, adaptive-alpha/tests/test_evidence_packets.py, adaptive-alpha/tests/test_autonomous.py, adaptive-alpha/tests/test_api_workflows.py, adaptive-alpha/tests/test_campaign_recovery.py, adaptive-alpha/tests/test_generation_route.py, adaptive-alpha/tests/test_operations.py, adaptive-alpha/docs/**, adaptive-alpha/openspec/**

Scope: immutable search scope, bounded citation passages and explicit replication/novel evidence gaps; full-text acquisition and real provider acceptance remain later work

- [x] G1: source results become tamper-evident packets with bounded passages, exact provider health and explicit evidence gaps
  CHECK: uv run pytest tests/test_evidence_packets.py -k 'builds_bounded_tamper_evident_packet or rejects_tampered_passage_and_duplicate_evidence'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=5c86347d920cb21dcf6f6773ef4a4b0c622915c520224e0c7b3aefff58514f3a; exit=0; EXPECT=matched; output-sha256=3c2c22c46515cc860dbb7df955a47a4dcaf7a5f5bdd09b62e64a02445b5062c4; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G2: replication and novel campaigns retain distinct evidence status and bind real researcher citations to the frozen WorkOrder
  CHECK: uv run pytest tests/test_evidence_packets.py -k 'campaigns_retain_department_evidence_status or researcher_citations_are_bound_to_work_order'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=d49bca820806489fcaf60988a5c33ce151089e3e54c0cf00211e17022ee0ed6d; exit=0; EXPECT=matched; output-sha256=d7f0aab3c2d9ceefdfd6cec7ee660fb5ea4f17df3218e815f6ef387984ea49c6; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G3: evidence packets are visible through authenticated API/UI while document instructions remain inert quoted data
  CHECK: uv run pytest tests/test_evidence_packets.py -k 'api_and_ui_expose_evidence_packet or document_instructions_never_become_authority'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=5104bfd18886f64f9029945aa9ac2bea33847c2e2844c056e1f66ede159095a7; exit=0; EXPECT=matched; output-sha256=5826c84ff95b0a3c82bce523da1dabec0580fdc15c102ea492c830f5593acc48; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G4: lint, typing, full statement coverage, dependency audit and all strict OpenSpec items pass together
  CHECK: make check && uv run pip-audit
  EXPECT: No known vulnerabilities found
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=dd2342b679ba84dc0c8c0fdeebfe637599ce34c8cbdacafb34c0a081ea482b7e; exit=0; EXPECT=matched; output-sha256=4757ba2f8c31007d3f0f7ed1a2c432d71a4de8148c4ce8f8d9f3c1d16c00375e; output-bytes=9679; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries
