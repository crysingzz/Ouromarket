"""Verify the pinned checkout and create a service credential without printing it."""

import json
import os
import secrets
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
pin = json.loads((root / "upstream.json").read_text())
source = root.parent / pin["source_path"]
head = subprocess.check_output(["/usr/bin/git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
dirty = subprocess.check_output(
    ["/usr/bin/git", "status", "--porcelain"], cwd=source, text=True
).strip()
if head != pin["commit"] or dirty:
    raise SystemExit("Pinned Ouroboros checkout is missing, different or modified")
directory = root / ".secrets"
directory.mkdir(mode=0o700, exist_ok=True)
directory.chmod(0o700)
path = directory / "ouroboros_token"
if not path.exists():
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o444)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(secrets.token_urlsafe(48) + "\n")
path.chmod(0o444)  # Non-root container can read the mounted leaf; host parent stays 0700.
print(f"Verified Ouroboros {pin['release']} at {head}; service credential ready")
