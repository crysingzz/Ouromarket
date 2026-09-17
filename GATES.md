# Gates: separate research department workflows

OWNS: GATES.md, adaptive-alpha/compose.yaml, adaptive-alpha/scripts/mock_autonomous.py, adaptive-alpha/src/adaptive_alpha/config.py, adaptive-alpha/src/adaptive_alpha/research/departments.py, adaptive-alpha/src/adaptive_alpha/research/campaigns.py, adaptive-alpha/src/adaptive_alpha/research/worker.py, adaptive-alpha/src/adaptive_alpha/api/app.py, adaptive-alpha/src/adaptive_alpha/ui/app.js, adaptive-alpha/src/adaptive_alpha/ui/operations.js, adaptive-alpha/tests/test_research_departments.py, adaptive-alpha/tests/test_runtime_lifecycle.py, adaptive-alpha/tests/test_api_workflows.py, adaptive-alpha/docs/**, adaptive-alpha/openspec/**

Scope: fixed replication and novel worker queues, campaign-local budgets, department-scoped retained memory and server-owned result policies; model execution, formula verification and scientific truth remain outside this leaf

- [x] G1: fixed department workers claim only their own durable queue and cannot steal or relabel work from the other department
  CHECK: uv run pytest tests/test_research_departments.py -k 'separate_department_workers_claim_only_own_queue'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=751a670fa82c702da7e5874e469b43184153bbf9b3dd17ae64cbd41095a023d9; exit=0; EXPECT=matched; output-sha256=dad0d186d0295375e1036b297cf41cd91e81b3976be8a22183d0b37a2dcb5232; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G2: each campaign freezes its department policy and budget while retained memory and result criteria remain isolated by department
  CHECK: uv run pytest tests/test_research_departments.py -k 'department_budget_memory_and_result_policy_are_isolated'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=d4a5f2d9356b911b68c30d6f474238c3cb53005222fef1216be5b89dafb88189; exit=0; EXPECT=matched; output-sha256=b181c9c42f883702a8fe078a6d3495a1177d9d68ec03ec32e72bc7a0ccdb62d7; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G3: API, UI and Docker topology expose two independently healthy research department workers without granting capital authority
  CHECK: uv run pytest tests/test_research_departments.py -k 'department_readiness_and_compose_are_explicit'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=36137a034051d10becb439636127cf3ad54f611d7cde258e0b40912d7437693f; exit=0; EXPECT=matched; output-sha256=2905212fe7e90d09dad9aeaccb0dd85d0708ef483c843921455fb08a46b88a55; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G4: lint, typing, full statement coverage, dependency audit and all strict OpenSpec items pass together
  CHECK: make check && uv run pip-audit
  EXPECT: No known vulnerabilities found
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=dd2342b679ba84dc0c8c0fdeebfe637599ce34c8cbdacafb34c0a081ea482b7e; exit=0; EXPECT=matched; output-sha256=9f959cc2433d9086ee40d36b737ecea665e49798208f4c2db53b996f91dd9dfc; output-bytes=9947; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G5: the repeatable Docker campaign binds its department lease, completes three generations and reproduces exactly without an OpenAI call
  CHECK: docker exec -i adaptive-alpha-worker-1 python - --offline-literature --controlled-evaluation < scripts/mock_autonomous.py
  EXPECT: "status": "COMPLETED"
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=ba82811f0c009ff02263f27de9b2c60c5df450dbb7d8b3166b3cc3c026702b11; exit=0; EXPECT=matched; output-sha256=39e988e26abbd21b89d8af27e84fc25e4cac031c93bd312c9f0c14d2cd481ddb; output-bytes=568; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries
