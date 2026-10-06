"""Stateless MCP server protected by a configured bearer token."""

from __future__ import annotations

from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer

from responseapi.auth import StaticBearerTokenVerifier
from responseapi.mcp_transport import transport_security_for
from responseapi.settings import Settings, get_settings


def create_bearer_mcp_app(settings: Settings | None = None):
    """Create the bearer-authenticated Streamable HTTP MCP application."""
    current = settings or get_settings()
    server = MCPServer(
        name="reference-mcp",
        description="Provides a stateless reference lookup tool.",
        auth=AuthSettings(
            issuer_url=f"http://{current.response_api_host}:{current.response_api_port}/local-auth",
            resource_server_url=current.bearer_mcp_url,
            required_scopes=["mcp:tools"],
            validate_token_resource=True,
        ),
        token_verifier=StaticBearerTokenVerifier(
            current.bearer_mcp_token,
            client_id="local-responses-api",
            resource=current.bearer_mcp_url,
        ),
    )

    @server.tool(structured_output=True)
    def lookup_reference(query: str) -> dict[str, str]:
        """Return a deterministic local reference result for a query."""
        normalized_query = " ".join(query.split())
        return {
            "query": normalized_query,
            "answer": f"Local reference result for: {normalized_query}",
            "source": "reference-mcp",
        }

    return server.streamable_http_app(
        json_response=True,
        stateless_http=True,
        transport_security=transport_security_for(current.bearer_mcp_url),
    )


app = create_bearer_mcp_app()