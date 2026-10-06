"""Foundry Hosted Agent for stateless reference requests."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _bearer_token(authorization: str) -> str:
    scheme, separator, token = authorization.strip().partition(" ")
    if separator and scheme.lower() == "bearer":
        return token
    return authorization.strip()


async def call_mcp_tool(
    endpoint: str,
    *,
    token: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Call one tool on a Streamable HTTP MCP server."""
    headers = {"Authorization": f"Bearer {_bearer_token(token)}"}
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
async def lookup_reference(query: str) -> str:
    """Look up authoritative reference information for the user's query."""
    result = await call_mcp_tool(
        os.environ["BEARER_MCP_ENDPOINT"],
        token=os.environ["BEARER_MCP_AUTHORIZATION"],
        tool_name="lookup_reference",
        arguments={"query": query},
    )
    return str(result["answer"])


async def main() -> None:
    """Expose the reference agent through the Foundry Responses protocol."""
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
            "Use lookup_reference for every request. Return only information "
            "grounded in the tool result and keep the answer concise."
        ),
        tools=[lookup_reference],
        default_options={"store": False},
    )
    await ResponsesHostServer(agent).run_async()


if __name__ == "__main__":
    asyncio.run(main())