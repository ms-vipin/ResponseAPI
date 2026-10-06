"""Environment-backed configuration for the local services."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration shared by the Responses API and MCP servers."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["local", "azure"] = "local"
    response_api_host: str = "127.0.0.1"
    response_api_port: int = 8000
    bearer_mcp_host: str = "127.0.0.1"
    bearer_mcp_port: int = 8001
    bearer_mcp_endpoint: str | None = None
    bearer_mcp_token: str = "local-bearer-token"
    workload_mcp_host: str = "127.0.0.1"
    workload_mcp_port: int = 8002
    workload_mcp_endpoint: str | None = None
    local_workload_identity_token: str = "local-workload-identity-token"
    workload_identity_auth_mode: Literal["local-token", "external"] = "local-token"

    @property
    def bearer_mcp_url(self) -> str:
        """Return the bearer MCP endpoint URL."""
        return self.bearer_mcp_endpoint or (
            f"http://{self.bearer_mcp_host}:{self.bearer_mcp_port}/mcp"
        )

    @property
    def workload_mcp_url(self) -> str:
        """Return the workload identity MCP endpoint URL."""
        return self.workload_mcp_endpoint or (
            f"http://{self.workload_mcp_host}:{self.workload_mcp_port}/mcp"
        )


@lru_cache
def get_settings() -> Settings:
    """Load and cache application settings."""
    return Settings()