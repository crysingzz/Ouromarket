"""Authenticated task transport and readiness before any paid research call."""

import json
from unittest.mock import Mock

import httpx
import pytest
from pydantic import SecretStr
from test_engineering import SOURCE, spec

from adaptive_alpha.config import Settings
from adaptive_alpha.domain import digest, new_id
from adaptive_alpha.research import workflow
from adaptive_alpha.research.engineering import ImplementationBundle, WorkOrder
from adaptive_alpha.research.ouroboros import OuroborosEngineer

TOKEN = "service-credential-" + "a" * 40


def work_order():
    research = spec()
    return WorkOrder(
        id="work-" + new_id(),
        spec=research,
        spec_hash=digest(research.model_dump(mode="json")),
        input_digest="a" * 64,
        runtime_digest="b" * 64,
    )


def test_authenticated_workspace_task_result_and_cancel():
    work = work_order()
    bundle = ImplementationBundle(work_order_id=work.id, spec_hash=work.spec_hash, source=SOURCE)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer " + TOKEN
        if request.url.path == "/integration/status":
            return httpx.Response(200, json={"ready": True, "execution_enabled": True})
        if request.url.path == "/integration/workspaces":
            assert json.loads(request.content) == work.model_dump(mode="json")
            return httpx.Response(
                201,
                json={
                    "workspace_root": "/workspaces/" + work.id,
                    "work_order_id": work.id,
                    "spec_hash": work.spec_hash,
                },
            )
        if request.url.path == "/api/tasks":
            body = json.loads(request.content)
            assert body["workspace_root"] == "/workspaces/" + work.id
            assert body["metadata"] == {"source": "adaptive-alpha"}
            return httpx.Response(201, json={"task_id": "t1"})
        return httpx.Response(200, json={"status": "completed", "result": bundle.model_dump_json()})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = OuroborosEngineer(
            "http://runtime", "/workspaces", client, service_token=TOKEN, provision_workspaces=True
        )
        adapter.check_ready()
        assert adapter.implement(work, 5) == bundle
    assert calls[-1].url.path.endswith("/cancel")


@pytest.mark.parametrize(
    "reply",
    [
        {},
        {"workspace_root": "/control", "work_order_id": "forged", "spec_hash": "a" * 64},
    ],
)
def test_workspace_substitution_stops_before_task_create(reply):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(201, json=reply)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = OuroborosEngineer(
            "http://runtime", "/workspaces", client, service_token=TOKEN, provision_workspaces=True
        )
        with pytest.raises(ValueError, match="WORKSPACE_IDENTITY"):
            adapter.implement(work_order(), 5)
        with pytest.raises(ValueError, match="FROZEN_WORK_ORDER_REQUIRED"):
            adapter.generate({}, 5)
    assert calls == ["/integration/workspaces"]


def test_readiness_fails_closed_and_requires_service_credential(monkeypatch):
    with pytest.raises(ValueError, match="SERVICE_TOKEN_REQUIRED"):
        OuroborosEngineer("http://runtime", "/workspaces", provision_workspaces=True)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"ready": False}))
    )
    monkeypatch.setattr(httpx, "Client", Mock(return_value=client))
    with pytest.raises(ValueError, match="EXECUTION_NOT_READY"):
        OuroborosEngineer(
            "http://runtime", "/workspaces", service_token=TOKEN, provision_workspaces=True
        ).check_ready()


def test_unready_engineer_never_spends_research_tokens(monkeypatch, tmp_path):
    settings = Settings(
        secrets_dir=tmp_path,
        provider_vault_dir=tmp_path,
        ouroboros_url="http://runtime",
        ouroboros_workspace="/workspaces",
        ouroboros_token=SecretStr(TOKEN),
        ouroboros_provision_workspaces=True,
    )
    researcher = Mock()
    monkeypatch.setattr(workflow, "OpenAIProvider", researcher)
    monkeypatch.setattr(OuroborosEngineer, "check_ready", Mock(side_effect=ValueError("not ready")))
    with pytest.raises(ValueError, match="not ready"):
        workflow.implement_research(None, settings, "unused", {}, "dataset", 1000, 10, lambda: None)
    researcher.assert_not_called()


def test_service_token_is_loaded_from_mounted_secret(tmp_path):
    (tmp_path / "ouroboros_token").write_text(TOKEN)
    settings = Settings(secrets_dir=tmp_path, provider_vault_dir=tmp_path)
    assert settings.ouroboros_token.get_secret_value() == TOKEN
    assert TOKEN not in repr(settings)
