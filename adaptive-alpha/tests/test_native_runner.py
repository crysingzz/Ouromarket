"""Controller faults use a fake Docker transport; no submitted Python runs here."""

import json
import threading
from unittest.mock import Mock

import httpx
import pytest

from adaptive_alpha.runner import docker
from adaptive_alpha.runner.contracts import PROTOCOL, ToolRequest
from adaptive_alpha.runner.docker import DEADLINE, LABEL, OWNER, DockerRunner

IMAGE = "sha256:" + "a" * 64
REQUEST = ToolRequest(source="def run(payload): return payload")
NAME = "alpha-tool-00000000-0000-0000-0000-000000000001"


def frame(value):
    data = json.dumps(value).encode()
    return b"\x01\0\0\0" + len(data).to_bytes(4, "big") + data


class Daemon:
    def __init__(self):
        self.calls = []
        self.config = None
        self.runtimes = {"runsc": {}, "runc": {}}
        self.image = {
            "Id": IMAGE,
            "Config": {"Labels": {"org.ouromarket.runner.protocol": PROTOCOL}},
        }
        self.states = [{"Running": False, "ExitCode": 0}]
        self.result = {"status": "SUCCESS", "output": {"ok": True}, "protocol": PROTOCOL}
        self.raw = None
        self.error_at = ""
        self.delete_status = 204
        self.on_create = lambda: None
        self.items = []

    def handle(self, request):
        path = request.url.path.removeprefix("/v1.47")
        self.calls.append((request.method, path))
        if self.error_at and self.error_at in path:
            raise httpx.ReadTimeout("controlled transport loss")
        if path == "/info":
            return httpx.Response(200, json={"Runtimes": self.runtimes})
        if path.startswith("/images/"):
            return httpx.Response(200, json=self.image)
        if path == "/containers/create":
            self.config = json.loads(request.content)
            self.on_create()
            return httpx.Response(201, json={"Id": "container"})
        if path == "/containers/json":
            assert json.loads(request.url.params["filters"]) == {"label": [LABEL + "=" + OWNER]}
            return httpx.Response(200, json=self.items)
        if request.method == "DELETE":
            assert dict(request.url.params) == {"force": "true", "v": "true"}
            return httpx.Response(self.delete_status)
        if path.endswith("/start"):
            return httpx.Response(204)
        if path.endswith("/json"):
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            return httpx.Response(200, json={"State": state})
        assert path.endswith("/logs")
        job = json.loads(self.config["Cmd"][0])
        body = {"request_hash": job["request_hash"], **self.result}
        return httpx.Response(200, content=self.raw if self.raw is not None else frame(body))

    def runner(self, **kwargs):
        return DockerRunner(
            httpx.Client(transport=httpx.MockTransport(self.handle), base_url="http://docker"),
            IMAGE,
            **kwargs,
        )


def test_request_bounds_identity_and_unknown_fields():
    assert REQUEST.fingerprint == ToolRequest.model_validate(REQUEST.model_dump()).fingerprint
    for update in ({"seconds": 31}, {"source": "x"}, {"mount": "/secret"}, {"output_bytes": 1}):
        with pytest.raises(ValueError):
            ToolRequest.model_validate({**REQUEST.model_dump(), **update})
    with pytest.raises(ValueError, match="TOOL_INPUT_TOO_LARGE"):
        ToolRequest(source=REQUEST.source, payload={"data": "x" * 60000})
    with pytest.raises(ValueError):
        ToolRequest(source=REQUEST.source, payload={"data": float("nan")})
    with pytest.raises(ValueError, match="PINNED_RUNNER_IMAGE_REQUIRED"):
        DockerRunner(httpx.Client(), "runner:latest")


def test_production_policy_and_provenance():
    daemon = Daemon()
    result = daemon.runner().run(REQUEST)
    assert result["status"] == "SUCCESS" and result["output"] == {"ok": True}
    assert result["cleanup_confirmed"] and not result["capital_eligible"]
    assert result["request_hash"] == REQUEST.fingerprint
    assert result["runtime"] == "runsc" and not result["fixture_only"]
    config = daemon.config
    assert config["Image"] == IMAGE and config["NetworkDisabled"]
    assert config["Entrypoint"] == [
        "/usr/local/bin/python",
        "-I",
        "-S",
        "-B",
        "/runner/supervisor.py",
    ]
    assert len(config["Cmd"]) == 1 and json.loads(config["Cmd"][0])["source"] == REQUEST.source
    policy = config["HostConfig"]
    assert policy["ReadonlyRootfs"] and policy["NetworkMode"] == "none"
    assert policy["CapDrop"] == ["ALL"] and policy["CapAdd"] == ["SETUID", "SETGID", "KILL"]
    assert policy["SecurityOpt"] == ["no-new-privileges:true"]
    assert policy["PidsLimit"] == 32 and policy["Memory"] == policy["MemorySwap"] == 201326592
    assert "Binds" not in policy and "Mounts" not in policy and not policy.get("Privileged")
    assert "noexec,nosuid,nodev,size=32m" in policy["Tmpfs"]["/tmp"]  # noqa: S108
    assert daemon.calls[-1][0] == "DELETE"


