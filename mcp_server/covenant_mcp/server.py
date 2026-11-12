"""MCP server (stdio). Reads COVENANT_API_URL and COVENANT_API_KEY and calls the REST API."""

import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from pydantic_settings import BaseSettings, SettingsConfigDict

from covenant_mcp.client import CovenantClient

mcp = MCPServer("covenant")


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    covenant_api_url: str = "http://127.0.0.1:8000/api/v1"
    covenant_api_key: str = ""


def _client() -> CovenantClient:
    settings = McpSettings()
    return CovenantClient(settings.covenant_api_url, settings.covenant_api_key)


@mcp.tool()
def find_workers(category: str, max_price: str = "", min_reputation: int = 0) -> str:
    """List verified workers in one category."""
    with _Session() as client:
        return _text(
            client.find_workers(
                category,
                max_price=max_price or None,
                min_reputation=min_reputation or None,
            )
        )


@mcp.tool()
def propose_contract(worker_id: str, request_text: str, budget: str = "") -> str:
    """Draft a contract for a worker id or display name. Does not hold money until fund_contract."""
    with _Session() as client:
        return _text(client.propose_contract(worker_id, request_text, budget or None))


@mcp.tool()
def get_contract(contract_id: str) -> str:
    """Read one contract, including its state and verdict."""
    with _Session() as client:
        return _text(client.get_contract(contract_id))


@mcp.tool()
def fund_contract(contract_id: str) -> str:
    """Agree and ask PayPal to hold the price. A person may still have to approve."""
    with _Session() as client:
        return _text(client.fund_contract(contract_id))


@mcp.tool()
def cancel_contract(contract_id: str) -> str:
    """Cancel before the worker accepts."""
    with _Session() as client:
        return _text(client.cancel_contract(contract_id))


@mcp.tool()
def get_mandate() -> str:
    """Read the organization's active mandate."""
    with _Session() as client:
        return _text(client.get_mandate())


class _Session:
    def __enter__(self) -> CovenantClient:
        self.client = _client()
        return self.client

    def __exit__(self, *exc: object) -> None:
        self.client.close()


def _text(payload: object) -> str:
    return json.dumps(payload)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
