"""Responses-compatible API backed by the two local MCP services."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from responseapi.mcp_client import call_mcp_tool
from responseapi.settings import Settings, get_settings

AgentName = Literal["reference-agent", "workflow-agent"]
ToolCaller = Callable[..., Awaitable[dict[str, Any]]]


class ResponseRequest(BaseModel):
    """Supported subset of the Responses API create request."""

    model_config = ConfigDict(extra="forbid")

    model: AgentName
    input: str = Field(min_length=1)
    previous_response_id: str | None = None
    store: bool | None = None
    stream: bool = False
    metadata: dict[str, str] | None = None


class ApiError(Exception):
    """Represent a client-facing Responses API error."""

    def __init__(self, message: str, *, status_code: int, code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class InMemoryResponseStore:
    """Store response records for local stateful chaining."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def get(self, response_id: str) -> dict[str, Any] | None:
        """Return a stored response record by ID."""
        return self._records.get(response_id)

    def put(self, response: dict[str, Any]) -> None:
        """Store a response record by its ID."""
        self._records[response["id"]] = response


class AgentRuntime:
    """Route Responses API requests to the configured MCP-backed agent."""

    def __init__(
        self,
        settings: Settings,
        *,
        store: InMemoryResponseStore | None = None,
        tool_caller: ToolCaller = call_mcp_tool,
    ) -> None:
        self._settings = settings
        self._store = store or InMemoryResponseStore()
        self._tool_caller = tool_caller

    async def create(self, request: ResponseRequest) -> dict[str, Any]:
        """Create a stateless or stateful agent response."""
        if request.stream:
            raise ApiError(
                "Streaming is not implemented by the local harness.",
                status_code=400,
                code="unsupported_parameter",
            )
        if request.model == "reference-agent":
            return await self._create_stateless(request)
        return await self._create_stateful(request)

    async def _create_stateless(self, request: ResponseRequest) -> dict[str, Any]:
        if request.previous_response_id is not None:
            raise ApiError(
                "reference-agent does not accept previous_response_id.",
                status_code=400,
                code="stateless_agent",
            )
        if request.store is True:
            raise ApiError(
                "reference-agent requires store=false.",
                status_code=400,
                code="stateless_agent",
            )

        result = await self._tool_caller(
            self._settings.bearer_mcp_url,
            token=self._settings.bearer_mcp_token,
            tool_name="lookup_reference",
            arguments={"query": request.input},
        )
        return self._build_response(
            request,
            text=str(result["answer"]),
            store=False,
            mcp_server="reference-mcp",
        )

    async def _create_stateful(self, request: ResponseRequest) -> dict[str, Any]:
        if request.store is False:
            raise ApiError(
                "workflow-agent requires store=true.",
                status_code=400,
                code="stateful_agent",
            )

        previous_summary = ""
        if request.previous_response_id is not None:
            previous = self._store.get(request.previous_response_id)
            if previous is None:
                raise ApiError(
                    "previous_response_id was not found.",
                    status_code=404,
                    code="response_not_found",
                )
            if previous["model"] != "workflow-agent":
                raise ApiError(
                    "previous_response_id belongs to a different agent.",
                    status_code=400,
                    code="agent_mismatch",
                )
            previous_summary = str(previous["output_text"])

        result = await self._tool_caller(
            self._settings.workload_mcp_url,
            token=self._settings.local_workload_identity_token,
            tool_name="continue_workflow",
            arguments={
                "update": request.input,
                "previous_summary": previous_summary,
            },
        )
        response = self._build_response(
            request,
            text=str(result["summary"]),
            store=True,
            mcp_server="workflow-mcp",
        )
        self._store.put(response)
        return response

    @staticmethod
    def _build_response(
        request: ResponseRequest,
        *,
        text: str,
        store: bool,
        mcp_server: str,
    ) -> dict[str, Any]:
        response_id = f"resp_{uuid4().hex}"
        message_id = f"msg_{uuid4().hex}"
        return {
            "id": response_id,
            "object": "response",
            "created_at": int(time.time()),
            "status": "completed",
            "model": request.model,
            "previous_response_id": request.previous_response_id,
            "store": store,
            "output": [
                {
                    "id": message_id,
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": text,
                            "annotations": [],
                        }
                    ],
                }
            ],
            "output_text": text,
            "metadata": {
                **(request.metadata or {}),
                "mcp_server": mcp_server,
            },
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        }


def create_responses_app(
    settings: Settings | None = None,
    *,
    runtime: AgentRuntime | None = None,
) -> Starlette:
    """Create the local Responses-compatible HTTP application."""
    current = settings or get_settings()
    current_runtime = runtime or AgentRuntime(current)

    async def create_response(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
            response_request = ResponseRequest.model_validate(payload)
            response = await current_runtime.create(response_request)
            return JSONResponse(response)
        except ValidationError as error:
            return JSONResponse(
                {
                    "error": {
                        "message": "Invalid Responses API request.",
                        "type": "invalid_request_error",
                        "code": "validation_error",
                        "details": error.errors(include_url=False),
                    }
                },
                status_code=400,
            )
        except ApiError as error:
            return JSONResponse(
                {
                    "error": {
                        "message": str(error),
                        "type": "invalid_request_error",
                        "code": error.code,
                    }
                },
                status_code=error.status_code,
            )

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return Starlette(
        routes=[
            Route("/healthz", health, methods=["GET"]),
            Route("/v1/responses", create_response, methods=["POST"]),
        ]
    )


app = create_responses_app()