from app.models import Contract
from app.schemas.common import AmountOut, ResponseModel


class ContractSummary(ResponseModel):
    id: str
    number: str
    state: str
    amount: AmountOut
    currency: str

    @classmethod
    def of(cls, contract: Contract) -> "ContractSummary":
        return cls(
            id=contract.id,
            number=f"C-{contract.number}",
            state=contract.state,
            amount=contract.amount,
            currency=contract.currency,
        )


class PolicyOut(ResponseModel):
    outcome: str
    code: str
    reason: str
    mandate_version: int | None


class AgreeOut(ResponseModel):
    contract: ContractSummary
    policy: PolicyOut


class CancelOut(ResponseModel):
    contract: ContractSummary
