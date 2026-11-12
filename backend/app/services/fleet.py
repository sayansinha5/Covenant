"""The caller's workers beside the Astropods account that governs agents of the same name."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.astropods import AstropodsClient, AstropodsError
from app.integrations.astropods.match import names_match
from app.models import Worker

_NOT_CONFIGURED = (
    "Set ASTROPODS_API_TOKEN and ASTROPODS_ACCOUNT to see which workers are running "
    "as governed agents, and what the account has spent."
)


async def fleet_view(session: AsyncSession, settings: Settings, org_id: str) -> dict[str, Any]:
    own = list(
        await session.scalars(
            select(Worker).where(Worker.org_id == org_id).order_by(Worker.display_name)
        )
    )
    if not settings.astropods_configured:
        return _empty(own, configured=False, account=None, detail=_NOT_CONFIGURED)
    pool = await _match_pool(session, own)
    client = AstropodsClient(settings)
    try:
        deployments = await client.deployments()
    except AstropodsError as exc:
        return _empty(own, configured=True, account=settings.astropods_account, detail=exc.detail)
    try:
        blueprints = await client.blueprints()
    except AstropodsError:
        blueprints = []
    try:
        meters = await client.meters()
    except AstropodsError:
        meters = []
    linked = [_with_worker(deployment, pool) for deployment in deployments]
    return {
        "configured": True,
        "account": settings.astropods_account,
        "detail": None,
        "meters": meters,
        "deployments": linked,
        "blueprints": blueprints,
        "workers": [_worker_row(worker, linked, blueprints) for worker in own],
    }


async def _match_pool(session: AsyncSession, own: list[Worker]) -> list[Worker]:
    public = list(
        await session.scalars(select(Worker).where(Worker.status == "verified").limit(200))
    )
    by_id = {worker.id: worker for worker in [*own, *public]}
    return list(by_id.values())


def _empty(
    own: list[Worker], *, configured: bool, account: str | None, detail: str
) -> dict[str, Any]:
    return {
        "configured": configured,
        "account": account,
        "detail": detail,
        "meters": [],
        "deployments": [],
        "blueprints": [],
        "workers": [_worker_row(worker, [], []) for worker in own],
    }


def _with_worker(deployment: dict[str, Any], pool: list[Worker]) -> dict[str, Any]:
    match = _find(pool, deployment["name"], deployment["display_name"])
    return {
        **deployment,
        "matched_worker_id": match.id if match else None,
        "matched_worker_name": match.display_name if match else None,
    }


def _worker_row(
    worker: Worker, deployments: list[dict[str, Any]], blueprints: list[dict[str, Any]]
) -> dict[str, Any]:
    deployment = _find_deployment(deployments, worker.display_name)
    published = any(names_match(worker.display_name, blueprint["name"]) for blueprint in blueprints)
    if deployment is not None and deployment["status"] == "running":
        fleet_status = "running"
    elif deployment is not None or published:
        fleet_status = "published"
    else:
        fleet_status = "absent"
    return {
        "id": worker.id,
        "name": worker.display_name,
        "kind": worker.kind,
        "status": worker.status,
        "fleet_status": fleet_status,
        "deployment_id": deployment["id"] if deployment else None,
    }


def _find(workers: list[Worker], *names: str) -> Worker | None:
    for worker in workers:
        if any(names_match(worker.display_name, name) for name in names if name):
            return worker
    return None


def _find_deployment(deployments: list[dict[str, Any]], worker_name: str) -> dict[str, Any] | None:
    for deployment in deployments:
        if names_match(worker_name, deployment["name"]) or names_match(
            worker_name, deployment["display_name"]
        ):
            return deployment
    return None
