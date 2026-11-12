"""A hirer can name Lipi, Tally, QuickWordz or Arjun. An id still wins when names collide."""

import json
from decimal import Decimal
from typing import cast

import pytest

from app.ai.buyer.agent import Turn, build_tools
from app.core.config import Settings
from app.db.engine import Database
from app.integrations.paypal import PayPalClient
from app.models import Organization, Worker
from app.services.hiring import WorkerAmbiguous, WorkerUnavailable, resolve_worker

pytestmark = pytest.mark.usefixtures("clean_tables")

AGENTS = (
    ("Lipi", "agent", "http://lipi:9101", ["translation"]),
    ("Tally", "agent", "http://tally:9102", ["catalog_data"]),
    ("QuickWordz", "agent", "http://quickwordz:9103", ["copywriting"]),
    ("Arjun", "human", None, ["design"]),
)


async def test_every_worker_resolves_by_name_or_id(
    database: Database, migrated_test_db: Settings
) -> None:
    async with database.session() as session:
        async with session.begin():
            hirer = Organization(name="Kantha", industry="retail", country="IN", can_hire=True)
            provider = Organization(name="Kabir Studio", industry="services", country="IN")
            session.add_all([hirer, provider])
            await session.flush()
            for name, kind, url, categories in AGENTS:
                session.add(_worker(provider.id, name, kind, url, categories))
            session.add(
                _worker(
                    provider.id,
                    "Pending",
                    "agent",
                    "http://pending:9104",
                    ["translation"],
                    "pending",
                )
            )
            hirer_id = hirer.id
            provider_id = provider.id

        for name in ("Lipi", "Tally", "QuickWordz", "Arjun"):
            found = await resolve_worker(session, org_id=hirer_id, ref=name.casefold())
            assert found.display_name == name
        tally_id = (await resolve_worker(session, org_id=hirer_id, ref="Tally")).id
        assert (await resolve_worker(session, org_id=hirer_id, ref=tally_id)).id == tally_id
        with pytest.raises(WorkerUnavailable):
            await resolve_worker(session, org_id=provider_id, ref="Arjun")
        with pytest.raises(WorkerUnavailable):
            await resolve_worker(session, org_id=hirer_id, ref="Pending")
        with pytest.raises(WorkerUnavailable):
            await resolve_worker(session, org_id=hirer_id, ref="  ")

        turn = Turn(
            session=session,
            settings=migrated_test_db,
            paypal=cast(PayPalClient, None),
            org_id=hirer_id,
            user_id="user",
            org_name="Kantha",
            assistant_name="Mira",
            actor_name="Riya",
        )
        get_worker = next(tool for tool in build_tools(turn) if tool.name == "get_worker")
        card = json.loads(await get_worker.ainvoke({"worker_id": "tally"}))
        assert (card["name"], card["id"]) == ("Tally", tally_id)
        missing = json.loads(await get_worker.ainvoke({"worker_id": "Nobody"}))
        assert missing == {"error": "That worker isn't available."}

        await session.commit()
        async with session.begin():
            other = Organization(name="Other Studio", industry="services", country="IN")
            session.add(other)
            await session.flush()
            session.add(
                _worker(other.id, "Tally", "agent", "http://tally-other:9102", ["catalog_data"])
            )
        with pytest.raises(WorkerAmbiguous):
            await resolve_worker(session, org_id=hirer_id, ref="Tally")
        still = json.loads(await get_worker.ainvoke({"worker_id": tally_id}))
        assert still["id"] == tally_id


def _worker(
    org_id: str,
    name: str,
    kind: str,
    url: str | None,
    categories: list[str],
    status: str = "verified",
) -> Worker:
    return Worker(
        org_id=org_id,
        kind=kind,
        display_name=name,
        base_url=url,
        categories=categories,
        price=Decimal("30.00"),
        currency="USD",
        status=status,
    )
