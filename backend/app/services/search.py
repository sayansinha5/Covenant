"""Documents the caller is allowed to find, then ranked by Elasticsearch when it is up."""

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.integrations.elastic.client import ElasticClient, ElasticError
from app.integrations.elastic.query import clean_query, filter_documents
from app.models import Contract, Organization, Worker

logger = get_logger("covenant.search")
_BODY_LIMIT = 1000


async def search_work(
    session: AsyncSession, settings: Settings, org: Organization, query: str
) -> dict[str, Any]:
    cleaned = clean_query(query)
    documents = await _documents(session, org)
    if len(cleaned) < 2:
        return {"engine": "database", "query": cleaned, "items": []}
    if settings.elastic_configured:
        try:
            items = await ElasticClient(settings).search_documents(documents, cleaned)
        except ElasticError as exc:
            logger.warning("elastic_search_failed", error=str(exc))
        else:
            return {"engine": "elasticsearch", "query": cleaned, "items": items}
    return {
        "engine": "database",
        "query": cleaned,
        "items": filter_documents(documents, cleaned),
    }


async def _documents(session: AsyncSession, org: Organization) -> list[dict[str, Any]]:
    contracts = (
        await session.execute(
            select(Contract, Worker.display_name)
            .join(Worker, Worker.id == Contract.worker_id)
            .where(or_(Contract.hirer_org_id == org.id, Contract.provider_org_id == org.id))
            .order_by(Contract.updated_at.desc())
            .limit(200)
        )
    ).all()
    workers = list(
        await session.scalars(
            select(Worker)
            .where(or_(Worker.org_id == org.id, Worker.status == "verified"))
            .order_by(Worker.display_name)
            .limit(200)
        )
    )
    documents = [_contract_document(contract, worker_name) for contract, worker_name in contracts]
    seen: set[str] = set()
    for worker in workers:
        if worker.id in seen:
            continue
        seen.add(worker.id)
        documents.append(_worker_document(worker, owner=worker.org_id == org.id))
    return documents


def _contract_document(contract: Contract, worker_name: str) -> dict[str, Any]:
    number = f"C-{contract.number}"
    state = contract.state.replace("_", " ")
    return {
        "doc_id": f"contract:{contract.id}",
        "ref_id": contract.id,
        "kind": "contract",
        "title": f"{number} {contract.title}",
        "subtitle": f"{worker_name} · {state}",
        "body": contract.request_text[:_BODY_LIMIT],
        "href": f"/contracts/{contract.id}",
        "state": contract.state,
    }


def _worker_document(worker: Worker, *, owner: bool) -> dict[str, Any]:
    categories = " ".join(worker.categories or [])
    description = (worker.description or "")[:_BODY_LIMIT]
    return {
        "doc_id": f"worker:{worker.id}",
        "ref_id": worker.id,
        "kind": "worker",
        "title": worker.display_name,
        "subtitle": f"{worker.kind} · {worker.status.replace('_', ' ')}",
        "body": f"{description} {categories}".strip(),
        "href": "/workers" if owner else f"/find-workers?worker={worker.id}",
        "state": worker.status,
    }
