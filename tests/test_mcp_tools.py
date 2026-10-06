"""Protocol-level tests for both MCP services."""

from __future__ import annotations

import httpx2
import pytest

from responseapi.mcp_bearer import create_bearer_mcp_app
from responseapi.mcp_client import call_mcp_tool
from responseapi.mcp_workload import create_workload_mcp_app
from responseapi.settings import Settings


@pytest.mark.asyncio
async def test_given_query_when_bearer_tool_is_called_then_reference_is_returned() -> None:
    # Arrange
    settings = Settings(
        bearer_mcp_endpoint="https://reference.example/mcp",
        bearer_mcp_token="expected",
    )
    app = create_bearer_mcp_app(settings)
    transport = httpx2.ASGITransport(app=app)

    # Act
    async with app.router.lifespan_context(app):
        result = await call_mcp_tool(
            settings.bearer_mcp_url,
            token="expected",
            tool_name="lookup_reference",
            arguments={"query": "  MCP   registration  "},
            transport=transport,
        )

    # Assert
    assert result["answer"] == "Local reference result for: MCP registration"


@pytest.mark.asyncio
async def test_given_prior_summary_when_workflow_tool_is_called_then_context_is_continued() -> None:
    # Arrange
    settings = Settings(
        local_workload_identity_token="expected",
        workload_mcp_endpoint="https://workflow.example/mcp",
    )
    app = create_workload_mcp_app(settings)
    transport = httpx2.ASGITransport(app=app)

    # Act
    async with app.router.lifespan_context(app):
        result = await call_mcp_tool(
            settings.workload_mcp_url,
            token="expected",
            tool_name="continue_workflow",
            arguments={"update": "deploy", "previous_summary": "build"},
            transport=transport,
        )

    # Assert
    assert result["summary"] == "build | deploy"