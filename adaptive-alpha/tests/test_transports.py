"""Offline HTTP contracts, resource bounds and failure redaction."""

import asyncio
import json
from unittest.mock import Mock

import httpx
import pytest
from pydantic import SecretStr
from test_autonomous import candidate, evidence
from test_portfolio_broker import order_intent

from adaptive_alpha.brokers.alpaca import AlpacaPaper, validate_order
from adaptive_alpha.research import literature, ouroboros, provider, setup
from adaptive_alpha.research.market_connector import AlpacaMarketData


@pytest.mark.parametrize(
    "payload,error",
    [(b"x" * 2000001, "UPSTREAM_RESPONSE_TOO_LARGE"), (b"[]", "UPSTREAM_OBJECT_REQUIRED")],
)
def test_bounded_json_rejects_large_or_non_object_response(payload, error):
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))
        ) as client,
        pytest.raises(ValueError, match=error),
    ):
        literature.bounded_json(client, "GET", "https://example.test")


def test_live_openai_transport_uses_hard_deadline_and_private_request(monkeypatch):
    real_client = httpx.AsyncClient
    received = []

    async def respond(request):
        received.append(request)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": candidate("e").model_dump_json()}
                        ],
                    }
                ],
            },
        )

    monkeypatch.setattr(
        provider.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    result, usage = provider.OpenAIProvider("fixture-key").generate("fixture", {}, 30000)
    assert result.evidence_ids == ["e"] and usage["provider"] == "openai"
    sent = json.loads(received[0].content)
    assert sent["store"] is False and "tools" not in sent
    assert received[0].url == "https://api.openai.com/v1/responses"

    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    monkeypatch.setattr(
        provider.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(slow), **kwargs),
    )
    with pytest.raises(TimeoutError):
        asyncio.run(provider.live_response({}, {}, 0.001))


@pytest.mark.parametrize(
    "body,error",
    [(b"[]", "UPSTREAM_OBJECT_REQUIRED"), (b"x" * 2000001, "UPSTREAM_RESPONSE_TOO_LARGE")],
)
def test_live_openai_body_bounds(monkeypatch, body, error):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        provider.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body)), **kwargs
        ),
    )
    with pytest.raises(ValueError, match=error):
        asyncio.run(provider.live_response({}, {}, 1))


@pytest.mark.parametrize(
    "response,error",
    [
        ({"status": "incomplete"}, "PROVIDER_INCOMPLETE_OR_REFUSED"),
        ({"status": "completed", "output": []}, "PROVIDER_STRUCTURED_OUTPUT_REQUIRED"),
    ],
)
def test_openai_refusal_and_missing_structured_content(response, error):
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
        ) as client,
        pytest.raises(ValueError, match=error),
    ):
        provider.OpenAIProvider("key", client).generate("fixture", {}, 30000)
    with pytest.raises(ValueError, match="OPENAI_KEY_NOT_CONFIGURED"):
        provider.OpenAIProvider("")


def test_provider_setup_without_injected_client_and_failed_connection(monkeypatch, tmp_path):
    real_client = httpx.Client
    monkeypatch.setattr(
        setup.httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"data": [{"id": "gpt-fixture"}]})
            ),
            **kwargs,
        ),
    )
    result = setup.configure_provider(
        tmp_path, setup.ProviderSetup(api_key=SecretStr("k" * 32), model="gpt-fixture")
    )
    assert result["configured"] and "api_key" not in result
    monkeypatch.setattr(
        setup.httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda _: httpx.Response(401)), **kwargs
        ),
    )
    with pytest.raises(ValueError, match="OPENAI_CONNECTION_FAILED_CHECK_KEY_AND_NETWORK"):
        setup.configure_provider(tmp_path, setup.ProviderSetup())
    with pytest.raises(ValueError, match="OPENAI_KEY_REQUIRED"):
        setup.configure_provider(tmp_path, setup.ProviderSetup(api_key=SecretStr("short")))
    with (
        real_client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": []}))
        ) as client,
        pytest.raises(ValueError, match="MODEL_NOT_AVAILABLE_FOR_THIS_KEY"),
    ):
        setup.configure_provider(tmp_path, setup.ProviderSetup(), client)


def test_search_sources_partial_failure_and_unknown_source(monkeypatch):
    monkeypatch.setattr(literature.OpenAlex, "search", lambda *_: [evidence()])
    monkeypatch.setattr(literature.Arxiv, "search", Mock(side_effect=httpx.ReadTimeout("offline")))
    monkeypatch.setattr(literature.SemanticScholar, "search", lambda *_: [])
    documents, health = literature.search_sources(
        "query", ["openalex", "arxiv", "semantic_scholar", "openalex"]
    )
    assert len(documents) == 1
    assert health == {
        "openalex": "available",
        "arxiv": "unavailable",
        "semantic_scholar": "no_results",
    }
    with pytest.raises(ValueError, match="UNKNOWN_RESEARCH_SOURCE"):
        literature.search_sources("query", ["unknown"])


def test_arxiv_response_size_limit():
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 2000001))
        ) as client,
        pytest.raises(ValueError, match="UPSTREAM_RESPONSE_TOO_LARGE"),
    ):
        literature.Arxiv(client).search("query")


