"""Trusted container PID 1. This file uses only the pinned image's stdlib.

Never run this supervisor on the application host: its child intentionally runs
native source. The controller launches it in a networkless gVisor sandbox.
PID 1 keeps a separate UID so the unprivileged child cannot stop its watchdog.
"""

import json
import os
import selectors
import signal
import subprocess
import sys
import time
from contextlib import suppress
from typing import Any

CHILD = """import json, sys
job = json.loads(sys.argv[1])
namespace = {}
exec(compile(job['source'], '<isolated-tool>', 'exec'), namespace)
output = namespace['run'](job['payload'])
sys.stdout.write(json.dumps(output, allow_nan=False))
"""


def collect(child: subprocess.Popen[bytes], seconds: int, limit: int) -> tuple[str, bytes]:
    deadline = time.monotonic() + seconds
    output = bytearray()
    used = 0
    with selectors.DefaultSelector() as selector:
        for stream in (child.stdout, child.stderr):
            if stream is None:
                raise ValueError("CHILD_PIPES_REQUIRED")
            selector.register(stream, selectors.EVENT_READ)
        while selector.get_map():
            if time.monotonic() >= deadline:
                return "TIMEOUT", b""
            for key, _ in selector.select(timeout=0.05):
                chunk = os.read(key.fd, 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                used += len(chunk)
                if used > limit:
                    return "OUTPUT_LIMIT", b""
                if key.fileobj is child.stdout:
                    output.extend(chunk)
        try:
            code = child.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            return "TIMEOUT", b""
    return ("SUCCESS" if code == 0 else "TOOL_FAILED"), bytes(output)


def execute(job: dict[str, Any]) -> dict[str, Any]:
    if os.getpid() != 1 or os.getuid() != 0:
        raise SystemExit("SANDBOX_PID_ONE_REQUIRED")
    # Only the trusted image starts this function; request is data, never argv flags.
    child = subprocess.Popen(  # noqa: S603 — fixed interpreter; source executes only inside sandbox
        [sys.executable, "-I", "-S", "-B", "-c", CHILD, json.dumps(job)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/tmp",  # noqa: S108 — private bounded container tmpfs
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
        start_new_session=True,
        user=65532,
        group=65532,
        extra_groups=[],
    )
    try:
        status, raw = collect(child, job["seconds"], job["output_bytes"])
        output = None
        if status == "SUCCESS":
            try:
                output = json.loads(raw)
                if len(json.dumps(output, allow_nan=False).encode()) > job["output_bytes"]:
                    status, output = "OUTPUT_LIMIT", None
            except (ValueError, RecursionError):
                status, output = "INVALID_OUTPUT", None
        return {"status": status, "output": output}
    finally:
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGKILL)
        child.wait()
        if child.stdout is not None:
            child.stdout.close()
        if child.stderr is not None:
            child.stderr.close()


def main() -> None:
    if os.getpid() != 1 or os.getuid() != 0:
        raise SystemExit("SANDBOX_PID_ONE_REQUIRED")
    job = json.loads(sys.argv[1])
    result = execute(job)
    print(
        json.dumps(
            {
                "protocol": "native-tool-v1",
                "request_hash": job["request_hash"],
                "python": sys.version.split()[0],
                **result,
            },
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
