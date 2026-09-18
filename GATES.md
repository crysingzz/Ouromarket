# Gates: cobalt-inspired operator interface

OWNS: GATES.md, adaptive-alpha/src/adaptive_alpha/ui/index.html, adaptive-alpha/src/adaptive_alpha/ui/styles.css, adaptive-alpha/src/adaptive_alpha/ui/app.js, adaptive-alpha/scripts/ui_style_smoke.py, adaptive-alpha/tests/test_ui_design.py, adaptive-alpha/docs/**, adaptive-alpha/openspec/**

Scope: an original black-and-monochrome operator interface inspired by cobalt.tools layout principles; application workflows, API contracts and trading authority remain unchanged

- [x] G1: the UI exposes the compact accessible rail, monochrome theme, restrained cards and responsive bottom dock without copying external assets
  CHECK: uv run pytest tests/test_ui_design.py
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=2ba1071eb7990c4bc0eacd6dfa89521f013803c1a7ef9408802ddfc6db42ccd6; exit=0; EXPECT=matched; output-sha256=556ed54bb0004765fe9d735daa868d79edbd0055c4dbe9f5e334f7c2f488d5b6; output-bytes=1041; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G2: authenticated desktop and mobile browser rendering has the intended computed layout, no horizontal overflow and no JavaScript errors
  CHECK: ALPHA_BROWSER_CHANNEL=chrome uv run --with playwright python scripts/ui_style_smoke.py
  EXPECT: PASS: cobalt-inspired desktop and mobile layout
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=63239a74fc46ba6c8839df8483da1e0222b0d20bcc77be237a7ebe3cc1ba73c2; exit=0; EXPECT=matched; output-sha256=09ff21ff17d25a6c7403207f700dd83fcc05d0cc26d8baa499cf318a60f51791; output-bytes=177; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G3: all existing UI workflows still pass on desktop and mobile
  CHECK: ALPHA_BROWSER_CHANNEL=chrome uv run --with playwright python scripts/ui_smoke.py
  EXPECT: PASS: login, research, evidence, halt/resume, audit, autonomous and lifecycle panels
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=eabf3381434f0834cf70b81937fea2f7cd4296c209eb2dfaf38b4b7cf9fa2580; exit=0; EXPECT=matched; output-sha256=b6027d24c597637fcf97fe6c6317bb49595a7104f09233383b57e88a49ed4dca; output-bytes=279; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries

- [x] G4: lint, typing, full statement coverage, dependency audit and every strict OpenSpec item pass together
  CHECK: make check && uv run pip-audit
  EXPECT: No known vulnerabilities found
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=dd2342b679ba84dc0c8c0fdeebfe637599ce34c8cbdacafb34c0a081ea482b7e; exit=0; EXPECT=matched; output-sha256=8ff6948a4aad9371c2acab2c20f24a290806e6540fd872fe1dfc8b1a34bd0860; output-bytes=10088; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=124e595f5a5d/19 entries
