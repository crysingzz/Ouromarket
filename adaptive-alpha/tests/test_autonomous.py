import json
import time
from datetime import UTC, datetime, timedelta

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from adaptive_alpha.config import Settings
from adaptive_alpha.domain import digest
from adaptive_alpha.evaluation.service import create_evaluator
from adaptive_alpha.research.backtest import backtest
from adaptive_alpha.research.campaigns import Campaigns
from adaptive_alpha.research.contracts import (
    Bar,
    CampaignRequest,
    Candidate,
    DatasetImport,
    Evidence,
)
from adaptive_alpha.research.datasets import import_dataset
from adaptive_alpha.research.literature import OpenAlex
from adaptive_alpha.research.program import Program
from adaptive_alpha.research.provider import OpenAIProvider
from adaptive_alpha.research.statistics import deflated_sharpe, pbo
from adaptive_alpha.store import Store

SOURCE = "def signal(history):\n    if len(history) < 20:\n        return 0\n    return 0.1 if history[-1] > sum(history[-20:])/20 else 0\n"


def dataset() -> DatasetImport:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    return DatasetImport(
        name="test",
        symbol="SPY",
        provenance="Seeded test fixture",
        adjustment="synthetic",
        bars=[
            Bar(
                time=(start + timedelta(days=i)).isoformat(),
                available_at=(start + timedelta(days=i)).isoformat(),
                close=100 + i * 0.05 + np.sin(i / 8) * 3,
                volume=1_000_000,
            )
            for i in range(360)
        ],
    )


def evidence() -> Evidence:
    return Evidence(
        provider="test",
        external_id="w1",
        title="Test paper",
        abstract="Test effect",
        url="https://example.org",
        published="2020-01-01",
        references=[],
        retrieved_at="2020-01-01",
        content_hash=digest("paper"),
    )


def candidate(evidence_id: str) -> Candidate:
    return Candidate(
        name="Generated test",
        hypothesis="A testable hypothesis",
        rationale="A testable mechanism",
        evidence_ids=[evidence_id],
        contradictions=[],
        failure_modes=["Costs"],
        source=SOURCE,
    )


@pytest.mark.parametrize(
    "body",
    [
        "import os\ndef signal(history):\n return 0",
        "def signal(history):\n return history.__class__",
        "def signal(history):\n return eval(1)",
        "def signal(history):\n while True:\n  return 0",
        "def signal(history):\n return [x for x in history]",
        "def signal(history):\n return 2**999999999",
        "@print\ndef signal(history):\n return 0",
        "def signal(history):\n history[0]=1\n return 0",
        "def signal(history):\n return signal(history)",
        "def signal(history):\n return 'x'",
    ],
)
def test_program_rejects_host_and_unbounded_operations(body: str) -> None:
    with pytest.raises(ValueError):
        Program(body)


def test_program_causality_and_position_contract() -> None:
    original = dataset()
    altered = original.model_copy(
        update={
            "bars": original.bars[:300]
            + [b.model_copy(update={"close": b.close * 2}) for b in original.bars[300:]]
        }
    )
    a, b = backtest(SOURCE, original), backtest(SOURCE, altered)
    assert a["returns"][:180] == b["returns"][:180]
    with pytest.raises(ValueError, match="FRACTION"):
        Program("def signal(history):\n return 2").signal([1.0, 2.0])
    with pytest.raises(ValueError, match="NUMERIC_ARITHMETIC"):
        Program("def signal(history):\n return history*999999999").signal([1.0, 2.0])


def test_dataset_immutability_and_availability(settings: Settings) -> None:
    store = Store(settings.database_url)
    store.initialize()
    data = dataset()
    a = import_dataset(store, data, "operator")
    assert import_dataset(store, data, "operator")["id"] == a["id"]
    invalid = data.model_copy(update={"bars": list(reversed(data.bars))})
    with pytest.raises(ValueError, match="ORDER"):
        import_dataset(store, invalid, "operator")


