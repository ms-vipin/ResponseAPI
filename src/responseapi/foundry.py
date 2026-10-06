"""Provision the two MCP-backed prompt agents in Microsoft Foundry."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from pydantic_settings import BaseSettings, SettingsConfigDict


class FoundryConfig(BaseSettings):
    """Configuration required to create the Foundry agent versions."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    foundry_project_endpoint: str = ""
    foundry_model_deployment: str = "gpt-5-mini"
    bearer_mcp_endpoint: str = ""
    workload_mcp_endpoint: str = ""
    bearer_mcp_connection_name: str = "reference-mcp-connection"
    workload_mcp_connection_name: str = "workflow-mcp-connection"

    def require(self, *, include_project: bool) -> None:
        """Raise when required provisioning values are absent."""
        required = {
            "BEARER_MCP_ENDPOINT": self.bearer_mcp_endpoint,
            "WORKLOAD_MCP_ENDPOINT": self.workload_mcp_endpoint,
        }
        if include_project:
            required["FOUNDRY_PROJECT_ENDPOINT"] = self.foundry_project_endpoint
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required settings: {', '.join(missing)}")


def _reference_mcp_tool(config: FoundryConfig) -> MCPTool:
    """Build the reference MCP tool bound to the bearer connection."""
    return MCPTool(
        server_label="reference-mcp",
        server_url=config.bearer_mcp_endpoint,
        require_approval="never",
        project_connection_id=config.bearer_mcp_connection_name,
        allowed_tools=["lookup_reference"],
    )


def _workflow_mcp_tool(config: FoundryConfig) -> MCPTool:
    """Build the workflow MCP tool bound to the managed-identity connection."""
    return MCPTool(
        server_label="workflow-mcp",
        server_url=config.workload_mcp_endpoint,
        require_approval="never",
        project_connection_id=config.workload_mcp_connection_name,
        allowed_tools=["continue_workflow"],
    )


def build_agent_definitions(config: FoundryConfig) -> dict[str, PromptAgentDefinition]:
    """Build the one-to-one MCP tool definitions for both prompt agents."""
    return {
        "reference-agent": PromptAgentDefinition(
            model=config.foundry_model_deployment,
            instructions=(
                "Use lookup_reference for every request. Return only information "
                "grounded in that tool result. This agent is invoked with store=false."
            ),
            tools=[_reference_mcp_tool(config)],
        ),
        "workflow-agent": PromptAgentDefinition(
            model=config.foundry_model_deployment,
            instructions=(
                "Use continue_workflow for every request. Preserve relevant prior "
                "response context supplied by the Responses API chain."
            ),
            tools=[_workflow_mcp_tool(config)],
        ),
    }


def build_toolbox_agent_definitions(
    config: FoundryConfig,
) -> dict[str, PromptAgentDefinition]:
    """Build Phase 2 toolbox agents that reach MCP through project connections.

    These are additive, separately named agents used to validate the toolbox
    indirection path without touching the Phase 1 direct-call hosted agents.
    """
    return {
        "reference-toolbox-agent": PromptAgentDefinition(
            model=config.foundry_model_deployment,
            instructions=(
                "Use lookup_reference for every request. Return only information "
                "grounded in that tool result. This agent is invoked with store=false."
            ),
            tools=[_reference_mcp_tool(config)],
        ),
        "workflow-toolbox-agent": PromptAgentDefinition(
            model=config.foundry_model_deployment,
            instructions=(
                "Use continue_workflow for every request. Preserve relevant prior "
                "response context supplied by the Responses API chain."
            ),
            tools=[_workflow_mcp_tool(config)],
        ),
    }


def create_parser() -> argparse.ArgumentParser:
    """Create the provisioning command parser."""
    parser = argparse.ArgumentParser(
        description="Create two MCP-backed Foundry prompt agent versions."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print agent definitions without contacting Azure.",
    )
    parser.add_argument(
        "--toolbox",
        action="store_true",
        help="Provision only the Phase 2 toolbox agents, leaving existing agents untouched.",
    )
    return parser


def _serialize_definitions(
    definitions: dict[str, PromptAgentDefinition],
) -> dict[str, Any]:
    return {name: definition.as_dict() for name, definition in definitions.items()}


def main() -> int:
    """Validate configuration and create the Foundry agent versions."""
    args = create_parser().parse_args()
    config = FoundryConfig()
    try:
        config.require(include_project=not args.dry_run)
    except ValueError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    definitions = (
        build_toolbox_agent_definitions(config)
        if args.toolbox
        else build_agent_definitions(config)
    )
    if args.dry_run:
        print(json.dumps(_serialize_definitions(definitions), indent=2))
        return 0

    credential = DefaultAzureCredential()
    with AIProjectClient(
        endpoint=config.foundry_project_endpoint,
        credential=credential,
    ) as project:
        for agent_name, definition in definitions.items():
            agent = project.agents.create_version(
                agent_name=agent_name,
                definition=definition,
            )
            print(f"Created {agent.name} version {agent.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())