def test_runtime_image_and_fixture_gates():
    daemon = Daemon()
    daemon.runtimes = {"runc": {}}
    with pytest.raises(ValueError, match="GVISOR_REQUIRED"):
        daemon.runner().run(REQUEST)
    assert not any(method == "POST" for method, _ in daemon.calls)
    runner = daemon.runner(development_fixtures=True)
    with pytest.raises(ValueError, match="DEVELOPMENT_FIXTURES_ONLY"):
        runner.run(REQUEST)
    result = runner.run_fixture("echo")
    assert result["fixture_only"] and result["runtime"] == "runc"
    daemon.image["Id"] = "different"
    with pytest.raises(ValueError, match="RUNNER_IMAGE_MISMATCH"):
        runner.run_fixture("echo")
    daemon.image["Id"] = IMAGE
    daemon.image["Config"]["Labels"] = {}
    with pytest.raises(ValueError, match="RUNNER_IMAGE_MISMATCH"):
        runner.run_fixture("echo")
    with pytest.raises(ValueError):
        runner._run(REQUEST.model_copy(update={"seconds": 100}), threading.Event())


@pytest.mark.parametrize("moment", ["before", "create", "running"])
def test_cancellation_removes_whole_container(moment):
    daemon, cancel = Daemon(), threading.Event()
    if moment == "before":
        cancel.set()
    elif moment == "create":
        daemon.on_create = cancel.set
    else:
        daemon.states = [{"Running": True}]
        cancel.wait = Mock(side_effect=lambda _: cancel.set())
    result = daemon.runner().run(REQUEST, cancel)
    assert result["status"] == "CANCELLED" and result["cleanup_confirmed"]
    if moment == "before":
        assert not any(method in {"POST", "DELETE"} for method, _ in daemon.calls)
    else:
        assert daemon.calls[-1][0] == "DELETE"
    if moment == "create":
        assert not any(path.endswith("/start") for _, path in daemon.calls)


def test_host_deadline_independent_of_child(monkeypatch):
    daemon = Daemon()
    daemon.states = [{"Running": True}]
    monkeypatch.setattr(docker.time, "monotonic", Mock(side_effect=[0, 100]))
    result = daemon.runner().run(REQUEST)
    assert result["status"] == "TIMEOUT" and result["cleanup_confirmed"]


@pytest.mark.parametrize(
    "state,expected",
    [
        ({"Running": False, "ExitCode": 137, "OOMKilled": True}, "RESOURCE_LIMIT"),
        ({"Running": False, "ExitCode": 1}, "TOOL_FAILED"),
        ({"Running": False}, "RUNNER_ERROR"),
    ],
)
def test_container_failure_is_not_success(state, expected):
    daemon = Daemon()
    daemon.states = [state]
    assert daemon.runner().run(REQUEST)["status"] == expected


@pytest.mark.parametrize(
    "error_at,expected",
    [
        ("/create", "CLEANUP_UNCONFIRMED"),
        ("/start", "RUNNER_ERROR"),
        ("/logs", "RUNNER_ERROR"),
    ],
)
def test_transport_failure_cleanup_and_ambiguous_create(error_at, expected):
    daemon = Daemon()
    daemon.error_at = error_at
    daemon.delete_status = 404
    runner = daemon.runner()
    result = runner.run(REQUEST)
    assert result["status"] == expected
    assert runner.quarantined == (error_at == "/create")
    assert daemon.calls[-1][0] == "DELETE"
    if runner.quarantined:
        with pytest.raises(ValueError, match="RUNNER_QUARANTINED"):
            runner.run(REQUEST)
        assert runner.recover() == {"removed": [], "quarantined": True}


def test_unconfirmed_delete_quarantines_controller():
    daemon = Daemon()
    daemon.delete_status = 500
    runner = daemon.runner()
    assert runner.run(REQUEST)["status"] == "CLEANUP_UNCONFIRMED"
    assert runner.quarantined
    daemon.error_at = "alpha-tool-"
    assert not runner._remove(NAME)


@pytest.mark.parametrize(
    "raw", [b"", b"x", b"\x02\0\0\0\0\0\0\0", b"\x01\0\0\0\0\0\0\xff", b"x" * 131073]
)
def test_malformed_or_excess_logs_fail_closed(raw):
    daemon = Daemon()
    daemon.raw = raw
    result = daemon.runner().run(REQUEST)
    assert result["status"] == "RUNNER_ERROR" and result["output"] is None


@pytest.mark.parametrize(
    "update",
    [
        {"request_hash": "forged"},
        {"protocol": "old"},
        {"status": "invented"},
        {"output": "x" * 20000},
        {"output": float("nan")},
    ],
)
def test_result_identity_and_size(update):
    daemon = Daemon()
    daemon.result.update(update)
    assert daemon.runner().run(REQUEST)["status"] == "RUNNER_ERROR"


def owned(deadline="0", name=NAME):
    return {"Labels": {LABEL: OWNER, DEADLINE: deadline, "org.ouromarket.runner.name": name}}


def test_recovery_only_reaps_expired_owned_containers():
    daemon = Daemon()
    daemon.items = [owned(), owned("99999999999"), owned(name="another-container"), {"Labels": {}}]
    assert daemon.runner().recover() == {"removed": [NAME], "quarantined": False}
    assert [path for method, path in daemon.calls if method == "DELETE"] == ["/containers/" + NAME]
    daemon.delete_status = 500
    runner = daemon.runner()
    with pytest.raises(ValueError, match="RUNNER_CLEANUP_REQUIRED"):
        runner.recover()
    assert runner.quarantined


@pytest.mark.parametrize("deadline", ["nan", "inf", "bad", None])
def test_invalid_owned_lease_requires_operator(deadline):
    daemon = Daemon()
    daemon.items = [owned(deadline)]
    runner = daemon.runner()
    with pytest.raises(ValueError, match="RUNNER_INVALID_LEASE"):
        runner.recover()
    assert runner.quarantined
