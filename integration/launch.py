"""Boot the pinned upstream server in a credential-free protocol profile."""

import json
import os
import sys
from pathlib import Path

from runtime_gateway import RuntimeGateway

pin = json.loads(Path("/integration/upstream.json").read_text())
token = Path("/run/secrets/ouroboros_token").read_text().strip()
# This profile never mounts model credentials. A paid/executing profile requires
# separate admission under runsc and must not be enabled through the upstream UI.
os.environ.update(
    {
        "OUROBOROS_NETWORK_PASSWORD": token,
        "OUROBOROS_RUNTIME_MODE": "light",
        "OUROBOROS_MAX_WORKERS": "1",
        "OUROBOROS_MAX_ACTIVE_SUBAGENTS_PER_ROOT": "1",
        "OUROBOROS_POST_TASK_EVOLUTION": "false",
        "TOTAL_BUDGET": "0",
    }
)
sys.path.insert(0, "/opt/ouroboros")
import server  # noqa: E402 — environment must precede upstream import
import uvicorn  # noqa: E402

uvicorn.run(
    RuntimeGateway(server.app, token, Path("/workspaces"), pin),
    host="0.0.0.0",  # noqa: S104 — isolated container; host publication is loopback only
    port=8765,
    access_log=False,
)
