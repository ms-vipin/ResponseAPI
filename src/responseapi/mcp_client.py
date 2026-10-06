"""Client helpers for calling Streamable HTTP MCP tools."""

from __future__ import annotations

from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def call_mcp_tool(
    endpoint: str,
    *,
    token: str,
    tool_name: str,
    arguments: dict[str, Any],
    transport: httpx2.AsyncBaseTransport | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Call one MCP tool and return its structured result."""
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra_headers or {})

    async with (
        httpx2.AsyncClient(headers=headers, transport=transport) as http_client,
        streamable_http_client(endpoint, http_client=http_client) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        result = await session.call_tool(tool_name, arguments)

    if result.is_error:
        raise RuntimeError(f"MCP tool {tool_name!r} returned an error")
    if not isinstance(result.structured_content, dict):
        raise TypeError(f"MCP tool {tool_name!r} did not return structured content")
    return result.structured_content