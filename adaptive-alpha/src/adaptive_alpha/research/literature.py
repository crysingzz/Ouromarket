"""Fixed-origin literature connectors with bounded, inert full-text extraction."""

import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import httpx

from adaptive_alpha.domain import digest, now
from adaptive_alpha.research.contracts import Evidence, FullTextPolicy

MAX_UPSTREAM_BYTES = 2_000_000
MAX_FULL_TEXT_CHARS = 100_000
MAX_ARXIV_FULL_TEXTS = 3


def bounded_json(client: httpx.Client, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    with client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > MAX_UPSTREAM_BYTES:
                raise ValueError("UPSTREAM_RESPONSE_TOO_LARGE")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("UPSTREAM_OBJECT_REQUIRED")
        return result


class OpenAlex:
    capabilities = frozenset({"search", "metadata", "references"})

    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    def search(self, query: str) -> list[Evidence]:
        if not 3 <= len(query) <= 300:
            raise ValueError("INVALID_SEARCH_QUERY")
        if self.client:
            raw = bounded_json(
                self.client,
                "GET",
                "https://api.openalex.org/works",
                params={"search": query, "per-page": 8},
            )
        else:
            with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
                raw = bounded_json(
                    client,
                    "GET",
                    "https://api.openalex.org/works",
                    params={"search": query, "per-page": 8},
                )
        evidence = []
        for work in raw.get("results", [])[:8]:
            if not isinstance(work, dict):
                continue
            words: dict[int, str] = {}
            inverted = work.get("abstract_inverted_index") or {}
            for word, positions in inverted.items():
                for position in positions[:3000]:
                    if isinstance(position, int) and 0 <= position < 3000:
                        words[position] = str(word)[:100]
            abstract = " ".join(words[i] for i in sorted(words))[:16_000]
            external = str(work.get("id", ""))
            if not external.startswith("https://openalex.org/W"):
                continue
            payload = dict(
                provider="openalex",
                external_id=external,
                title=str(work.get("title") or "Untitled")[:2000],
                abstract=abstract,
                url=str(work.get("doi") or external),
                published=str(work.get("publication_date") or "unknown"),
                references=[str(x) for x in work.get("referenced_works", [])[:100]],
                content_level="abstract",
                full_text=None,
                full_text_source_url=None,
                license_url=None,
            )
            content_hash = digest(payload)
            evidence.append(
                Evidence.model_validate(
                    {
                        **payload,
                        "id": "evidence-"
                        + digest(
                            {
                                "provider": payload["provider"],
                                "external_id": payload["external_id"],
                                "content_hash": content_hash,
                            }
                        ),
                        "retrieved_at": now(),
                        "content_hash": content_hash,
                    }
                )
            )
        return evidence


class SemanticScholar:
    capabilities = frozenset({"search", "metadata", "references"})

    def __init__(self, client: httpx.Client):
        self.client = client

    def search(self, query: str) -> list[Evidence]:
        raw = bounded_json(
            self.client,
            "GET",
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": 8,
                "fields": "title,abstract,year,url,references.paperId",
            },
        )
        result = []
        for paper in raw.get("data", [])[:8]:
            payload = {
                "provider": "semantic_scholar",
                "external_id": str(paper["paperId"]),
                "title": str(paper.get("title") or "Untitled")[:2000],
                "abstract": str(paper.get("abstract") or "")[:16000],
                "url": str(paper.get("url") or ""),
                "published": str(paper.get("year") or "unknown"),
                "references": [
                    str(r["paperId"])
                    for r in (paper.get("references") or [])[:100]
                    if r.get("paperId")
                ],
                "content_level": "abstract",
                "full_text": None,
                "full_text_source_url": None,
                "license_url": None,
            }
            content_hash = digest(payload)
            result.append(
                Evidence.model_validate(
                    {
                        **payload,
                        "id": "evidence-"
                        + digest(
                            {
                                "provider": payload["provider"],
                                "external_id": payload["external_id"],
                                "content_hash": content_hash,
                            }
                        ),
                        "retrieved_at": now(),
                        "content_hash": content_hash,
                    }
                )
            )
        return result


class _PlainTextExtractor(HTMLParser):
    """Extract display text without retaining executable markup."""

    blocked_tags = frozenset({"script", "style", "noscript", "svg", "nav"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocked: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in self.blocked_tags:
            self.blocked.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.blocked_tags and tag in self.blocked:
            reverse_index = self.blocked[::-1].index(tag)
            self.blocked.pop(len(self.blocked) - reverse_index - 1)

    def handle_data(self, data: str) -> None:
        if not self.blocked and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self.parts).split())[:MAX_FULL_TEXT_CHARS]


