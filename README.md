---
title: Foundry MCP Responses Solution
description: Local reference implementation for two authenticated MCP-backed Foundry agents
ms.date: 2026-10-05
ms.topic: overview
---

## Architecture

The local stack has three HTTP services:

* Responses-compatible API at `http://127.0.0.1:8000/v1/responses`
* Bearer-authenticated MCP endpoint at `http://127.0.0.1:8001/mcp`
* Workload-identity MCP endpoint at `http://127.0.0.1:8002/mcp`

`reference-agent` is stateless. It calls only `reference-mcp`, requires
`store=false`, and rejects `previous_response_id`.

`workflow-agent` is stateful. It calls only `workflow-mcp`, stores responses,
and uses `previous_response_id` to continue prior context.

The localhost workload identity token is an explicit development substitute.
The Azure design replaces it with the Foundry project's managed identity and
Microsoft Entra validation at Azure Container Apps ingress.

## Run Locally

Install the locked environment and start all services:

```powershell
uv sync --frozen
uv run responseapi
```

Check the service:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

Create a stateless response:

```powershell
$body = @{
	model = "reference-agent"
	input = "Explain the MCP registration"
	store = $false
} | ConvertTo-Json

Invoke-RestMethod `
	-Method Post `
	-Uri http://127.0.0.1:8000/v1/responses `
	-ContentType application/json `
	-Body $body
```

Create and continue a stateful response:

```powershell
$firstBody = @{
	model = "workflow-agent"
	input = "Build the MCP containers"
} | ConvertTo-Json

$first = Invoke-RestMethod `
	-Method Post `
	-Uri http://127.0.0.1:8000/v1/responses `
	-ContentType application/json `
	-Body $firstBody

$nextBody = @{
	model = "workflow-agent"
	input = "Register them in Foundry"
	previous_response_id = $first.id
} | ConvertTo-Json

Invoke-RestMethod `
	-Method Post `
	-Uri http://127.0.0.1:8000/v1/responses `
	-ContentType application/json `
	-Body $nextBody
```

## Validate

```powershell
uv run pytest -q
uv run ruff check .
uv lock --check
```

## Prepare Foundry Agents

Use a Foundry project created with Standard Agent Setup and creation-time VNet
injection. Copy `.env.example` to `.env` and set MCP endpoints that resolve only
through the peered private VNets. Verify agent definitions without Azure access:

```powershell
uv run responseapi-provision --dry-run
```

After private DNS, endpoint reachability, the two Foundry project connections,
and `az login` are validated, remove `--dry-run` to create the agent versions.

See [docs/azure-deployment-plan.md](docs/azure-deployment-plan.md) for the
deployment sequence, identity model, and Foundry API examples.
