"""Stateful workflow MCP server for workload identity callers."""

from __future__ import annotations

from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer

from responseapi.auth import StaticBearerTokenVerifier
from responseapi.external_identity import RequireExternalPrincipal
from responseapi.mcp_transport import transport_security_for
from responseapi.settings import Settings, get_settings


def create_workload_mcp_app(settings: Settings | None = None):
    """Create the local-token or externally authenticated workload MCP app."""
    current = settings or get_settings()
    auth = None
    verifier = None

    if current.workload_identity_auth_mode == "local-token":
        auth = AuthSettings(
            issuer_url=f"http://{current.response_api_host}:{current.response_api_port}/local-auth",
            resource_server_url=current.workload_mcp_url,
            required_scopes=["mcp:tools"],
            validate_token_resource=True,
        )
        verifier = StaticBearerTokenVerifier(
            current.local_workload_identity_token,
            client_id="local-workload-identity",
            resource=current.workload_mcp_url,
        )

    server = MCPServer(
        name="workflow-mcp",
        description="Continues a workflow using prior response context.",
        auth=auth,
        token_verifier=verifier,
    )

    @server.tool(structured_output=True)
    def continue_workflow(update: str, previous_summary: str = "") -> dict[str, str]:
        """Combine a workflow update with the prior stored response summary."""
        normalized_update = " ".join(update.split())
        normalized_previous = " ".join(previous_summary.split())
        summary = normalized_update
        if normalized_previous:
            summary = f"{normalized_previous} | {normalized_update}"
        return {
            "update": normalized_update,
            "previous_summary": normalized_previous,
            "summary": summary,
            "source": "workflow-mcp",
        }

    app = server.streamable_http_app(
        json_response=True,
        stateless_http=True,
        transport_security=transport_security_for(current.workload_mcp_url),
    )
    if current.workload_identity_auth_mode == "external":
        return RequireExternalPrincipal(app)
    return app


app = create_workload_mcp_app()