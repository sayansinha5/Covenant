from fastapi import APIRouter

from app.api.v1 import (
    admin,
    assistant,
    auth,
    contracts,
    health,
    mandate,
    operate,
    organizations,
    paypal,
    webhooks,
    workers,
    workspace,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(paypal.router)
api_router.include_router(paypal.return_router)
api_router.include_router(mandate.router)
api_router.include_router(contracts.router)
api_router.include_router(workspace.router)
api_router.include_router(operate.router)
api_router.include_router(assistant.router)
api_router.include_router(webhooks.router)
api_router.include_router(workers.router)
api_router.include_router(admin.router)
