from __future__ import annotations

import main
import pytest


@pytest.mark.parametrize(
    ("authorization", "expected"),
    [
        ("secret", "secret"),
        ("Bearer secret", "secret"),
        ("bearer secret", "secret"),
    ],
)
def test_given_authorization_when_normalized_then_returns_raw_token(
    authorization: str,
    expected: str,
) -> None:
    # Act
    result = main._bearer_token(authorization)

    # Assert
    assert result == expected


@pytest.mark.asyncio
async def test_given_query_when_lookup_reference_then_calls_direct_mcp(
    monkeypatch: pytest.MonkeyPatch,
    mocker,
) -> None:
    # Arrange
    monkeypatch.setenv("BEARER_MCP_ENDPOINT", "https://reference.example/mcp")
    monkeypatch.setenv("BEARER_MCP_AUTHORIZATION", "Bearer secret")
    call_mcp_tool = mocker.patch.object(
        main,
        "call_mcp_tool",
        return_value={"answer": "Local reference result for: networking"},
    )

    # Act
    result = await main.lookup_reference.invoke(query="networking")

    # Assert
    assert len(result) == 1
    assert result[0].text == "Local reference result for: networking"
    call_mcp_tool.assert_awaited_once_with(
        "https://reference.example/mcp",
        token="Bearer secret",
        tool_name="lookup_reference",
        arguments={"query": "networking"},
    )