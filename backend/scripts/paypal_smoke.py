"""Manual PayPal sandbox smoke test (build step 2).

Runs the real money flow against the sandbox and prints every PayPal ID:
  1. hold $40 (authorize) -> capture $24 as final capture -> PayPal releases the other $16
  2. hold $25 -> void
  3. pay out $5 to a sandbox email (optional)
Each mutating call is then replayed with the same PayPal-Request-Id to show it is not duplicated.

    python scripts/paypal_smoke.py --payout-email <sandbox email>
    python scripts/paypal_smoke.py --vault-id <payment token id>

Without --vault-id each order is approved by hand: the script prints a PayPal link, you open it,
log in as a sandbox *personal* account, approve, and press Enter. After approving, PayPal sends the
browser to the API health page; that is expected.
"""

import argparse
import asyncio
import sys
from decimal import Decimal

from app.core.config import ConfigurationError, load_settings
from app.core.ids import uuid7
from app.core.money import format_amount
from app.db.engine import Database
from app.integrations.paypal import PayPalApiError, PayPalClient, PayPalConfig, PayPalError
from app.integrations.paypal.audit import Operation, OperationKind
from app.integrations.paypal.types import Authorization, Order
from app.services.paypal_audit import SqlOperationRecorder

HOLD_AMOUNT = Decimal("40.00")
PARTIAL_CAPTURE = Decimal("24.00")
VOID_HOLD_AMOUNT = Decimal("25.00")
PAYOUT_POLL_SECONDS = 5
PAYOUT_POLL_ATTEMPTS = 12


class Smoke:
    def __init__(self, client: PayPalClient, run_id: str, vault_id: str | None) -> None:
        self.client = client
        self.run_id = run_id
        self.vault_id = vault_id
        self.summary: list[tuple[str, str]] = []

    def op(self, label: str, kind: OperationKind) -> Operation:
        return Operation(kind=kind, request_id=f"cov-smoke-{self.run_id}-{label}-{kind}-1")

    def note(self, label: str, value: str) -> None:
        self.summary.append((label, value))
        print(f"  {label:<34} {value}")

    @staticmethod
    def check_replay(what: str, first: str, second: str) -> None:
        if first != second:
            raise SystemExit(f"  FAIL: replaying {what} returned {second}, expected {first}")
        print(f"  replay {what:<27} same ID returned, nothing duplicated")

    async def hold(self, label: str, amount: Decimal) -> Authorization:
        return_url = f"{self.client.config.return_base_url}/api/v1/health"
        create_op = self.op(label, "create_order")

        async def create() -> Order:
            return await self.client.create_authorize_order(
                operation=create_op,
                amount=amount,
                reference_id=f"smoke-{label}",
                custom_id=f"smoke-{self.run_id}-{label}",
                invoice_id=f"SMOKE-{self.run_id}-{label}",
                description=f"Covenant smoke test {label}: escrow hold",
                vault_id=self.vault_id,
                return_url=return_url,
                cancel_url=return_url,
            )

        order = await create()
        self.note(f"[{label}] order", f"{order.id} ({order.status})")
        self.check_replay("create order", order.id, (await create()).id)

        if order.authorization is None:
            if order.payer_action_url:
                print(f"\n  Approve the ${format_amount(amount)} hold as a sandbox buyer:")
                print(f"  {order.payer_action_url}\n")
                await asyncio.to_thread(input, "  Press Enter once you have approved it... ")
            authorize_op = self.op(label, "authorize")
            order = await self.client.authorize_order(order.id, operation=authorize_op)
            replay = await self.client.authorize_order(order.id, operation=authorize_op)
            if order.authorization is None or replay.authorization is None:
                raise SystemExit(f"  FAIL: order {order.id} has no authorization ({order.status})")
            self.check_replay("authorize", order.authorization.id, replay.authorization.id)

        if order.authorization is None:
            raise SystemExit(f"  FAIL: order {order.id} has no authorization ({order.status})")
        auth = order.authorization
        self.note(f"[{label}] authorization", f"{auth.id} {auth.status} ${auth.amount}")
        return auth

    async def capture_partial(self) -> None:
        print(f"\n1. Hold ${HOLD_AMOUNT}, capture ${PARTIAL_CAPTURE} as final capture")
        auth = await self.hold("A", HOLD_AMOUNT)
        capture_op = self.op("A", "capture")

        async def capture() -> str:
            result = await self.client.capture_authorization(
                auth.id,
                operation=capture_op,
                amount=PARTIAL_CAPTURE,
                invoice_id=f"SMOKE-{self.run_id}-A",
                note_to_payer="Covenant smoke test: partial capture",
            )
            self.note("[A] capture", f"{result.id} {result.status} ${result.amount}")
            return result.id

        first = await capture()
        self.check_replay("capture", first, await capture())
        after = await self.client.get_authorization(auth.id)
        self.note("[A] authorization after capture", after.status)
        self.note("[A] released to buyer", f"${format_amount(HOLD_AMOUNT - PARTIAL_CAPTURE)}")

    async def hold_and_void(self) -> None:
        print(f"\n2. Hold ${VOID_HOLD_AMOUNT}, then void")
        auth = await self.hold("B", VOID_HOLD_AMOUNT)
        void_op = self.op("B", "void")
        voided = await self.client.void_authorization(auth.id, operation=void_op)
        self.note("[B] void", voided.status)
        replay = await self.client.void_authorization(auth.id, operation=void_op)
        self.check_replay("void", voided.status, replay.status)

    async def payout(self, email: str, amount: Decimal) -> None:
        print(f"\n3. Pay out ${format_amount(amount)} to {email}")
        payout_id = f"smoke-{self.run_id}"

        async def send() -> str:
            batch = await self.client.create_payout(
                payout_id=payout_id,
                contract_id=None,
                receiver_email=email,
                amount=amount,
                sender_item_id=f"SMOKE-{self.run_id}",
                note="Covenant smoke test payout",
                email_subject="Covenant sandbox payout",
            )
            self.note("payout batch", f"{batch.batch_id} ({batch.batch_status})")
            return batch.batch_id

        batch_id = await send()
        self.check_replay("payout", batch_id, await send())
        for _ in range(PAYOUT_POLL_ATTEMPTS):
            batch = await self.client.get_payout_batch(batch_id)
            if batch.batch_status in {"SUCCESS", "DENIED", "CANCELED"}:
                break
            await asyncio.sleep(PAYOUT_POLL_SECONDS)
        self.note("payout batch final status", batch.batch_status)
        for item in batch.items:
            detail = f"{item.item_id} {item.transaction_status}"
            self.note("payout item", detail + (f" ({item.error})" if item.error else ""))


