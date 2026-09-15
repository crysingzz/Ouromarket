"""Safe opt-in arXiv HTML acquisition and truthful evidence-level reporting."""

from collections.abc import Callable

import httpx
import pytest
from test_autonomous import candidate, dataset

import adaptive_alpha.research.campaigns as campaign_module
from adaptive_alpha.config import Settings
from adaptive_alpha.domain import digest
from adaptive_alpha.research.campaigns import Campaigns
from adaptive_alpha.research.contracts import CampaignRequest, Evidence
from adaptive_alpha.research.datasets import import_dataset
from adaptive_alpha.research.evidence import build_evidence_packet
from adaptive_alpha.research.literature import Arxiv, arxiv_html_url
from adaptive_alpha.store import Store


def atom(identity: str = "https://arxiv.org/abs/2401.01234v2") -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>{identity}</id>
        <title>Robust momentum after costs</title>
        <summary>A reproducible momentum effect after estimated costs.</summary>
        <published>2025-01-02T00:00:00Z</published>
        <arxiv:license>https://creativecommons.org/licenses/by/4.0/</arxiv:license>
      </entry>
    </feed>""".encode()


def page_text() -> bytes:
    body = " ".join(
        [
            "The study specifies a twelve month momentum lookback and a one month skip.",
            "Signals are formed at month end and evaluated after transaction costs.",
            "The authors report turnover, drawdown, and out of sample performance.",
            "Replication still requires independent verification of equations and tables.",
        ]
        * 2000
    )
    return (
        "<html><head><style>HIDDEN STYLE</style><script>HIDDEN SCRIPT</script></head>"
        f"<body><nav>HIDDEN NAV</nav><article><h1>Paper</h1><p>{body}</p>"
        "<svg><text>HIDDEN SVG</text></svg></article></body></html>"
    ).encode()


def client_for(html: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "export.arxiv.org":
            return httpx.Response(
                200, content=atom(), headers={"content-type": "application/atom+xml"}
            )
        return html(request)

    return httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=False)


def test_arxiv_available_html_is_bounded_and_provenanced() -> None:
    seen: list[str] = []

    def html(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert request.url.host == "arxiv.org"
        assert request.url.path == "/html/2401.01234v2"
        assert request.headers["accept"] == "text/html"
        return httpx.Response(
            200, content=page_text(), headers={"content-type": "text/html; charset=utf-8"}
        )

    with client_for(html) as client:
        item = Arxiv(client, include_full_text=True).search("momentum")[0]
    assert seen == ["https://arxiv.org/html/2401.01234v2"]
    assert item.content_level == "full_text"
    assert item.full_text_source_url == "https://arxiv.org/html/2401.01234v2"
    assert item.license_url == "https://creativecommons.org/licenses/by/4.0/"
    assert item.full_text and len(item.full_text) == 100_000
    assert "twelve month momentum" in item.full_text
    assert "HIDDEN" not in item.full_text and "<" not in item.full_text
    packet = build_evidence_packet(
        "campaign-arxiv",
        "replication",
        "twelve month momentum",
        ("arxiv",),
        {"arxiv": "available"},
        [item],
        full_text_policy="available-arxiv-html",
    )
    assert packet.status == "REPLICATION_EVIDENCE_AVAILABLE"
    assert packet.full_text_policy == "available-arxiv-html"
    assert "FORMULAS_TABLES_AND_PARAMETERS_NOT_VERIFIED" in packet.gaps
    partial = build_evidence_packet(
        "campaign-partial",
        "replication",
        "momentum",
        ("arxiv",),
        {"arxiv": "available"},
        [
            item,
            item.model_copy(
                update={
                    "id": "evidence-abstract",
                    "content_level": "abstract",
                    "full_text": None,
                    "full_text_source_url": None,
                }
            ),
        ],
        full_text_policy="available-arxiv-html",
    )
    assert partial.status == "REPLICATION_EVIDENCE_INCOMPLETE"
    assert "FULL_TEXT_INCOMPLETE" in partial.gaps


def test_arxiv_full_text_fails_closed_to_abstract() -> None:
    for invalid in (
        "https://evil.test/abs/2401.01234",
        "https://arxiv.org:443/abs/2401.01234",
        "https://arxiv.org/html/2401.01234",
        "https://arxiv.org/abs/../admin",
        "https://arxiv.org/abs/2401.01234?download=1",
        "",
    ):
        with pytest.raises(ValueError, match="ARXIV_IDENTITY_INVALID"):
            arxiv_html_url(invalid)

    failures = (
        lambda _: httpx.Response(404),
        lambda _: httpx.Response(302, headers={"location": "https://evil.test/full-text"}),
        lambda _: httpx.Response(
            200, content=page_text(), headers={"content-type": "application/pdf"}
        ),
        lambda _: httpx.Response(
            200, content=b"x" * 2_000_001, headers={"content-type": "text/html"}
        ),
        lambda _: httpx.Response(
            200, content=b"<p>too short</p>", headers={"content-type": "text/html"}
        ),
    )
    for failure in failures:
        with client_for(failure) as client:
            item = Arxiv(client, include_full_text=True).search("momentum")[0]
        assert item.content_level == "abstract"
        assert item.full_text is None and item.full_text_source_url is None

    def invalid_feed(request: httpx.Request) -> httpx.Response:
        if request.url.host == "export.arxiv.org":
            return httpx.Response(200, content=atom("https://evil.test/abs/2401.01234"))
        raise AssertionError("invalid metadata identity must not be fetched")

    with httpx.Client(transport=httpx.MockTransport(invalid_feed)) as client:
        assert Arxiv(client, include_full_text=True).search("momentum") == []


def full_evidence() -> Evidence:
    payload = {
        "provider": "arxiv",
        "external_id": "https://arxiv.org/abs/2401.01234",
        "title": "Robust momentum after costs",
        "abstract": "A reproducible momentum effect after estimated costs.",
        "url": "https://arxiv.org/abs/2401.01234",
        "published": "2025-01-02",
        "references": [],
        "content_level": "full_text",
        "full_text": ("Twelve month momentum remains positive after estimated costs. " * 6),
        "full_text_source_url": "https://arxiv.org/html/2401.01234",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    }
    content_hash = digest(payload)
    return Evidence.model_validate(
        {
            **payload,
            "id": "evidence-" + digest(payload),
            "retrieved_at": "2026-09-15T00:00:00+00:00",
            "content_hash": content_hash,
        }
    )


def test_campaign_policy_produces_truthful_packet(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(settings.database_url)
    store.initialize()
    snapshot = import_dataset(store, dataset(), "operator")
    pipeline = Campaigns(store, settings)
    created = pipeline.create(
        CampaignRequest(
            objective="Replicate a fully specified momentum strategy",
            query="twelve month momentum",
            dataset_id=snapshot["id"],
            model="fixture",
            generations=1,
            token_budget=4000,
            sources=["arxiv"],
            full_text_policy="available-arxiv-html",
        ),
        "operator",
    )
    claimed = pipeline.claim()
    assert claimed is not None
    item = full_evidence()

    def search(query: str, sources: list[str], policy: str):
        assert (query, sources, policy) == (
            "twelve month momentum",
            ["arxiv"],
            "available-arxiv-html",
        )
        return [item], {"arxiv": "available"}

    monkeypatch.setattr(campaign_module, "search_sources", search)
    outcome = pipeline.run(
        *claimed,
        generate=lambda *_: (candidate(item.id), {}),
        hidden=lambda *_: {"verdict": "PASS", "score": 1.0},
    )
    assert outcome["status"] == "COMPLETED"
    with store.transaction() as conn:
        packet = store.related(conn, "evidence-packet", "campaign_id", created["id"])[0]
        searches = store.related(conn, "literature-search", "campaign_id", created["id"])
    assert packet["full_text_policy"] == "available-arxiv-html"
    assert packet["status"] == "REPLICATION_EVIDENCE_AVAILABLE"
    assert searches[0]["full_text_policy"] == "available-arxiv-html"
    store.engine.dispose()


def test_api_ui_expose_full_text_policy(client) -> None:
    snapshot = client.post("/api/datasets", json=dataset().model_dump(mode="json")).json()
    body = CampaignRequest(
        objective="Replicate a strategy from available full text",
        query="momentum specification",
        dataset_id=snapshot["id"],
        model="fixture",
        generations=1,
        token_budget=4000,
        sources=["arxiv"],
        full_text_policy="available-arxiv-html",
    ).model_dump(mode="json")
    response = client.post("/api/campaigns", json=body)
    assert response.status_code == 202
    assert response.json()["full_text_policy"] == "available-arxiv-html"
    assert client.get("/api/campaigns").json()[0]["full_text_policy"] == "available-arxiv-html"
    page = client.get("/").text
    javascript = client.get("/assets/app.js").text
    assert 'id="campaign-full-text-policy"' in page
    assert "available-arxiv-html" in page and "full_text_policy" in javascript
