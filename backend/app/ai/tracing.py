"""LangSmith tracing through an explicit tracer callback, so nothing depends on process-wide
environment variables and an unset key simply means no tracing."""

import uuid
from dataclasses import dataclass
from functools import cache

from langchain_core.runnables import RunnableConfig
from langchain_core.tracers.langchain import LangChainTracer, wait_for_all_tracers
from langsmith import Client

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class Traced:
    config: RunnableConfig
    run_id: str | None  # saved on the result when tracing is on; None otherwise


@cache
def _client(api_url: str, api_key: str) -> Client:
    return Client(api_url=api_url, api_key=api_key)


def run_config(
    settings: Settings,
    *,
    component: str,
    prompt_version: str,
    contract_id: str | None = None,
    org_id: str | None = None,
) -> Traced:
    """Config for one AI run, tagged with what the spec asks for (contract, org, component and
    prompt version). The run ID is fixed up front so it can be stored before the trace lands."""
    metadata = {
        "component": component,
        "prompt_version": prompt_version,
        "contract_id": contract_id,
        "org_id": org_id,
    }
    config = RunnableConfig(
        run_name=component,
        tags=[component, prompt_version],
        metadata={key: value for key, value in metadata.items() if value is not None},
    )
    if not settings.langsmith_enabled:
        return Traced(config=config, run_id=None)
    run_id = uuid.uuid4()
    client = _client(settings.langsmith_endpoint, settings.langsmith_api_key.get_secret_value())
    config["callbacks"] = [LangChainTracer(project_name=settings.langsmith_project, client=client)]
    config["run_id"] = run_id
    return Traced(config=config, run_id=str(run_id))


def flush() -> None:
    """Wait for pending traces; scripts call this before exiting."""
    wait_for_all_tracers()
