"""Tests for the bearer-authenticated MCP endpoint."""

from __future__ import annotations

from starlette.testclient import TestClient

from responseapi.mcp_bearer import create_bearer_mcp_app
from responseapi.settings import Settings


def test_given_no_token_when_mcp_is_called_then_request_is_unauthorized() -> None:
    # Arrange
    app = create_bearer_mcp_app(Settings(bearer_mcp_token="expected"))

    # Act
    with TestClient(app) as client:
        response = client.post("/mcp")

    # Assert
    assert response.status_code == 401


def test_given_invalid_token_when_mcp_is_called_then_request_is_unauthorized() -> None:
    # Arrange
    app = create_bearer_mcp_app(Settings(bearer_mcp_token="expected"))

    # Act
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers={"Authorization": "Bearer invalid"},
        )

    # Assert
    assert response.status_code == 401