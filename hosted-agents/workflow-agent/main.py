"""Foundry Hosted Agent for stateful workflow requests."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger(__name__)


async def get_workload_token(audience: str) -> str:
    """Acquire an access token for the workflow MCP API."""
    scope = f"{audience.rstrip('/')}/.default"
    async with AsyncDefaultAzureCredential() as credential:
        access_token = await credential.get_token(scope)
    return access_token.token


async def call_mcp_tool(
    endpoint: str,
    *,
    token: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Call one tool on a Streamable HTTP MCP server."""
    headers = {"Authorization": f"Bearer {token}"}
    async with (
        httpx.AsyncClient(headers=headers) as http_client,
        streamable_http_client(endpoint, http_client=http_client) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        await session.initialize()
        result = await session.call_tool(tool_name, arguments)

    if result.isError:
        raise RuntimeError(f"MCP tool {tool_name!r} returned an error")
    if not isinstance(result.structuredContent, dict):
        raise TypeError(f"MCP tool {tool_name!r} did not return structured content")
    return result.structuredContent


@tool
async def continue_workflow(update: str, previous_summary: str = "") -> str:
    """Continue the workflow using the new update and optional prior summary."""
    try:
        token = await get_workload_token(os.environ["WORKLOAD_MCP_AUDIENCE"])
        result = await call_mcp_tool(
            os.environ["WORKLOAD_MCP_ENDPOINT"],
            token=token,
            tool_name="continue_workflow",
            arguments={"update": update, "previous_summary": previous_summary},
        )
        return str(result["summary"])
    except Exception:
        logger.exception("Workflow MCP call failed")
        raise


async def main() -> None:
    """Expose the workflow agent through the Foundry Responses protocol."""
    load_dotenv()
    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )
    agent = Agent(
        client=client,
        instructions=(
            "Use continue_workflow for every request. Incorporate relevant history "
            "provided by the Responses host through previous_response_id."
        ),
        tools=[continue_workflow],
    )
    await ResponsesHostServer(agent).run_async()


if __name__ == "__main__":
    asyncio.run(main())