async def run(args: argparse.Namespace) -> int:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(exc, file=sys.stderr)
        return 2
    config = PayPalConfig.from_settings(settings)
    if not config.configured:
        print(
            "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in backend/.env first.", file=sys.stderr
        )
        return 2

    database = Database.from_settings(settings)
    client = PayPalClient(config, recorder=SqlOperationRecorder(database))
    smoke = Smoke(client, run_id=uuid7()[-12:], vault_id=args.vault_id)
    print(f"PayPal sandbox smoke test, run {smoke.run_id} against {config.base_url}")
    print("Funding: " + ("vaulted payment token" if args.vault_id else "approve each order"))
    try:
        await smoke.capture_partial()
        await smoke.hold_and_void()
        if args.payout_email and config.payouts_enabled:
            await smoke.payout(args.payout_email, Decimal(args.payout_amount))
        else:
            print("\n3. Payout skipped (pass --payout-email, and PAYPAL_PAYOUTS_ENABLED=true)")
    except PayPalApiError as exc:
        print(f"\nFAILED: {exc}\n  PayPal-Debug-Id: {exc.debug_id}", file=sys.stderr)
        return 1
    except PayPalError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.aclose()
        await database.dispose()

    print("\nAll steps passed. Look these IDs up in the sandbox dashboard:")
    for label, value in smoke.summary:
        print(f"  {label:<34} {value}")
    print("Audit rows: SELECT kind, request_id, response_status, attempts FROM paypal_operations;")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--vault-id", help="Vaulted PayPal payment token ID (skips approvals)")
    parser.add_argument("--payout-email", help="Sandbox personal account email to pay out to")
    parser.add_argument("--payout-amount", default="5.00", help="Payout amount in USD")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
