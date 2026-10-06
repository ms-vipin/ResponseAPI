"""Tests for Foundry prompt agent provisioning definitions."""

from __future__ import annotations

from responseapi.foundry import (
    FoundryConfig,
    build_agent_definitions,
    build_toolbox_agent_definitions,
)


def test_given_mcp_endpoints_when_definitions_built_then_each_agent_has_one_mcp() -> None:
    # Arrange
    config = FoundryConfig(
        bearer_mcp_endpoint="https://reference.example/mcp",
        workload_mcp_endpoint="https://workflow.example/mcp",
    )

    # Act
    definitions = build_agent_definitions(config)
    serialized = {name: definition.as_dict() for name, definition in definitions.items()}

    # Assert
    assert {
        name: definition["tools"][0]["project_connection_id"]
        for name, definition in serialized.items()
    } == {
        "reference-agent": "reference-mcp-connection",
        "workflow-agent": "workflow-mcp-connection",
    }


def test_given_agent_definitions_when_serialized_then_allowed_tools_are_restricted() -> None:
    # Arrange
    config = FoundryConfig(
        bearer_mcp_endpoint="https://reference.example/mcp",
        workload_mcp_endpoint="https://workflow.example/mcp",
    )

    # Act
    definitions = build_agent_definitions(config)
    reference_tool = definitions["reference-agent"].as_dict()["tools"][0]
    workflow_tool = definitions["workflow-agent"].as_dict()["tools"][0]

    # Assert
    assert (reference_tool["allowed_tools"], workflow_tool["allowed_tools"]) == (
        ["lookup_reference"],
        ["continue_workflow"],
    )


def test_given_toolbox_flag_when_definitions_built_then_new_agents_use_same_connections() -> None:
    # Arrange
    config = FoundryConfig(
        bearer_mcp_endpoint="https://reference.example/mcp",
        workload_mcp_endpoint="https://workflow.example/mcp",
    )

    # Act
    definitions = build_toolbox_agent_definitions(config)
    serialized = {name: definition.as_dict() for name, definition in definitions.items()}

    # Assert
    assert {
        name: definition["tools"][0]["project_connection_id"]
        for name, definition in serialized.items()
    } == {
        "reference-toolbox-agent": "reference-mcp-connection",
        "workflow-toolbox-agent": "workflow-mcp-connection",
    }