def test_openalex_and_openai_transport_contracts() -> None:
    ev = evidence()

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openalex.org":
            assert request.url.params["search"] == "momentum"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "https://openalex.org/W1",
                            "title": "Paper",
                            "abstract_inverted_index": {"effect": [1], "Test": [0]},
                        }
                    ]
                },
            )
        body = json.loads(request.content)
        assert body["store"] is False and body["model"] == "configured-model"
        assert body["text"]["format"]["strict"] is True
        assert "tools" not in body
        return httpx.Response(
            200,
            json={
                "id": "r1",
                "status": "completed",
                "usage": {"input_tokens": 100, "output_tokens": 200},
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": candidate(ev.id).model_dump_json()}
                        ],
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        first = OpenAlex(client).search("momentum")[0]
        second = OpenAlex(client).search("momentum")[0]
        assert first.abstract == "Test effect" and first.content_level == "abstract"
        assert first.id == second.id and first.content_hash == second.content_hash
        provider = OpenAIProvider("test-key", client)
        result, usage = provider.generate("configured-model", {}, 20_000)
        assert result.source == SOURCE and usage["output_tokens"] == 200
        with pytest.raises(ValueError, match="BUDGET"):
            provider.generate("configured-model", {}, 100)


def test_campaign_pipeline_and_fenced_claim(settings: Settings) -> None:
    store = Store(settings.database_url)
    store.initialize()
    ds = import_dataset(store, dataset(), "operator")
    pipeline = Campaigns(store, settings)
    request = CampaignRequest(
        objective="Find testable effects",
        query="momentum",
        dataset_id=ds["id"],
        model="fixture",
        generations=2,
    )
    pipeline.create(request, "operator")
    claimed = pipeline.claim()
    assert claimed is not None and pipeline.claim() is None
    ev = evidence()

    def generate(model, context, budget):
        assert "hidden" not in json.dumps(context)
        return candidate(ev.id), {"input_tokens": 10, "output_tokens": 20}

    result = pipeline.run(
        *claimed,
        generate=generate,
        search=lambda q: [ev],
        hidden=lambda *args: {"verdict": "PASS", "score": 1},
    )
    assert result["status"] == "COMPLETED" and result["attempts"] == 2
    with store.transaction() as conn:
        assert len(store.list_records(conn, "candidate")) == 2
        assert len(store.list_records(conn, "autonomous-attempt")) == 2
        assert store.verify_audit(conn)


def test_campaign_crash_and_unknown_provider_outcome(settings: Settings) -> None:
    store = Store(settings.database_url)
    store.initialize()
    ds = import_dataset(store, dataset(), "operator")
    pipeline = Campaigns(store, settings)
    request = CampaignRequest(
        objective="Find testable effects", query="momentum", dataset_id=ds["id"], model="fixture"
    )
    created = pipeline.create(request, "operator")
    claimed = pipeline.claim()
    assert claimed
    with store.transaction() as conn:
        state = store.state(conn, "campaign:" + created["id"])
        state["lease_until"] = time.time() - 1
        store.set_state(conn, "campaign:" + created["id"], state)
        store.append(
            conn,
            "agent-evolution-attempt",
            {"id": "lost-reflection", "campaign_id": created["id"], "reserved_tokens": 4000},
        )
    assert pipeline.claim() is None
    assert pipeline.list()[0]["status"] == "INTERRUPTED"
    assert pipeline.claim() is None
    with store.transaction() as conn:
        recovered = store.related(conn, "agent-evolution-result", "campaign_id", created["id"])
        assert len(recovered) == 1 and recovered[0]["status"] == "INTERRUPTED"
    pipeline.create(request, "operator")
    claimed = pipeline.claim()
    assert claimed

    def fail(*args):
        raise httpx.ReadTimeout("secret must not be disclosed")

    outcome = pipeline.run(*claimed, generate=fail, search=lambda q: [evidence()])
    assert outcome["tokens_charged"] > 0
    assert "secret" not in json.dumps(outcome)
    with store.transaction() as conn:
        assert store.list_records(conn, "candidate-result")[0]["status"] == "ERROR"


def test_unsupported_citation_is_retained_without_fabricated_graph_edge(settings: Settings) -> None:
    store = Store(settings.database_url)
    store.initialize()
    ds = import_dataset(store, dataset(), "operator")
    pipeline = Campaigns(store, settings)
    pipeline.create(
        CampaignRequest(
            objective="Check invented citations",
            query="momentum",
            dataset_id=ds["id"],
            model="fixture",
            generations=1,
        ),
        "operator",
    )
    claimed = pipeline.claim()
    assert claimed
    outcome = pipeline.run(
        *claimed,
        generate=lambda *_: (
            candidate("invented-publication"),
            {"input_tokens": 100, "output_tokens": 100},
        ),
        search=lambda _: [evidence()],
    )
    assert outcome["status"] == "COMPLETED"
    with store.transaction() as conn:
        assert store.list_records(conn, "candidate")[0]["evidence_ids"] == ["invented-publication"]
        assert (
            store.list_records(conn, "candidate-result")[0]["reason"]
            == "UNSUPPORTED_EVIDENCE_CITATION"
        )
        assert not store.list_records(conn, "knowledge-edge")


def test_generated_hidden_feedback_is_minimal_and_idempotent(settings: Settings) -> None:
    with TestClient(create_evaluator(settings)) as client:
        client.headers["Authorization"] = "Bearer " + settings.token("evaluator_token")
        payload = {"experiment_id": "program-test", "source": SOURCE, "symbol": "SPY"}
        first = client.post("/evaluate-program", json=payload)
        assert first.status_code == 200 and set(first.json()) == {"verdict", "score"}
        assert client.post("/evaluate-program", json=payload).json() == first.json()
        assert (
            client.post("/evaluate-program", json={**payload, "source": SOURCE + "\n"}).status_code
            == 409
        )


def test_scientific_diagnostics_degenerate_and_non_degenerate() -> None:
    rng = np.random.default_rng(3)
    matrix = rng.normal(0, 0.01, (360, 4))
    assert pbo(matrix)["splits"] == 70
    assert 0 <= pbo(matrix)["probability"] <= 1
    assert deflated_sharpe(matrix[:, 0], [0.01, 0.02, -0.01, 0.03])["probability"] is not None
    assert pbo(matrix[:, :1])["probability"] is None


def test_campaign_api_permissions(client: TestClient) -> None:
    created = client.post("/api/datasets", json=dataset().model_dump(mode="json"))
    assert created.status_code == 201
    assert client.get("/api/research/readiness").status_code == 200
    client.headers["Authorization"] = "Bearer " + "r" * 48
    body = CampaignRequest(
        objective="Find testable effects",
        query="momentum",
        dataset_id=created.json()["id"],
        model="fixture",
    )
    assert client.post("/api/campaigns", json=body.model_dump()).status_code == 403


def test_provider_setup_keeps_secret_local_and_rejects_research(
    client: TestClient, settings: Settings, monkeypatch
) -> None:
    from adaptive_alpha.research import setup
    from adaptive_alpha.research.setup import ProviderSetup, configure_provider

    key = "sk-test-" + "x" * 40

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.openai.com" and request.url.path == "/v1/models"
        return httpx.Response(
            200, json={"data": [{"id": "gpt-fixture"}, {"id": "gpt-image-fixture"}]}
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        result = configure_provider(
            settings.provider_vault_dir,
            ProviderSetup(api_key=SecretStr(key), model="gpt-fixture"),
            transport,
        )
    assert result["models"] == ["gpt-fixture"]
    assert key not in json.dumps(result)
    assert setup.load_provider(settings.provider_vault_dir)["api_key"] == key
    assert (settings.provider_vault_dir / "openai.json").stat().st_mode & 0o777 == 0o600
    # Invalid bodies never echo credentials in FastAPI validation details.
    invalid = client.post("/api/provider/setup", json={"api_key": key, "model": {"secret": key}})
    assert invalid.status_code == 422 and key not in invalid.text
    client.headers["Authorization"] = "Bearer " + "r" * 48
    assert client.post("/api/provider/setup", json={"api_key": key}).status_code == 403


def test_preregistered_agent_benchmark_has_equal_budgets_and_no_early_promotion(
    client: TestClient,
) -> None:
    ds = client.post("/api/datasets/demo").json()
    revision = client.post(
        "/api/agents/revisions",
        json={
            "name": "Cost-aware research",
            "research_instructions": "Prioritize falsification and low turnover mechanisms.",
            "openspec_rationale": "Change research prompt only; keep evaluation and risk immutable.",
        },
    )
    assert revision.status_code == 201
    benchmark = client.post(
        "/api/agents/benchmarks",
        json={
            "objective": "Test persistence after costs",
            "query": "equity momentum",
            "dataset_id": ds["id"],
            "model": "fixture",
            "challenger_revision_id": revision.json()["id"],
        },
    )
    assert benchmark.status_code == 202
    identity = benchmark.json()["id"]
    report = client.get(f"/api/agents/benchmarks/{identity}").json()
    assert (
        report["arms"]["static"]["tokens_reserved"]
        == report["arms"]["adaptive"]["tokens_reserved"]
        == 0
    )
    assert not report["promotion_evidence"]
    assert client.post(f"/api/agents/benchmarks/{identity}/promote").status_code == 409


def test_forward_paper_is_idempotent_and_kill_switch_blocks(settings: Settings) -> None:
    from adaptive_alpha.research.forward import ForwardPaper

    store = Store(settings.database_url)
    store.initialize()
    data = dataset()
    manifest = import_dataset(store, data, "test")
    source = "def signal(history):\n    return 0.05\n"
    with store.transaction() as conn:
        store.append(
            conn,
            "candidate",
            {
                "id": "forward-test",
                "dataset_id": manifest["id"],
                "source": source,
                "source_hash": digest(source),
            },
            "forward-test",
        )
        store.append(
            conn,
            "candidate-result",
            {
                "id": "forward-test",
                "status": "PASS",
                "public": {"verdict": "PASS"},
                "hidden": {"verdict": "PASS", "score": 1},
            },
        )
        store.set_state(conn, "kill", {"halted": True})
    paper = ForwardPaper(store)
    paper.admit("forward-test", "operator")
    clock = datetime.fromisoformat(data.bars[-1].time) + timedelta(seconds=1)
    quote = {"timestamp": clock.isoformat(), "prices": {"SPY": data.bars[-1].close}}
    assert paper.step("forward-test", data, quote, clock=clock)["status"] == "REJECTED"
    with store.transaction() as conn:
        store.set_state(conn, "kill", {"halted": False})
    assert paper.step("forward-test", data, quote, clock=clock)["status"] == "FILLED"
    assert paper.step("forward-test", data, quote, clock=clock)["status"] == "NO_NEW_BAR"
    # Held positions are checked without a new daily strategy signal.
    crash_quote = {**quote, "prices": {"SPY": data.bars[-1].close * 0.1}}
    assert paper.step("forward-test", data, crash_quote, clock=clock)["status"] == "HALT"
    assert (
        paper.step("forward-test", data, quote, clock=clock + timedelta(seconds=61))["reason"]
        == "STALE_QUOTE"
    )
    with store.transaction() as conn:
        assert len(store.list_records(conn, "forward-fill")) == 1
        assert store.verify_audit(conn)


def test_market_adapter_pagination_and_quote() -> None:
    from adaptive_alpha.research.market_connector import AlpacaMarketData

    fixture = dataset()

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "data.alpaca.markets"
        if request.url.path.endswith("/quotes/latest"):
            return httpx.Response(
                200, json={"quote": {"bp": 100, "ap": 101, "t": "2024-01-01T12:00:00Z"}}
            )
        rows = fixture.bars[:180] if "page_token" not in request.url.params else fixture.bars[180:]
        return httpx.Response(
            200,
            json={
                "bars": [{"t": b.time, "c": b.close, "v": b.volume} for b in rows],
                "next_page_token": "page2" if "page_token" not in request.url.params else None,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        feed = AlpacaMarketData("key", "secret", client)
        result = feed.historical("SPY", "2020-01-01T00:00:00Z", "2021-01-01T00:00:00Z")
        assert len(result.bars) == 360 and result.point_in_time_verified is False
        assert result.bars[0].time.startswith("2020-01-02")
        assert feed.latest_quote("SPY")["prices"] == {"SPY": 100.5}


def test_ouroboros_adapter_uses_actual_task_contract() -> None:
    from adaptive_alpha.research.ouroboros import OuroborosEngineer

    ev = evidence()
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/tasks":
            body = json.loads(request.content)
            assert body["workspace_mode"] == "external" and body["memory_mode"] == "forked"
            assert body["workspace_root"] == "/isolated/research"
            return httpx.Response(200, json={"task_id": "t1"})
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={"status": "completed"})
        return httpx.Response(
            200, json={"status": "completed", "result": candidate(ev.id).model_dump_json()}
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        adapter = OuroborosEngineer("http://isolated-runtime", "/isolated/research", client)
        assert adapter.generate({"objective": "test"}, 30).source == SOURCE
    assert calls[-1] == ("POST", "/api/tasks/t1/cancel")


def test_program_cannot_construct_exponential_nested_comparisons() -> None:
    with pytest.raises(ValueError, match="FLAT_NUMERIC"):
        Program("def signal(history):\n    a = [1]\n    b = [a, a]\n    return 0").signal([100.0])
    with pytest.raises(ValueError, match="NUMERIC_COMPARISON"):
        Program("def signal(history):\n    return 0.1 if history == history else 0").signal([100.0])


def test_artifact_store_rejects_tampering_and_paths(tmp_path) -> None:
    from adaptive_alpha.artifacts import ArtifactStore

    root = tmp_path / "blobs"
    artifacts = ArtifactStore(root)
    descriptor = artifacts.put(b"immutable bytes", "application/octet-stream")
    assert artifacts.put(b"immutable bytes", "application/octet-stream") == descriptor
    assert artifacts.get(descriptor["id"]) == b"immutable bytes"
    with pytest.raises(ValueError, match="INVALID_ARTIFACT"):
        artifacts.get("../secret")
    path = root / descriptor["id"]
    path.chmod(0o600)
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="INTEGRITY"):
        artifacts.get(descriptor["id"])


def test_reflection_is_budgeted_and_cannot_promote_itself(settings: Settings, monkeypatch) -> None:
    from adaptive_alpha.research.benchmark import AgentRevision

    store = Store(settings.database_url)
    store.initialize()
    manifest = import_dataset(store, dataset(), "test")
    configured = settings.model_copy(update={"openai_api_key": SecretStr("fixture-key")})
    pipeline = Campaigns(store, configured)
    pipeline.create(
        CampaignRequest(
            objective="Test reflexive research",
            query="momentum",
            dataset_id=manifest["id"],
            model="fixture",
            generations=1,
            token_budget=40000,
            propose_agent_revision=True,
        ),
        "operator",
    )
    claimed = pipeline.claim()
    assert claimed
    ev = evidence()

    def reflect(self, model, context, budget, response_type, instructions):
        assert "hidden" not in json.dumps(context)
        return AgentRevision(
            name="Revision from public evidence",
            research_instructions="Prioritize fewer trades and explicit contrary evidence.",
            openspec_rationale="Improve only the research workflow; keep evaluation and finance controls unchanged.",
        ), {"input_tokens": 100, "output_tokens": 100}

    monkeypatch.setattr(OpenAIProvider, "structured", reflect)
    outcome = pipeline.run(
        *claimed,
        generate=lambda *args: (candidate(ev.id), {"input_tokens": 10, "output_tokens": 20}),
        search=lambda query: [ev],
        hidden=lambda *args: {"verdict": "PASS", "score": 1},
    )
    assert outcome["status"] == "COMPLETED" and outcome["tokens_charged"] == 40000
    with store.transaction() as conn:
        assert len(store.list_records(conn, "agent-revision")) == 1
        assert not store.state(conn, "active-research-revision")


def test_arxiv_xml_blocks_entities_and_scholar_normalizes() -> None:
    from defusedxml.common import DefusedXmlException

    from adaptive_alpha.research.literature import Arxiv, SemanticScholar

    xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/1</id><title>Test</title><summary>Abstract</summary><published>2020-01-01</published></entry></feed>'
    malicious = b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><feed>&x;</feed>'

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "export.arxiv.org":
            return httpx.Response(
                200, content=malicious if "malicious" in str(request.url) else xml
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "paperId": "1",
                        "title": "Paper",
                        "abstract": "Effect",
                        "year": 2020,
                        "references": [{"paperId": "2"}],
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert Arxiv(client).search("momentum")[0].title == "Test"
        with pytest.raises(DefusedXmlException):
            Arxiv(client).search("malicious")
        assert SemanticScholar(client).search("momentum")[0].references == ["2"]


def test_walk_forward_never_selects_using_test_returns() -> None:
    from adaptive_alpha.research.walk_forward import rolling_selection

    rng = np.random.default_rng(51)
    matrix = rng.normal(0, 0.01, (360, 3))
    first = rolling_selection(matrix)
    perturbed = matrix.copy()
    perturbed[200:, 0] += 0.1
    second = rolling_selection(perturbed)
    assert first["folds"][:3] == second["folds"][:3]
    assert first["returns"][:75] == second["returns"][:75]
    assert all(f["train_end_exclusive"] + 5 == f["test_start"] for f in first["folds"])
