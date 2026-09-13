# Gates: recover interrupted campaigns from retained engineering results

OWNS: GATES.md, adaptive-alpha/src/adaptive_alpha/research/**, adaptive-alpha/tests/test_campaign_resume.py, adaptive-alpha/docs/**, adaptive-alpha/openspec/**

Scope: resume a fenced campaign after a worker crash without repeating completed OpenAI or Ouroboros work

- [x] G1: a completed engineering result resumes into exactly one evaluated candidate without another model or runtime call
  CHECK: uv run pytest tests/test_campaign_resume.py -k 'reuses_completed_engineering_result or finalizes_closed_generation'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=f25468cadcdf6e6a6d829b8067ab8867678bee0923878c037fabe5c418814286; exit=0; EXPECT=matched; output-sha256=5cd606f2dfa8f40d83b17ccb3959acfc65033125ae427b4087f664549560e891; output-bytes=1056; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G2: incomplete, ambiguous, or tampered recovery state fails closed and is never silently replayed
  CHECK: uv run pytest tests/test_campaign_resume.py -k 'unknown_outcome or tampered_result'
  EXPECT: 2 passed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=a4081f767e64d05418c253615671b847605b380f2152cc039465cd35035e4727; exit=0; EXPECT=matched; output-sha256=02e33070506ba44ea9503dcd778d897b9ee9572d8b2f3bde3db5560c97696e36; output-bytes=1056; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries

- [x] G3: repository quality, full coverage, typing, and strict OpenSpec validation pass together
  CHECK: make check
  EXPECT: Totals: 20 passed, 0 failed
  CWD: adaptive-alpha
  EVIDENCE: automatic-evidence=v1; definition-sha256=59d96ea4695db9f7e605cf00c32deae22fb1aa642c1b15da1803226b0946210c; exit=0; EXPECT=matched; output-sha256=fc7d7fa2927e447af76856bc2f7ba21c7c95afbe44a5b4d7fe7dd5e315c06d6f; output-bytes=8677; shell=/bin/sh; cwd=/Users/crysingzz/Desktop/projects/ouromarket-repository/adaptive-alpha; path=74401630f0b5/19 entries
