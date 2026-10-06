"""Authentication helpers for MCP resource servers."""

from __future__ import annotations

import hmac

from mcp.server.auth.provider import AccessToken


class StaticBearerTokenVerifier:
    """Verify a configured bearer token without exposing it in logs."""

    def __init__(
        self,
        expected_token: str,
        *,
        client_id: str,
        resource: str,
        scopes: list[str] | None = None,
    ) -> None:
        if not expected_token:
            raise ValueError("expected_token must not be empty")

        self._expected_token = expected_token
        self._client_id = client_id
        self._resource = resource
        self._scopes = scopes or ["mcp:tools"]

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return MCP access metadata when the supplied token is valid."""
        if not hmac.compare_digest(token, self._expected_token):
            return None

        return AccessToken(
            token=token,
            client_id=self._client_id,
            scopes=self._scopes,
            resource=self._resource,
            subject=self._client_id,
        )