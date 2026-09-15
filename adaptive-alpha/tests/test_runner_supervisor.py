"""Test watchdog/parser with pipes and mocked spawning, never native source on host."""

import io
import json
import os
import runpy
import subprocess
from unittest.mock import Mock

import pytest

from adaptive_alpha.runner import supervisor


def pipe(data):
    read, write = os.pipe()
    os.write(write, data)
    os.close(write)
    return os.fdopen(read, "rb")


@pytest.mark.parametrize(
    "code,stderr,limit,expected",
    [
        (0, b"", 1024, "SUCCESS"),
        (1, b"failure", 1024, "TOOL_FAILED"),
        (0, b"x" * 20, 10, "OUTPUT_LIMIT"),
    ],
)
def test_collect_bounds_both_streams(code, stderr, limit, expected):
    with pipe(b"{}") as stdout, pipe(stderr) as errors:
        child = Mock(stdout=stdout, stderr=errors)
        child.wait.return_value = code
        status, output = supervisor.collect(child, 2, limit)
        assert status == expected
        if expected == "SUCCESS":
            assert output == b"{}"


def test_collect_wall_timeout_closed_pipe_hang_and_missing_pipe(monkeypatch):
    with pipe(b"") as stdout, pipe(b"") as stderr:
        child = Mock(stdout=stdout, stderr=stderr)
        clock = Mock(side_effect=[0, 2])
        with monkeypatch.context() as patch:
            patch.setattr(supervisor.time, "monotonic", clock)
            assert supervisor.collect(child, 1, 1024) == ("TIMEOUT", b"")
        child.wait.side_effect = subprocess.TimeoutExpired("fixed-interpreter", 1)
        assert supervisor.collect(child, 1, 1024) == ("TIMEOUT", b"")
    with pytest.raises(ValueError, match="CHILD_PIPES_REQUIRED"):
        supervisor.collect(Mock(stdout=None, stderr=None), 1, 1024)


@pytest.mark.parametrize(
    "status,raw,expected",
    [
        ("SUCCESS", b'{"answer":42}', {"status": "SUCCESS", "output": {"answer": 42}}),
        ("SUCCESS", b"garbage", {"status": "INVALID_OUTPUT", "output": None}),
        ("SUCCESS", b"NaN", {"status": "INVALID_OUTPUT", "output": None}),
        ("SUCCESS", b'"' + b"x" * 2000 + b'"', {"status": "OUTPUT_LIMIT", "output": None}),
        ("TIMEOUT", b"", {"status": "TIMEOUT", "output": None}),
    ],
)
def test_execute_drops_privileges_and_always_kills_child_group(monkeypatch, status, raw, expected):
    monkeypatch.setattr(supervisor.os, "getpid", lambda: 1)
    monkeypatch.setattr(supervisor.os, "getuid", lambda: 0)
    child = Mock(pid=123, stdout=io.BytesIO(), stderr=io.BytesIO())
    spawn = Mock(return_value=child)
    kill = Mock(side_effect=ProcessLookupError)
    monkeypatch.setattr(supervisor.subprocess, "Popen", spawn)
    monkeypatch.setattr(supervisor, "collect", Mock(return_value=(status, raw)))
    monkeypatch.setattr(supervisor.os, "killpg", kill)
    job = {"source": "never executed", "payload": {}, "seconds": 1, "output_bytes": 1024}
    assert supervisor.execute(job) == expected
    argv = spawn.call_args.args[0]
    options = spawn.call_args.kwargs
    assert argv[1:5] == ["-I", "-S", "-B", "-c"] and json.loads(argv[-1]) == job
    assert options["user"] == options["group"] == 65532 and options["extra_groups"] == []
    assert options["start_new_session"] and options["stdin"] == subprocess.DEVNULL
    assert set(options["env"]) == {"PATH", "LANG"}
    kill.assert_called_once_with(123, supervisor.signal.SIGKILL)
    child.wait.assert_called_once_with()
    assert child.stdout.closed and child.stderr.closed


def test_entrypoint_refuses_host_and_emits_bound_result(monkeypatch, capsys):
    monkeypatch.setattr(supervisor.os, "getpid", lambda: 200)
    with pytest.raises(SystemExit, match="SANDBOX_PID_ONE_REQUIRED"):
        supervisor.execute({})
    with pytest.raises(SystemExit, match="SANDBOX_PID_ONE_REQUIRED"):
        runpy.run_path(supervisor.__file__, run_name="__main__")
    monkeypatch.setattr(supervisor.os, "getpid", lambda: 1)
    monkeypatch.setattr(supervisor.os, "getuid", lambda: 65532)
    with pytest.raises(SystemExit, match="SANDBOX_PID_ONE_REQUIRED"):
        supervisor.main()
    monkeypatch.setattr(supervisor.os, "getuid", lambda: 0)
    monkeypatch.setattr(supervisor.sys, "argv", ["supervisor.py", '{"request_hash":"identity"}'])
    monkeypatch.setattr(supervisor, "execute", lambda job: {"status": "SUCCESS", "output": [1]})
    supervisor.main()
    result = json.loads(capsys.readouterr().out)
    assert result["request_hash"] == "identity" and result["protocol"] == "native-tool-v1"
    assert result["output"] == [1]
