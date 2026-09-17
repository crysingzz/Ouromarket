# Gates: bind research claims and economic mechanisms

OWNS: GATES.md, adaptive-alpha/src/adaptive_alpha/research/knowledge.py, adaptive-alpha/src/adaptive_alpha/research/engineering.py, adaptive-alpha/src/adaptive_alpha/research/workflow.py, adaptive-alpha/src/adaptive_alpha/research/roles.py, adaptive-alpha/src/adaptive_alpha/research/campaigns.py, adaptive-alpha/src/adaptive_alpha/api/app.py, adaptive-alpha/src/adaptive_alpha/ui/**, adaptive-alpha/tests/test_research_claims.py, adaptive-alpha/tests/test_engineering.py, adaptive-alpha/tests/test_evidence_packets.py, adaptive-alpha/tests/test_operations.py, adaptive-alpha/tests/test_api_workflows.py, adaptive-alpha/docs/**, adaptive-alpha/openspec/**

Scope: content-addressed researcher claims bound to exact evidence passages plus structured economic-mechanism identity and department-aware duplicate handling; semantic truth verification remains outside this leaf

- [x] G1: each retained claim binds a supports/contradicts assertion to an exact immutable passage and WorkOrder without gaining verified authority
  CHECK: uv run pytest tests/test_research_claims.py -k 'claim_graph_is_bound_to_passages_and_work_order'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=013c261567edf7f58c48e99420777cbf336736b92532abcd3368778281ecff3d; exit=0; EXPECT=matched; output-sha256=dfe54434a660e44ef04121eb994236de89ca56ee22312dec5037dbe5db33824d; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G2: missing, unbound, duplicated or contradictory claim contracts fail before an Ouroboros WorkOrder can be admitted
  CHECK: uv run pytest tests/test_research_claims.py -k 'unbound_or_ambiguous_claims_fail_closed'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=13e1f2851162fcdb7044a67fbc71c21b9ee7d652c6f16f75247a49e8238daea9; exit=0; EXPECT=matched; output-sha256=dfe54434a660e44ef04121eb994236de89ca56ee22312dec5037dbe5db33824d; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G3: normalized economic-mechanism identity detects prior novel mechanisms while replication variants remain explicitly related instead of silently relabelled
  CHECK: uv run pytest tests/test_research_claims.py -k 'mechanism_identity_drives_department_duplicate_policy'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=ff40af1c7b8fb6787bb67655e4fa1b62b6e2cecb5103a6cc79249808ded79963; exit=0; EXPECT=matched; output-sha256=c8aed5a6d33e9939900b82ea1b1cf40f8f8b46c64805553ff9932f4ca0c1c393; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G4: authenticated knowledge API and operator UI expose claim relation, semantic status, mechanism family and lineage
  CHECK: uv run pytest tests/test_research_claims.py -k 'claims_and_mechanisms_are_visible_to_operator'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=01bf87a98184c9ec145830d3780b77af5f241f59dfa58e6a46307c73d87a5321; exit=0; EXPECT=matched; output-sha256=fc4250a43c136a49e972908166283d9186b3507e0a0d312a43f2dadaa078aeac; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G5: lint, typing, full statement coverage, dependency audit and all strict OpenSpec items pass together
  CHECK: make check && uv run pip-audit
  EXPECT: No known vulnerabilities found
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=dd2342b679ba84dc0c8c0fdeebfe637599ce34c8cbdacafb34c0a081ea482b7e; exit=0; EXPECT=matched; output-sha256=df761458254506ee0ebd4d54367091769a8d6c79e1ea61253546061be967823e; output-bytes=9832; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries
