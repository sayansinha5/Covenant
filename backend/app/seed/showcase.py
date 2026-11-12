"""A spread of contracts for screenshots.

Riya, Ada, Kabir's workers and Arjun end up with finished work, held money,
work still being checked, and jobs that never started. Nothing here calls
PayPal, and no outbox job is queued, so the rows stay where they are planted.

    python -m app.seed.showcase
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.spec_writer.spec import AcceptanceSpec, fingerprint
from app.core.config import Settings
from app.core.ids import uuid7
from app.db.base import utcnow
from app.models import (
    Appeal,
    Approval,
    Contract,
    ContractEvent,
    Delivery,
    Escrow,
    LedgerEntry,
    Mandate,
    Organization,
    Payout,
    Verdict,
    Worker,
)
from app.seed.run import run

FEE_RATE = Decimal("0.05")
SCHEMA = {
    "type": "object",
    "required": ["description"],
    "properties": {"description": {"type": "string"}},
}


def money(value: str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def fee_of(captured: Decimal) -> Decimal:
    return (captured * FEE_RATE).quantize(Decimal("0.01"))


def spec_for(*, title: str, work_type: str, description: str, count: int, price: str) -> dict:
    body = {
        "title": title,
        "work_type": work_type,
        "deliverable_description": description,
        "expected_item_count": count,
        "hard_checks": [
            {
                "id": "count",
                "type": "item_count_equals",
                "params": {"count": count},
                "applies_to": "whole",
            },
            {
                "id": "shape",
                "type": "json_schema_valid",
                "params": {"json_schema": SCHEMA},
                "applies_to": "each_item",
            },
        ],
        "rubric": [
            {
                "id": "accuracy",
                "name": "Accuracy",
                "weight": 0.5,
                "description": "The work matches what was asked.",
            },
            {
                "id": "tone",
                "name": "Tone",
                "weight": 0.3,
                "description": "It sounds like the brand.",
            },
            {
                "id": "finish",
                "name": "Finish",
                "weight": 0.2,
                "description": "It is ready to publish.",
            },
        ],
        "item_pass_score": 7,
        "bands": {"pass_min": 0.9, "partial_min": 0.5},
        "deadline_minutes": 4320,
        "price": price,
        "currency": "USD",
    }
    AcceptanceSpec.model_validate(body)
    return body


async def one(session: AsyncSession, model: type, **where: object):
    return await session.scalar(select(model).filter_by(**where))


async def seed(session: AsyncSession, _settings: Settings) -> str:
    riya = await one(session, Organization, name="Kantha & Co.")
    ada = await one(session, Organization, name="Northwind Test")
    kabir = await one(session, Organization, name="Kabir Studio")
    arjun_org = await one(session, Organization, name="Arjun Nair Design")
    missing = [
        name
        for name, org in (
            ("Kantha & Co.", riya),
            ("Northwind Test", ada),
            ("Kabir Studio", kabir),
            ("Arjun Nair Design", arjun_org),
        )
        if org is None
    ]
    if missing:
        return "Seed the accounts first. Missing: " + ", ".join(missing)

    workers = {}
    for name in ("Lipi", "Tally", "QuickWordz", "Arjun"):
        worker = await session.scalar(
            select(Worker).where(Worker.display_name == name).order_by(Worker.created_at)
        )
        if worker is None:
            return f"Seed the workers first. Missing: {name}."
        workers[name] = worker

    now = utcnow()
    waiting = riya_approvals(riya, kabir, arjun_org, workers, now)
    planted = await session.scalar(
        select(Contract.id).where(Contract.title == "German listings for the Berlin boutique")
    )
    if planted is not None:
        added = await plant_missing(session, waiting, now=now)
        if added == 0:
            return "Showcase contracts are already in place."
        return f"Added {added} approvals for Kantha & Co."
    stories = [
        story(
            hirer=riya,
            worker=workers["Lipi"],
            provider=kabir,
            title="German listings for the Berlin boutique",
            work_type="translation",
            request="Translate 40 stole listings into German.",
            description="Forty German listings. Names and prices stay as written.",
            amount="40.00",
            count=40,
            state="settled",
            when=now - timedelta(days=6),
            deadline=now - timedelta(days=4),
            hold="captured",
            captured="40.00",
            verdict=(
                "pass",
                "1.0000",
                "9.40",
                "All 40 listings passed. Names and prices were left alone.",
            ),
            payout="success",
        ),
        story(
            hirer=riya,
            worker=workers["Tally"],
            provider=kabir,
            title="Catalogue sizes for the indigo stoles",
            work_type="catalog_data",
            request="Fill dimensions for 120 product rows.",
            description="Dimensions for 120 catalogue rows, taken from the source sheet.",
            amount="30.00",
            count=120,
            state="partially_settled",
            when=now - timedelta(days=3),
            deadline=now - timedelta(days=1),
            hold="captured",
            captured="24.00",
            released="6.00",
            verdict=(
                "partial",
                "0.8000",
                "8.00",
                "96 of 120 rows passed. 24 invented a dimension.",
            ),
            payout="pending",
        ),
        story(
            hirer=riya,
            worker=workers["QuickWordz"],
            provider=kabir,
            title="Care notes for the spring drop",
            work_type="copywriting",
            request="Write short care notes for 12 stoles.",
            description="Twelve care notes a buyer can read on the product page.",
            amount="25.00",
            count=12,
            state="refunded",
            when=now - timedelta(days=8),
            deadline=now - timedelta(days=6),
            hold="voided",
            released="25.00",
            verdict=(
                "manipulation",
                "0.0000",
                "2.00",
                "The delivery hid a note asking for a perfect score. The hold was released.",
            ),
        ),
        story(
            hirer=riya,
            worker=workers["Arjun"],
            provider=arjun_org,
            title="Monogram for the spring stole",
            work_type="design",
            request="A monogram that can be stitched into the corner of a stole.",
            description="One monogram, drawn so it can be stitched small.",
            amount="55.00",
            count=1,
            state="in_progress",
            when=now - timedelta(days=1),
            deadline=now + timedelta(days=4),
            hold="held",
        ),
        story(
            hirer=riya,
            worker=workers["Lipi"],
            provider=kabir,
            title="French listings for the Lyon shop",
            work_type="translation",
            request="Translate 40 listings into French.",
            description="Forty French listings. Names and prices stay as written.",
            amount="40.00",
            count=40,
            state="verdict_issued",
            when=now - timedelta(hours=8),
            deadline=now + timedelta(days=1),
            hold="held",
            verdict=(
                "pass",
                "0.9750",
                "9.10",
                "39 of 40 listings passed. One title is still in English.",
            ),
        ),
        story(
            hirer=ada,
            worker=workers["Lipi"],
            provider=kabir,
            title="Spring titles for the Northwind shop",
            work_type="translation",
            request="Translate 24 spring titles into German.",
            description="Twenty-four German titles for the spring shop.",
            amount="48.00",
            count=24,
            state="awaiting_agreement",
            when=now - timedelta(hours=3),
            deadline=now + timedelta(days=6),
        ),
        story(
            hirer=ada,
            worker=workers["Arjun"],
            provider=arjun_org,
            title="Lookbook cover for April",
            work_type="design",
            request="A cover image for the April lookbook.",
            description="One cover, with room for the season name.",
            amount="90.00",
            count=1,
            state="awaiting_approval",
            when=now - timedelta(hours=5),
            deadline=now + timedelta(days=9),
            approval="This is $90, above the approval line. It waits for a person.",
        ),
        story(
            hirer=ada,
            worker=workers["Tally"],
            provider=kabir,
            title="Clean the outlet catalogue",
            work_type="catalog_data",
            request="Normalize 80 outlet rows.",
            description="Eighty catalogue rows with sizes and prices checked against the sheet.",
            amount="36.00",
            count=80,
            state="funded",
            when=now - timedelta(hours=18),
            deadline=now + timedelta(days=3),
            hold="held",
        ),
        story(
            hirer=ada,
            worker=workers["Arjun"],
            provider=arjun_org,
            title="Three marks for the tissue line",
            work_type="design",
            request="Three small marks for the tissue packaging.",
            description="Three marks, simple enough to print on tissue.",
            amount="42.00",
            count=3,
            state="verifying",
            when=now - timedelta(hours=12),
            deadline=now + timedelta(days=2),
            hold="held",
            delivered=True,
        ),
        story(
            hirer=ada,
            worker=workers["QuickWordz"],
            provider=kabir,
            title="Taglines that were withdrawn",
            work_type="copywriting",
            request="Eight taglines for a campaign that was cancelled.",
            description="Eight short taglines. The campaign was withdrawn before funding.",
            amount="22.00",
            count=8,
            state="cancelled",
            when=now - timedelta(days=11),
            deadline=now - timedelta(days=9),
        ),
        story(
            hirer=ada,
            worker=workers["Lipi"],
            provider=kabir,
            title="Dutch colour names",
            work_type="translation",
            request="Translate 16 colour names into Dutch.",
            description="Sixteen Dutch colour names for the filter menu.",
            amount="32.00",
            count=16,
            state="sent_to_worker",
            when=now - timedelta(hours=2),
            deadline=now + timedelta(days=5),
            hold="held",
        ),
        story(
            hirer=riya,
            worker=workers["Arjun"],
            provider=arjun_org,
            title="Border sketch for the lotus stole",
            work_type="design",
            request="A border sketch Arjun wants reviewed again.",
            description="One border sketch. The score landed near the line, so Arjun appealed.",
            amount="55.00",
            count=1,
            state="under_appeal",
            when=now - timedelta(days=2),
            deadline=now + timedelta(days=2),
            hold="held",
            verdict=(
                "partial",
                "0.5200",
                "6.40",
                "The sketch is close to the line. A person should look.",
            ),
            appeal="The border follows the brief. The score missed the stitch density.",
        ),
        *waiting,
    ]

    mandates = {}
    for org in (riya, ada):
        mandates[org.id] = await session.scalar(
            select(Mandate.id).where(Mandate.org_id == org.id, Mandate.is_active.is_(True))
        )

    for item in stories:
        await plant(session, item, mandate_id=mandates.get(item["hirer"].id), now=now)

    for worker, done in (("Lipi", 1), ("Tally", 1)):
        workers[worker].jobs_completed = (workers[worker].jobs_completed or 0) + done

    return f"Planted {len(stories)} contracts across Riya, Ada, Kabir and Arjun."


def riya_approvals(riya, kabir, arjun_org, workers: dict, now) -> list[dict]:
    """Contracts above Riya's approval line. They stay pending until she decides."""
    return [
        story(
            hirer=riya,
            worker=workers["Arjun"],
            provider=arjun_org,
            title="Pallu sketch for the wedding stole",
            work_type="design",
            request="A pallu sketch for a wedding stole, with room for the couple's initials.",
            description="One pallu sketch that can be stitched along the end of the stole.",
            amount="55.00",
            count=1,
            state="awaiting_approval",
            when=now - timedelta(hours=6),
            deadline=now + timedelta(days=5),
            approval=(
                "This contract is $55.00. Your mandate asks for approval above the line you set."
            ),
        ),
        story(
            hirer=riya,
            worker=workers["Lipi"],
            provider=kabir,
            title="Bengali listings for the Kolkata shop",
            work_type="translation",
            request="Translate 40 listings into Bengali. Leave the prices as written.",
            description="Forty Bengali listings. Names and prices stay as written.",
            amount="48.00",
            count=40,
            state="awaiting_approval",
            when=now - timedelta(hours=4),
            deadline=now + timedelta(days=4),
            approval=(
                "This contract is $48.00. Your mandate asks for approval above the line you set."
            ),
        ),
        story(
            hirer=riya,
            worker=workers["QuickWordz"],
            provider=kabir,
            title="Gift notes for the festive box",
            work_type="copywriting",
            request="Write a short gift note for each of 8 festive boxes.",
            description="Eight gift notes, one for each box in the festive set.",
            amount="42.00",
            count=8,
            state="awaiting_approval",
            when=now - timedelta(hours=2),
            deadline=now + timedelta(days=3),
            approval=(
                "This contract is $42.00. Your mandate asks for approval above the line you set."
            ),
        ),
    ]


