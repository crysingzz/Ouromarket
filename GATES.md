# Gates: acquire available arXiv HTML without widening trust

OWNS: GATES.md, adaptive-alpha/src/adaptive_alpha/research/contracts.py, adaptive-alpha/src/adaptive_alpha/research/literature.py, adaptive-alpha/src/adaptive_alpha/research/evidence.py, adaptive-alpha/src/adaptive_alpha/research/campaigns.py, adaptive-alpha/src/adaptive_alpha/ui/**, adaptive-alpha/tests/test_full_text_evidence.py, adaptive-alpha/tests/test_autonomous.py, adaptive-alpha/tests/test_transports.py, adaptive-alpha/tests/test_evidence_packets.py, adaptive-alpha/docs/**, adaptive-alpha/openspec/**

Scope: explicit opt-in retrieval of available arXiv HTML full text through a fixed-origin bounded parser; PDF parsing, formula/table interpretation and claim verification remain outside this leaf

- [x] G1: opted-in arXiv results retain bounded plain text, exact origin and license metadata while scripts and markup remain inert
  CHECK: uv run pytest tests/test_full_text_evidence.py -k 'arxiv_available_html_is_bounded_and_provenanced'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=846b3582e10a31f9d11436c8156046dd4b88ecdb74461bc071002db685761d35; exit=0; EXPECT=matched; output-sha256=955e8fa0ff5ab73bc0de1d39148387fa83e48028867149528fde0d866adc1aee; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G2: invalid identity, content type, oversized response or unavailable HTML cannot become a full-text evidence claim
  CHECK: uv run pytest tests/test_full_text_evidence.py -k 'arxiv_full_text_fails_closed_to_abstract'
  EXPECT: 1 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=523928117f68584a065b257c728099902cf249b4a177d221b25748f7e41b0465; exit=0; EXPECT=matched; output-sha256=6b68787dfb8081b46a3018ea66dd3fbeff1d057598e9230a5785109bf21af1c4; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G3: campaign policy, evidence packet, authenticated API and UI expose the actual acquisition level without granting new authority
  CHECK: uv run pytest tests/test_full_text_evidence.py -k 'campaign_policy_produces_truthful_packet or api_ui_expose_full_text_policy'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=3e1d6bb72983cd031db47492dc7654fb0e6f37ab680649367ec280e2354000e4; exit=0; EXPECT=matched; output-sha256=7124fbed31ae81edb8e4546abf1064527924a8a6a8b631036f0a3b3af812246a; output-bytes=1055; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G4: lint, typing, full statement coverage, dependency audit and all strict OpenSpec items pass together
  CHECK: make check && uv run pip-audit
  EXPECT: No known vulnerabilities found
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=dd2342b679ba84dc0c8c0fdeebfe637599ce34c8cbdacafb34c0a081ea482b7e; exit=0; EXPECT=matched; output-sha256=430a4d5ed4f26dbfeb98b39c8a99e03366b50c3055d613c563940de10f0384c9; output-bytes=9720; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries
