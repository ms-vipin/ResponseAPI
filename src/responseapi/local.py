"""Run all localhost services in one process."""

from __future__ import annotations

import asyncio
import logging

import uvicorn

from responseapi.mcp_bearer import create_bearer_mcp_app
from responseapi.mcp_workload import create_workload_mcp_app
from responseapi.responses import create_responses_app
from responseapi.settings import get_settings

logger = logging.getLogger(__name__)


async def serve() -> None:
    """Serve the Responses API and both MCP endpoints until interrupted."""
    settings = get_settings()
    services = [
        (
            "Responses API",
            create_responses_app(settings),
            settings.response_api_host,
            settings.response_api_port,
        ),
        (
            "Bearer MCP",
            create_bearer_mcp_app(settings),
            settings.bearer_mcp_host,
            settings.bearer_mcp_port,
        ),
        (
            "Workload MCP",
            create_workload_mcp_app(settings),
            settings.workload_mcp_host,
            settings.workload_mcp_port,
        ),
    ]
    servers: list[uvicorn.Server] = []
    for name, app, host, port in services:
        logger.info("Starting %s at http://%s:%s", name, host, port)
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        servers.append(uvicorn.Server(config))

    await asyncio.gather(*(server.serve() for server in servers))


def main() -> None:
    """Run the localhost service group."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        logger.info("Local services stopped")