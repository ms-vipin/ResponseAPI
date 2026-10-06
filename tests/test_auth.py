"""Tests for MCP authentication helpers."""

from __future__ import annotations

import pytest

from responseapi.auth import StaticBearerTokenVerifier


@pytest.mark.asyncio
async def test_given_invalid_token_when_verified_then_access_is_denied() -> None:
    # Arrange
    verifier = StaticBearerTokenVerifier(
        "expected",
        client_id="test-client",
        resource="http://localhost/mcp",
    )

    # Act
    result = await verifier.verify_token("invalid")

    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_given_valid_token_when_verified_then_access_metadata_is_returned() -> None:
    # Arrange
    verifier = StaticBearerTokenVerifier(
        "expected",
        client_id="test-client",
        resource="http://localhost/mcp",
    )

    # Act
    result = await verifier.verify_token("expected")

    # Assert
    assert result is not None and result.client_id == "test-client"