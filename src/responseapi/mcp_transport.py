"""Transport security configuration shared by the MCP servers."""

from __future__ import annotations

from urllib.parse import urlsplit

from mcp.server.transport_security import TransportSecuritySettings


def transport_security_for(endpoint: str) -> TransportSecuritySettings:
    """Allow only the host and origin declared by an MCP endpoint URL."""
    parsed_endpoint = urlsplit(endpoint)
    if not parsed_endpoint.scheme or not parsed_endpoint.netloc:
        raise ValueError(f"MCP endpoint must be an absolute URL: {endpoint!r}")

    origin = f"{parsed_endpoint.scheme}://{parsed_endpoint.netloc}"
    return TransportSecuritySettings(
        allowed_hosts=[parsed_endpoint.netloc],
        allowed_origins=[origin],
    )