def test_openalex_default_transport_skips_invalid_records(monkeypatch):
    original = httpx.Client

    def respond(request):
        assert request.url.host == "api.openalex.org"
        return httpx.Response(
            200,
            json={
                "results": [
                    None,
                    {"id": "untrusted-id"},
                    {"id": "https://openalex.org/W1", "title": "Valid paper"},
                ]
            },
        )

    monkeypatch.setattr(
        literature.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs),
    )
    documents = literature.OpenAlex().search("momentum")
    assert len(documents) == 1 and documents[0].title == "Valid paper"
    with pytest.raises(ValueError, match="INVALID_SEARCH_QUERY"):
        literature.OpenAlex().search("x")


@pytest.mark.parametrize(
    "outcome,error",
    [
        ({"status": "failed"}, "OUROBOROS_TASK_FAILED"),
        ({"status": "completed"}, "OUROBOROS_JSON_RESULT_REQUIRED"),
        ({"status": "queued"}, "OUROBOROS_DEADLINE"),
    ],
)
def test_ouroboros_failure_cancels_exact_task(monkeypatch, outcome, error):
    clock = [0.0]
    monkeypatch.setattr(ouroboros.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        ouroboros.time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay)
    )
    cancelled = []

    def respond(request):
        if request.url.path.endswith("/cancel"):
            cancelled.append(str(request.url))
            return httpx.Response(200, json={})
        return httpx.Response(
            200, json={"task_id": "task/1"} if request.method == "POST" else outcome
        )

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(ValueError, match=error),
    ):
        ouroboros.OuroborosEngineer("https://isolated.test", "/workspace", client).generate({}, 0.5)
    assert cancelled == ["https://isolated.test/api/tasks/task%2F1/cancel"]


def test_ouroboros_configuration_task_identity_and_nested_result(monkeypatch):
    with pytest.raises(ValueError, match="ISOLATED_OUROBOROS_NOT_CONFIGURED"):
        ouroboros.OuroborosEngineer("", "")
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))
        ) as client,
        pytest.raises(ValueError, match="OUROBOROS_TASK_ID_REQUIRED"),
    ):
        ouroboros.OuroborosEngineer("https://isolated.test", "/workspace", client).generate({}, 1)
    real_client = httpx.Client

    def respond(request):
        return httpx.Response(
            200,
            json={"task_id": "t"}
            if request.method == "POST"
            else {"status": "completed", "result": {"text": candidate("e").model_dump_json()}},
        )

    monkeypatch.setattr(
        ouroboros.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    assert ouroboros.OuroborosEngineer("https://isolated.test", "/workspace").generate(
        {}, 1
    ).evidence_ids == ["e"]


@pytest.mark.parametrize(
    "kind,error",
    [
        ("cycle", "UPSTREAM_PAGINATION_CYCLE"),
        ("pages", "UPSTREAM_PAGINATION_LIMIT"),
        ("rows", "DATASET_ROW_LIMIT"),
    ],
)
def test_market_pagination_bounds(kind, error):
    count = [0]

    def respond(request):
        count[0] += 1
        return httpx.Response(
            200,
            json={
                "bars": [{"t": "2020-01-01T00:00:00Z", "c": 1, "v": 1}]
                * (5001 if kind == "rows" else 0),
                "next_page_token": "same" if kind == "cycle" else str(count[0]),
            },
        )

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(ValueError, match=error),
    ):
        AlpacaMarketData("key", "secret", client).historical(
            "SPY", "2020-01-01T00:00:00Z", "2021-01-01T00:00:00Z"
        )


def test_market_invalid_credentials_dates_quote():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"quote": {"bp": 2, "ap": 1}})
        )
    ) as client:
        with pytest.raises(ValueError, match="ALPACA_DATA_CREDENTIALS_REQUIRED"):
            AlpacaMarketData("", "", client)
        feed = AlpacaMarketData("key", "secret", client)
        with pytest.raises(ValueError, match="INVALID_DATE_RANGE"):
            feed.historical("SPY", "2021-01-01T00:00:00Z", "2020-01-01T00:00:00Z")
        with pytest.raises(ValueError, match="INVALID_MARKET_QUOTE"):
            feed.latest_quote("SPY")


@pytest.mark.parametrize(
    "method,payload,error",
    [
        ("account", [], "BROKER_ACCOUNT_REQUIRED"),
        ("positions", {}, "BROKER_POSITIONS_REQUIRED"),
        ("by_client_id", [], "BROKER_ORDER_REQUIRED"),
    ],
)
def test_broker_rejects_wrong_response_shape(method, payload, error):
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as client,
        pytest.raises(ValueError, match=error),
    ):
        getattr(AlpacaPaper("key", "secret", client), method)(
            *([] if method != "by_client_id" else ["id"])
        )


def test_broker_bounds_status_and_idempotent_quantity_normalization():
    intent = order_intent()
    order = {**intent, "qty": "5.000", "id": "broker-id", "status": "new"}
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=order))
    ) as client:
        broker = AlpacaPaper("key", "secret", client)
        assert broker.submit(intent) == order
        with pytest.raises(ValueError, match="PAPER_BROKER_CREDENTIALS_REQUIRED"):
            AlpacaPaper("", "", client)
    for changed in ({"id": ""}, {"qty": "6"}):
        with pytest.raises(ValueError):
            validate_order({**order, **changed}, intent)
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        AlpacaPaper("key", "secret", client).by_client_id("id")
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 2000001))
        ) as client,
        pytest.raises(ValueError, match="BROKER_RESPONSE_TOO_LARGE"),
    ):
        AlpacaPaper("key", "secret", client).account()
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(404) if r.method == "GET" else httpx.Response(200, json=[])
            )
        ) as client,
        pytest.raises(ValueError, match="BROKER_ORDER_REQUIRED"),
    ):
        AlpacaPaper("key", "secret", client).submit(intent)