def arxiv_html_url(external_id: str) -> str:
    """Map a validated arXiv abstract identity to its fixed HTML origin."""

    parsed = urlsplit(external_id)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.netloc not in {"arxiv.org", "export.arxiv.org"}
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/abs/")
    ):
        raise ValueError("ARXIV_IDENTITY_INVALID")
    identifier = parsed.path.removeprefix("/abs/")
    if (
        not identifier
        or len(identifier) > 100
        or ".." in identifier
        or not re.fullmatch(r"[A-Za-z0-9._/-]+", identifier)
    ):
        raise ValueError("ARXIV_IDENTITY_INVALID")
    return "https://arxiv.org/html/" + identifier


def bounded_html_text(client: httpx.Client, url: str) -> str:
    """Retrieve bounded HTML and return inert, whitespace-normalized text."""

    with client.stream("GET", url, headers={"Accept": "text/html"}) as response:
        response.raise_for_status()
        if (
            response.headers.get("content-type", "").partition(";")[0].strip().lower()
            != "text/html"
        ):
            raise ValueError("ARXIV_HTML_CONTENT_TYPE_REQUIRED")
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > MAX_UPSTREAM_BYTES:
                raise ValueError("UPSTREAM_RESPONSE_TOO_LARGE")
    parser = _PlainTextExtractor()
    parser.feed(bytes(data).decode("utf-8", errors="replace"))
    parser.close()
    text = parser.text()
    if len(text) < 200:
        raise ValueError("ARXIV_HTML_TEXT_INSUFFICIENT")
    return text


class Arxiv:
    capabilities = frozenset({"search", "metadata", "available-html-full-text"})

    def __init__(self, client: httpx.Client, *, include_full_text: bool = False):
        self.client = client
        self.include_full_text = include_full_text

    def search(self, query: str) -> list[Evidence]:
        from defusedxml import ElementTree  # type: ignore[import-untyped]

        with self.client.stream(
            "GET",
            "https://export.arxiv.org/api/query",
            params={"search_query": "all:" + query, "start": 0, "max_results": 8},
        ) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_UPSTREAM_BYTES:
                    raise ValueError("UPSTREAM_RESPONSE_TOO_LARGE")
        root = ElementTree.fromstring(
            bytes(data), forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
        namespace = {
            "a": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        result = []

        def field(entry: Any, name: str) -> str:
            return str(entry.findtext("a:" + name, default="", namespaces=namespace)).strip()

        for index, entry in enumerate(root.findall("a:entry", namespace)[:8]):
            external = field(entry, "id")
            try:
                full_text_url = arxiv_html_url(external)
            except ValueError:
                continue
            full_text = None
            full_text_source_url = None
            if self.include_full_text and index < MAX_ARXIV_FULL_TEXTS:
                try:
                    full_text_source_url = full_text_url
                    full_text = bounded_html_text(self.client, full_text_source_url)
                except (httpx.HTTPError, ValueError):
                    full_text = None
                    full_text_source_url = None
            payload: dict[str, Any] = {
                "provider": "arxiv",
                "external_id": external,
                "title": field(entry, "title")[:2000],
                "abstract": field(entry, "summary")[:16000],
                "url": external,
                "published": field(entry, "published"),
                "references": [],
                "content_level": "full_text" if full_text else "abstract",
                "full_text": full_text,
                "full_text_source_url": full_text_source_url,
                "license_url": str(
                    entry.findtext("arxiv:license", default="", namespaces=namespace) or ""
                )[:1000]
                or None,
            }
            content_hash = digest(payload)
            result.append(
                Evidence.model_validate(
                    {
                        **payload,
                        "id": "evidence-"
                        + digest(
                            {
                                "provider": payload["provider"],
                                "external_id": payload["external_id"],
                                "content_hash": content_hash,
                            }
                        ),
                        "retrieved_at": now(),
                        "content_hash": content_hash,
                    }
                )
            )
        return result


def search_sources(
    query: str,
    sources: list[str],
    full_text_policy: FullTextPolicy = "abstract-only",
) -> tuple[list[Evidence], dict[str, str]]:
    results: list[list[Evidence]] = []
    health = {}
    with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
        connectors = {
            "openalex": OpenAlex(client),
            "arxiv": Arxiv(client, include_full_text=full_text_policy == "available-arxiv-html"),
            "semantic_scholar": SemanticScholar(client),
        }
        for name in dict.fromkeys(sources):
            if name not in connectors:
                raise ValueError("UNKNOWN_RESEARCH_SOURCE")
            try:
                items = connectors[name].search(query)  # type: ignore[attr-defined]
                results.append(items)
                health[name] = "available" if items else "no_results"
            except Exception:
                health[name] = "unavailable"
    return [items[i] for i in range(8) for items in results if i < len(items)], health
