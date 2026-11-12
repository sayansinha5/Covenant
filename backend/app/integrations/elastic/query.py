"""Pure helpers for the Elasticsearch URL and the search request. No network."""

import base64
from typing import Any


def elasticsearch_endpoint(url: str, cloud_id: str) -> str:
    """Prefer an Elastic Cloud id when one is set. Otherwise use the plain URL.

    A cloud id looks like ``name:base64(host$esId$kibanaId)``. The Elasticsearch
    host is ``https://{esId}.{host}``.
    """

    cloud_id = cloud_id.strip()
    if not cloud_id:
        return url.strip().rstrip("/")
    label, separator, encoded = cloud_id.partition(":")
    if not separator or not label or not encoded:
        raise ValueError("ELASTIC_CLOUD_ID must look like a name, a colon, and an encoded host")
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        decoded = base64.b64decode(padded, validate=True).decode("ascii")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("ELASTIC_CLOUD_ID could not be read") from exc
    parts = decoded.split("$")
    if len(parts) < 2 or not parts[0] or not parts[1] or "/" in parts[0] or "/" in parts[1]:
        raise ValueError("ELASTIC_CLOUD_ID could not be read")
    host, es_id = parts[0], parts[1]
    return f"https://{es_id}.{host}"


def search_request(query: str, document_ids: list[str]) -> dict[str, Any]:
    """Match every word, and only inside the documents just loaded for this caller."""

    return {
        "size": 12,
        "track_total_hits": False,
        "query": {
            "bool": {
                "must": {
                    "multi_match": {
                        "query": query,
                        "fields": ["title^3", "body", "subtitle"],
                        "operator": "and",
                    }
                },
                "filter": {"ids": {"values": document_ids}},
            }
        },
    }


def filter_documents(
    documents: list[dict[str, Any]], query: str, *, limit: int = 12
) -> list[dict[str, Any]]:
    """The same 'every word' rule as Elasticsearch, used when the cluster is down."""

    terms = [part for part in query.casefold().split() if part]
    if not terms:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for document in documents:
        haystack = f"{document['title']} {document['subtitle']} {document['body']}".casefold()
        if not all(term in haystack for term in terms):
            continue
        title = str(document["title"]).casefold()
        score = sum(title.count(term) * 3 + haystack.count(term) for term in terms)
        scored.append((score, document))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [_hit(document) for _, document in scored[:limit]]


def clean_query(value: str, *, limit: int = 120) -> str:
    return " ".join(value.split())[:limit]


def _hit(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": document["ref_id"],
        "kind": document["kind"],
        "title": document["title"],
        "subtitle": document["subtitle"],
        "href": document["href"],
        "state": document["state"],
    }
