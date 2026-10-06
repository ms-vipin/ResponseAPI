from __future__ import annotations

import main
import pytest


@pytest.mark.asyncio
async def test_given_audience_when_get_workload_token_then_uses_default_scope(
    mocker,
) -> None:
    # Arrange
    credential = mocker.MagicMock()
    credential.__aenter__.return_value = credential
    credential.get_token = mocker.AsyncMock(
        return_value=mocker.Mock(token="access-token")
    )
    credential_type = mocker.patch.object(
        main,
        "AsyncDefaultAzureCredential",
        return_value=credential,
    )

    # Act
    result = await main.get_workload_token("api://workflow/")

    # Assert
    assert result == "access-token"
    credential_type.assert_called_once_with()
    credential.get_token.assert_awaited_once_with("api://workflow/.default")


@pytest.mark.asyncio
async def test_given_update_when_continue_workflow_then_calls_direct_mcp(
    monkeypatch: pytest.MonkeyPatch,
    mocker,
) -> None:
    # Arrange
    monkeypatch.setenv("WORKLOAD_MCP_ENDPOINT", "https://workflow.example/mcp")
    monkeypatch.setenv("WORKLOAD_MCP_AUDIENCE", "api://workflow")
    get_workload_token = mocker.patch.object(
        main,
        "get_workload_token",
        return_value="access-token",
    )
    call_mcp_tool = mocker.patch.object(
        main,
        "call_mcp_tool",
        return_value={"summary": "Started deployment; then approved release."},
    )

    # Act
    result = await main.continue_workflow.invoke(
        update="Approved release",
        previous_summary="Started deployment",
    )

    # Assert
    assert len(result) == 1
    assert result[0].text == "Started deployment; then approved release."
    get_workload_token.assert_awaited_once_with("api://workflow")
    call_mcp_tool.assert_awaited_once_with(
        "https://workflow.example/mcp",
        token="access-token",
        tool_name="continue_workflow",
        arguments={
            "update": "Approved release",
            "previous_summary": "Started deployment",
        },
    )