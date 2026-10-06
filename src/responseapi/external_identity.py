"""ASGI guard for identities authenticated by the Azure hosting platform."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class RequireExternalPrincipal:
    """Require the principal header injected by Azure Container Apps authentication."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject HTTP requests that lack an externally verified principal."""
        if scope["type"] == "http":
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            if b"x-ms-client-principal-id" not in headers:
                response = JSONResponse(
                    {"error": "An authenticated workload identity is required."},
                    status_code=401,
                )
                await response(scope, receive, send)
                return

        await self._app(scope, receive, send)