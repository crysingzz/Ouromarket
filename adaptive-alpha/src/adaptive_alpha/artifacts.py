"""Content-addressed local artifacts with atomic creation and hash verification."""

import hashlib
import os
from pathlib import Path
from typing import Any

from adaptive_alpha.domain import new_id


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root

    def put(self, content: bytes, media_type: str) -> dict[str, Any]:
        if len(content) > 20_000_000:
            raise ValueError("ARTIFACT_TOO_LARGE")
        identity = hashlib.sha256(content).hexdigest()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination = self.root / identity
        if destination.exists():
            self.get(identity)
        else:
            temporary = self.root / (".pending-" + new_id())
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(temporary, destination)
                except FileExistsError:
                    self.get(identity)
            finally:
                temporary.unlink(missing_ok=True)
        return {"id": identity, "sha256": identity, "size": len(content), "media_type": media_type}

    def get(self, identity: str) -> bytes:
        if len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("INVALID_ARTIFACT_ID")
        path = self.root / identity
        if path.is_symlink():
            raise ValueError("ARTIFACT_SYMLINK_REJECTED")
        with path.open("rb") as handle:
            content = handle.read(20_000_001)
        if len(content) > 20_000_000 or hashlib.sha256(content).hexdigest() != identity:
            raise ValueError("ARTIFACT_INTEGRITY_FAILURE")
        return content