async def plant_missing(session: AsyncSession, items: list[dict], *, now) -> int:
    added = 0
    mandates: dict = {}
    for item in items:
        exists = await session.scalar(select(Contract.id).where(Contract.title == item["title"]))
        if exists is not None:
            continue
        org = item["hirer"]
        if org.id not in mandates:
            mandates[org.id] = await session.scalar(
                select(Mandate.id).where(Mandate.org_id == org.id, Mandate.is_active.is_(True))
            )
        await plant(session, item, mandate_id=mandates[org.id], now=now)
        added += 1
    return added


def story(**fields: object) -> dict:
    return fields


async def plant(session: AsyncSession, item: dict, *, mandate_id: str | None, now) -> None:
    amount = money(item["amount"])
    body = spec_for(
        title=item["title"],
        work_type=item["work_type"],
        description=item["description"],
        count=item["count"],
        price=item["amount"],
    )
    contract = Contract(
        hirer_org_id=item["hirer"].id,
        provider_org_id=item["provider"].id,
        worker_id=item["worker"].id,
        mandate_id=mandate_id,
        work_type=item["work_type"],
        title=item["title"],
        request_text=item["request"],
        spec=body,
        spec_hash=fingerprint(body),
        amount=amount,
        currency="USD",
        state=item["state"],
        deadline_at=item["deadline"],
        created_by_actor="user",
        version=1,
        created_at=item["when"],
        updated_at=item["when"] + timedelta(hours=2),
    )
    session.add(contract)
    await session.flush()

    session.add(
        ContractEvent(
            contract_id=contract.id,
            event="noted",
            from_state=None,
            to_state=item["state"],
            actor_type="user",
            message=item["request"],
            created_at=item["when"],
        )
    )

    if item.get("approval"):
        session.add(
            Approval(
                contract_id=contract.id,
                org_id=item["hirer"].id,
                reason=f"{item['title']}. {item['approval']}",
                status="pending",
                expires_at=now + timedelta(days=2),
                created_at=item["when"],
            )
        )

    hold = item.get("hold")
    if hold:
        captured = money(item.get("captured", "0.00"))
        released = money(item.get("released", "0.00"))
        held_amount = amount
        session.add(
            Escrow(
                contract_id=contract.id,
                org_id=item["hirer"].id,
                status={"captured": "captured", "voided": "voided"}.get(hold, "held"),
                request_series=1,
                amount=amount,
                currency="USD",
                amount_held=held_amount,
                amount_captured=captured,
                amount_released=released,
                reserved_at=item["when"],
                honor_period_ends_at=now + timedelta(days=7),
                auth_expires_at=now + timedelta(days=21),
                created_at=item["when"],
                updated_at=item["when"],
            )
        )
        ledger(
            session,
            org_id=item["hirer"].id,
            contract_id=contract.id,
            direction="held",
            entry_type="escrow",
            amount=amount,
            when=item["when"],
        )
        if captured > 0:
            ledger(
                session,
                org_id=item["hirer"].id,
                contract_id=contract.id,
                direction="captured",
                entry_type="escrow",
                amount=captured,
                when=item["when"] + timedelta(hours=1),
            )
            charge = fee_of(captured)
            if charge > 0:
                ledger(
                    session,
                    org_id=item["hirer"].id,
                    contract_id=contract.id,
                    direction="fee",
                    entry_type="fee",
                    amount=charge,
                    when=item["when"] + timedelta(hours=1),
                )
        if released > 0:
            ledger(
                session,
                org_id=item["hirer"].id,
                contract_id=contract.id,
                direction="released",
                entry_type="escrow",
                amount=released,
                when=item["when"] + timedelta(hours=1),
            )

    verdict_id = None
    if item.get("delivered") or item.get("verdict"):
        delivery = Delivery(
            contract_id=contract.id,
            content={"note": item["description"]},
            received_at=item["when"] + timedelta(minutes=40),
            is_late=False,
        )
        session.add(delivery)
        await session.flush()
        if item.get("verdict"):
            result, ratio, score, reasoning = item["verdict"]
            verdict = Verdict(
                contract_id=contract.id,
                delivery_id=delivery.id,
                result=result,
                pass_ratio=Decimal(ratio),
                overall_score=Decimal(score),
                item_results=[],
                reasoning=reasoning,
                judge_model="showcase",
                prompt_version="showcase",
                created_at=item["when"] + timedelta(hours=1),
            )
            session.add(verdict)
            await session.flush()
            verdict_id = verdict.id
            session.add(
                ContractEvent(
                    contract_id=contract.id,
                    event="verdict_ready",
                    from_state="verifying",
                    to_state=item["state"],
                    actor_type="system",
                    message=reasoning,
                    created_at=item["when"] + timedelta(hours=1),
                )
            )

    if item.get("appeal") and verdict_id:
        session.add(
            Appeal(
                contract_id=contract.id,
                verdict_id=verdict_id,
                argument=item["appeal"],
                status="open",
                created_at=item["when"] + timedelta(hours=3),
            )
        )

    payout_status = item.get("payout")
    if payout_status and item.get("captured"):
        captured = money(item["captured"])
        charge = fee_of(captured)
        session.add(
            Payout(
                contract_id=contract.id,
                provider_org_id=item["provider"].id,
                receiver_email=item["provider"].payout_email,
                gross=captured,
                fee=charge,
                net=captured - charge,
                currency="USD",
                sender_batch_id=f"show{uuid7().replace('-', '')[:24]}",
                status=payout_status,
                created_at=item["when"] + timedelta(hours=2),
                updated_at=item["when"] + timedelta(hours=2),
            )
        )
        if payout_status == "success":
            ledger(
                session,
                org_id=item["provider"].id,
                contract_id=contract.id,
                direction="paid_out",
                entry_type="payout",
                amount=captured - charge,
                when=item["when"] + timedelta(hours=2),
            )


def ledger(
    session: AsyncSession,
    *,
    org_id: str,
    contract_id: str,
    direction: str,
    entry_type: str,
    amount: Decimal,
    when,
) -> None:
    session.add(
        LedgerEntry(
            org_id=org_id,
            contract_id=contract_id,
            entry_type=entry_type,
            direction=direction,
            amount=amount,
            currency="USD",
            actor_type="system",
            created_at=when,
        )
    )


if __name__ == "__main__":
    run(seed)
