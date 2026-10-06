"""Tests for stateless and stateful Responses API behavior."""

from __future__ import annotations

from starlette.testclient import TestClient

from responseapi.responses import AgentRuntime, create_responses_app
from responseapi.settings import Settings


def test_given_reference_agent_when_response_created_then_it_is_not_stored(mocker) -> None:
    # Arrange
    tool_caller = mocker.AsyncMock(
        return_value={"answer": "reference result", "source": "reference-mcp"}
    )
    settings = Settings()
    runtime = AgentRuntime(settings, tool_caller=tool_caller)
    app = create_responses_app(settings, runtime=runtime)

    # Act
    with TestClient(app) as client:
        response = client.post(
            "/v1/responses",
            json={"model": "reference-agent", "input": "question", "store": False},
        )

    # Assert
    assert response.status_code == 200 and response.json()["store"] is False


def test_given_reference_agent_when_previous_id_supplied_then_request_is_rejected(mocker) -> None:
    # Arrange
    runtime = AgentRuntime(Settings(), tool_caller=mocker.AsyncMock())
    app = create_responses_app(runtime=runtime)

    # Act
    with TestClient(app) as client:
        response = client.post(
            "/v1/responses",
            json={
                "model": "reference-agent",
                "input": "question",
                "previous_response_id": "resp_prior",
            },
        )

    # Assert
    assert response.status_code == 400


def test_given_workflow_agent_when_previous_response_supplied_then_context_is_chained(mocker) -> None:
    # Arrange
    async def tool_caller(*args, **kwargs):
        arguments = kwargs["arguments"]
        previous = arguments["previous_summary"]
        update = arguments["update"]
        summary = f"{previous} | {update}" if previous else update
        return {"summary": summary, "source": "workflow-mcp"}

    settings = Settings()
    runtime = AgentRuntime(settings, tool_caller=tool_caller)
    app = create_responses_app(settings, runtime=runtime)

    # Act
    with TestClient(app) as client:
        first = client.post(
            "/v1/responses",
            json={"model": "workflow-agent", "input": "build"},
        ).json()
        second = client.post(
            "/v1/responses",
            json={
                "model": "workflow-agent",
                "input": "deploy",
                "previous_response_id": first["id"],
            },
        )

    # Assert
    assert second.json()["output_text"] == "build | deploy"


def test_given_unknown_previous_id_when_workflow_response_created_then_not_found_is_returned(
    mocker,
) -> None:
    # Arrange
    runtime = AgentRuntime(Settings(), tool_caller=mocker.AsyncMock())
    app = create_responses_app(runtime=runtime)

    # Act
    with TestClient(app) as client:
        response = client.post(
            "/v1/responses",
            json={
                "model": "workflow-agent",
                "input": "deploy",
                "previous_response_id": "resp_missing",
            },
        )

    # Assert
    assert response.status_code == 404