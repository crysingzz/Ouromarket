# Gates: bind research claims and economic mechanisms

OWNS: GATES.md, integration/smoke.py, adaptive-alpha/src/adaptive_alpha/research/knowledge.py, adaptive-alpha/src/adaptive_alpha/research/engineering.py, adaptive-alpha/src/adaptive_alpha/research/workflow.py, adaptive-alpha/src/adaptive_alpha/research/roles.py, adaptive-alpha/src/adaptive_alpha/research/campaigns.py, adaptive-alpha/src/adaptive_alpha/api/app.py, adaptive-alpha/src/adaptive_alpha/ui/**, adaptive-alpha/tests/test_research_claims.py, adaptive-alpha/tests/test_engineering.py, adaptive-alpha/tests/test_evidence_packets.py, adaptive-alpha/tests/test_operations.py, adaptive-alpha/tests/test_api_workflows.py, adaptive-alpha/docs/**, adaptive-alpha/openspec/**

Scope: content-addressed researcher claims bound to exact evidence passages plus structured economic-mechanism identity and department-aware duplicate handling; semantic truth verification remains outside this leaf

- [x] G1: each retained claim binds a supports/contradicts assertion to an exact immutable passage and WorkOrder without gaining verified authority
  CHECK: uv run pytest tests/test_research_claims.py -k 'claim_graph_is_bound_to_passages_and_work_order'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=013c261567edf7f58c48e99420777cbf336736b92532abcd3368778281ecff3d; exit=0; EXPECT=matched; output-sha256=f9c5fc09515b899f57cd174e3c4132e1fb6f665695cb69e8b309880c399c868e; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G2: missing, unbound, duplicated or contradictory claim contracts fail before an Ouroboros WorkOrder can be admitted
  CHECK: uv run pytest tests/test_research_claims.py -k 'unbound_or_ambiguous_claims_fail_closed'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=13e1f2851162fcdb7044a67fbc71c21b9ee7d652c6f16f75247a49e8238daea9; exit=0; EXPECT=matched; output-sha256=be6a4c7e36fac9ae5b2f4d2fd13a08e19634eb982cea0e689d9da640bbf43103; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G3: normalized economic-mechanism identity detects prior novel mechanisms while replication variants remain explicitly related instead of silently relabelled
  CHECK: uv run pytest tests/test_research_claims.py -k 'mechanism_identity_drives_department_duplicate_policy'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=ff40af1c7b8fb6787bb67655e4fa1b62b6e2cecb5103a6cc79249808ded79963; exit=0; EXPECT=matched; output-sha256=2ae5ca97a8f742a8164ba5fc1220eb2bcd0755ee9d2e2df56f63c88da7368cd0; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G4: authenticated knowledge API and operator UI expose claim relation, semantic status, mechanism family and lineage
  CHECK: uv run pytest tests/test_research_claims.py -k 'claims_and_mechanisms_are_visible_to_operator'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=01bf87a98184c9ec145830d3780b77af5f241f59dfa58e6a46307c73d87a5321; exit=0; EXPECT=matched; output-sha256=baaa93f6904c1ca82d90f24e8421f24af8b810197ab62cefc1d025ddab4a643b; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G5: lint, typing, full statement coverage, dependency audit and all strict OpenSpec items pass together
  CHECK: make check && uv run pip-audit
  EXPECT: No known vulnerabilities found
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=dd2342b679ba84dc0c8c0fdeebfe637599ce34c8cbdacafb34c0a081ea482b7e; exit=0; EXPECT=matched; output-sha256=0b36f05949da2b07271f32fff8b20b23cf0701430146613489e419f8a9ec75dd; output-bytes=9832; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G6: pinned Ouroboros accepts the structured mechanism WorkOrder through the actual authenticated integration protocol while model execution remains disabled
  CHECK: uv run python ../integration/smoke.py
  EXPECT: PASS: actual Ouroboros health, auth, Git workspace and explicit unready-pool refusal; no model execution
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=4a17801d9c97d0d10d5ae5c183d82bbb4bddfbe5f0970195bc476205f10c282b; exit=0; EXPECT=matched; output-sha256=af018b8bee6cc03ddf3b8fd95405e18b74577db4dd5652b6906c23fa739e9d2c; output-bytes=105; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries
