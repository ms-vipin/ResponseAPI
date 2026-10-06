---
title: MCP and Foundry Agent Redeployment Runbook
description: Repeatable step-by-step runbook for shipping new private MCP server and Foundry hosted agent versions
ms.date: 2026-10-06
ms.topic: how-to
---

## Purpose

Use this runbook every time you ship a new version of a private MCP server or a
Foundry hosted agent. It assumes the private architecture already exists (VNets,
peering, private DNS, private ACR, internal Container Apps environment, Foundry
account with VNet injection). For first-time greenfield provisioning, use
[azure-deployment-plan.md](azure-deployment-plan.md) instead.

The single step that causes the most lost time is the Container Apps Easy Auth
**authorization allowlist** on the workflow MCP. If a new agent version uses a
new agent identity, its app ID must be added to `allowedApplications` or every
call returns HTTP 403 with an empty body. See [Part B](#part-b-deploy-a-new-foundry-hosted-agent-version).

## Environment values

Confirm these before running any step. The values shown are the current dev
environment; update the table per environment.

| Key | Current dev value |
| --- | --- |
| Subscription | `ebc7f959-26e9-47ac-801a-743a6a7472f2` |
| Tenant | `16b3c013-d300-468d-ac64-7eda0820b6d3` |
| MCP resource group | `rg-responseapi-private-cin-dev` |
| Container Apps environment | `cae-responseapi-private-cin-dev` |
| ACR | `acrresponseapiprivcin` (private, public access disabled) |
| MCP image repository | `acrresponseapiprivcin.azurecr.io/responseapi-mcp` |
| Reference Container App | `ca-reference-mcp-cin-dev` |
| Workflow Container App | `ca-workflow-mcp-cin-dev` |
| Workflow MCP managed identity | `id-responseapi-acr-pull-cin-dev` (`767ea88a-0d00-4a18-b1f5-ff555ed0ac94`) |
| Foundry account | `foundry-responseapi-devhbdy` |
| Foundry project | `responseapi-hosted-dev` |
| Foundry project endpoint | `https://foundry-responseapi-devhbdy.services.ai.azure.com/api/projects/responseapi-hosted-dev` |
| Model deployment | `gpt-4.1` |
| Workflow MCP Entra app (audience) | `e6bef87c-2e3a-4315-b790-11068270babf` |
| Workflow MCP audience URI | `api://e6bef87c-2e3a-4315-b790-11068270babf` |
| Easy Auth issuer | `https://login.microsoftonline.com/16b3c013-d300-468d-ac64-7eda0820b6d3/v2.0` |
| Easy Auth secret setting | `entra-client-secret` |

MCP startup commands (same image, different entrypoint):

| Server | Startup command |
| --- | --- |
| Reference (bearer) | `uvicorn responseapi.mcp_bearer:app --host 0.0.0.0 --port 8000` |
| Workflow (workload identity) | `uvicorn responseapi.mcp_workload:app --host 0.0.0.0 --port 8000` |

## Prerequisites

1. Sign in and select the subscription.

   ```powershell
   az login
   az account set --subscription ebc7f959-26e9-47ac-801a-743a6a7472f2
   ```

2. Confirm the local environment builds and passes checks.

   ```powershell
   uv sync --frozen
   uv run pytest -q
   uv run ruff check .
   uv lock --check
   ```

## Part A: Deploy a new MCP server version

Run this when MCP server code under `src/responseapi/` changes.

### A1. Temporarily open ACR for the build, then build and push

ACR stays private. Open it only for the build and re-lock immediately after.

```powershell
# Open ACR for the build
az acr update --name acrresponseapiprivcin --public-network-enabled true --default-action Allow

# Build and push a new tag (use a version or git short SHA, not latest)
$tag = (Get-Date -Format "yyyyMMdd-HHmm")
az acr build `
  --registry acrresponseapiprivcin `
  --image responseapi-mcp:$tag `
  --file Dockerfile .

# Re-lock ACR immediately
az acr update --name acrresponseapiprivcin --public-network-enabled false --default-action Deny
```

> [!IMPORTANT]
> Always re-lock the ACR in the same session. Never leave public network access
> enabled. Confirm with:
> `az acr show --name acrresponseapiprivcin --query "{public:publicNetworkAccess,default:networkRuleSet.defaultAction}" -o json`

### A2. Capture the pushed digest

Pin the Container App to the immutable digest, not the tag.

```powershell
$digest = az acr repository show --name acrresponseapiprivcin `
  --image responseapi-mcp:$tag --query "digest" -o tsv
$image = "acrresponseapiprivcin.azurecr.io/responseapi-mcp@$digest"
$image
```

### A3. Update the Container App revision

Keep the correct startup command for each app.

```powershell
# Workflow MCP
az containerapp update `
  --resource-group rg-responseapi-private-cin-dev `
  --name ca-workflow-mcp-cin-dev `
  --image $image `
  --command "uvicorn" "responseapi.mcp_workload:app" "--host" "0.0.0.0" "--port" "8000"

# Reference MCP (only if the reference server changed)
az containerapp update `
  --resource-group rg-responseapi-private-cin-dev `
  --name ca-reference-mcp-cin-dev `
  --image $image `
  --command "uvicorn" "responseapi.mcp_bearer:app" "--host" "0.0.0.0" "--port" "8000"
```

### A4. Verify the MCP ingress from inside the VNet

The ingress is private, so verify from inside the container. An unauthenticated
request must return `401` (sidecar healthy). A valid caller must get past Easy
Auth. Open a shell:

```powershell
az containerapp exec `
  --resource-group rg-responseapi-private-cin-dev `
  --name ca-workflow-mcp-cin-dev --command sh
```

Inside the shell, probe the app-direct port and the Easy Auth ingress:

```python
python - <<'PY'
import urllib.request, ssl
def p(u):
    try:
        return urllib.request.urlopen(urllib.request.Request(u), timeout=8,
            context=ssl.create_default_context()).status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return "ERR:" + type(e).__name__
print("APP_LOCAL", p("http://localhost:8000/mcp"))
print("VIA_EASYAUTH", p("https://ca-workflow-mcp-cin-dev.<env-domain>/mcp"))
PY
```

Expected: `APP_LOCAL 401` and `VIA_EASYAUTH 401` for no-token requests. A `500`
on the no-token path means the Easy Auth sidecar itself is unhealthy; a `403`
with a token means authorization denied (see [Part B](#part-b-deploy-a-new-foundry-hosted-agent-version)).

## Part B: Deploy a new Foundry hosted agent version

Run this when agent code under `hosted-agents/` or agent config changes. This
produces a new agent version (for example `v6`, `v7`).

### B1. Update agent env and config

Ensure each agent `.env` and `azure.yaml` point at the correct private MCP
endpoint and audience. For the workflow agent:

- `WORKLOAD_MCP_ENDPOINT` = `https://ca-workflow-mcp-cin-dev.<env-domain>/mcp`
- `WORKLOAD_MCP_AUDIENCE` = `api://e6bef87c-2e3a-4315-b790-11068270babf`

### B2. Deploy the agent version

```powershell
# Validate the agent definitions without Azure writes
uv run responseapi-provision --dry-run

# Create the new agent version
uv run responseapi-provision
```

### B3. Critical: update the Easy Auth authorization allowlist

A new agent version may introduce a new **AgentIdentity**. Easy Auth on the
workflow MCP only accepts callers whose app ID is in
`defaultAuthorizationPolicy.allowedApplications`. Skipping this returns HTTP 403
with an empty body and the agent reports `Error: Function failed.`

First, find the agent identity app IDs for the workflow agent:

```powershell
az ad sp list --display-name "foundry-responseapi-devhbdy-responseapi-hosted-dev-workflow-hosted-agent" `
  --query "[].{appId:appId,displayName:displayName,type:servicePrincipalType}" -o json
```

Record the `...-AgentIdentity` and `...-AgentIdentityBlueprint` app IDs. Current
dev values:

| App ID | Identity |
| --- | --- |
| `15eeadfd-426d-4f0a-b5e8-d51a44aa4461` | `workflow-hosted-agent-AgentIdentity` (the caller) |
| `8f0e3e66-e531-410b-9923-cf882074739f` | `workflow-hosted-agent-...-AgentIdentityBlueprint` |

Read the current authConfig:

```powershell
az rest --method get `
  --url "https://management.azure.com/subscriptions/ebc7f959-26e9-47ac-801a-743a6a7472f2/resourceGroups/rg-responseapi-private-cin-dev/providers/Microsoft.App/containerApps/ca-workflow-mcp-cin-dev/authConfigs/current?api-version=2024-03-01" `
  -o json
```

Write the full authConfig to a file (update `allowedApplications` with the
current agent identities), then PUT it:

```json
{
  "properties": {
    "globalValidation": { "unauthenticatedClientAction": "Return401" },
    "httpSettings": { "requireHttps": true },
    "identityProviders": {
      "azureActiveDirectory": {
        "isAutoProvisioned": false,
        "registration": {
          "clientId": "e6bef87c-2e3a-4315-b790-11068270babf",
          "clientSecretSettingName": "entra-client-secret",
          "openIdIssuer": "https://login.microsoftonline.com/16b3c013-d300-468d-ac64-7eda0820b6d3/v2.0"
        },
        "validation": {
          "allowedAudiences": [
            "e6bef87c-2e3a-4315-b790-11068270babf",
            "api://e6bef87c-2e3a-4315-b790-11068270babf"
          ],
          "defaultAuthorizationPolicy": {
            "allowedApplications": [
              "15eeadfd-426d-4f0a-b5e8-d51a44aa4461",
              "8f0e3e66-e531-410b-9923-cf882074739f"
            ]
          }
        }
      }
    },
    "login": { "preserveUrlFragmentsForLogins": false, "tokenStore": { "enabled": false } },
    "platform": { "enabled": true }
  }
}
```

```powershell
az rest --method put `
  --url "https://management.azure.com/subscriptions/ebc7f959-26e9-47ac-801a-743a6a7472f2/resourceGroups/rg-responseapi-private-cin-dev/providers/Microsoft.App/containerApps/ca-workflow-mcp-cin-dev/authConfigs/current?api-version=2024-03-01" `
  --body "@authconfig.json" `
  --query "properties.identityProviders.azureActiveDirectory.validation.defaultAuthorizationPolicy" -o json
```

> [!NOTE]
> Keep both the bare client ID (`e6bef87c...`) and the `api://` audience. The
> managed-identity token's `aud` claim is the bare GUID for a v2 token. Do not
> add the ACR-pull MI (`767ea88a...`) unless it is a real caller; the agent uses
> the AgentIdentity.

## Part C: Verify end-to-end

Invoke the live Responses endpoint. Replace `<agent>` with `workflow-hosted-agent`
or `reference-hosted-agent`.

```powershell
$tok = az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv
$url = "https://foundry-responseapi-devhbdy.services.ai.azure.com/api/projects/responseapi-hosted-dev/agents/workflow-hosted-agent/endpoint/protocols/openai/responses?api-version=v1"
$body = '{"model":"gpt-4.1","input":"Start workflow: provision the staging environment."}'
$r = Invoke-RestMethod -Method Post -Uri $url `
  -Headers @{ Authorization = "Bearer $tok"; "Content-Type" = "application/json" } -Body $body
$r | ConvertTo-Json -Depth 10
```

Success looks like a `function_call` to `continue_workflow`, a
`function_call_output` containing the real MCP summary, and `status: completed`.

Verify stateful chaining with `previous_response_id`:

```powershell
$body2 = '{"model":"gpt-4.1","input":"Now deploy the application.","previous_response_id":"<id-from-first-call>"}'
Invoke-RestMethod -Method Post -Uri $url `
  -Headers @{ Authorization = "Bearer $tok"; "Content-Type" = "application/json" } -Body $body2
```

The `function_call_output` should contain the prior summary concatenated with
the new update.

## Troubleshooting matrix

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Agent reports `Error: Function failed.` | Easy Auth 403 (caller not allowlisted) | Add the agent AgentIdentity app ID to `allowedApplications` ([B3](#b3-critical-update-the-easy-auth-authorization-allowlist)) |
| `VIA_EASYAUTH 403`, empty body, `x-ms-middleware-request-id` header | Authorization denied; token valid | Update `allowedApplications` |
| `VIA_EASYAUTH 500` on no-token probe | Easy Auth sidecar unhealthy (bad secret/issuer/config) | Verify `entra-client-secret` exists and issuer/audiences are correct |
| `401` on a request that carries a token | Audience mismatch or wrong issuer | Confirm token `aud` is in `allowedAudiences` and `iss` matches the v2 issuer |
| Image pull fails | ACR locked or MI missing AcrPull | Confirm `id-responseapi-acr-pull-cin-dev` has AcrPull on the ACR |
| `tool_user_error`, `closed the connection before returning a valid MCP response while enumerating tools`, `unexpected EOF or 0 bytes` | Prompt/toolbox agent whose MCP tool points at the internal-only MCP; Foundry tool enumeration cannot reach a private endpoint | Not fixable by DNS or allowlist. Use direct-call hosted agents, or expose the MCP to Foundry's connector. See [Known limitation](#known-limitation-toolbox--mcp-connection-agents-cannot-reach-a-private-mcp) |

Decode a managed-identity token to confirm claims (run inside the container):

```python
python - <<'PY'
from azure.identity import ManagedIdentityCredential
import base64, json
t = ManagedIdentityCredential(client_id="767ea88a-0d00-4a18-b1f5-ff555ed0ac94") \
    .get_token("api://e6bef87c-2e3a-4315-b790-11068270babf/.default").token
pl = t.split(".")[1]; pl += "=" * (-len(pl) % 4)
c = json.loads(base64.urlsafe_b64decode(pl))
print({k: c.get(k) for k in ("iss", "aud", "ver", "appid", "azp")})
PY
```

The `iss` must be the v2 issuer, `aud` must be the client ID, `ver` must be
`2.0`, and `azp` identifies the caller that must be in `allowedApplications`.

## Known limitation: toolbox / MCP-connection agents cannot reach a private MCP

Foundry **prompt agents** that attach an MCP server through a project connection
(`MCPTool` with `project_connection_id`, surfaced as a *toolbox*) fail against an
internal-only Container Apps MCP. Every call returns HTTP 400 with
`code: tool_user_error` and `closed the connection before returning a valid MCP
response while enumerating tools ... unexpected EOF or 0 bytes`.

Root cause, verified by correlating trigger timestamps with MCP app logs: the
server-side **tool enumeration** request never arrives at the MCP app. Foundry
performs enumeration from a managed plane that does **not** traverse the
network-injected agent subnet (`snet-foundry-agents`), so it cannot route to the
customer VNet's private IPs. This is independent of Easy Auth (the transport is
reset before any HTTP response) and is not fixable by DNS caching or the
allowlist.

By contrast, **direct-call hosted agents** (the pattern in this runbook) work
because the agent *runtime* egresses through `snet-foundry-agents` and reaches
the MCP over peering and the Private Endpoint.

Related DNS detail discovered while diagnosing this: the ACA environment's
internal Standard Load Balancer frontend (`10.20.1.11`) is **not** reachable over
*global* (cross-region) VNet peering; the environment's Private Endpoint
(`10.20.2.17`) is the correct private target, so the private DNS A records
(`*` and `@` in the `livelyground-….centralindia.azurecontainerapps.io` zone)
should point to the Private Endpoint, not the internal LB. This fix is necessary
for any cross-region private access but is **not sufficient** to make toolbox
agents work, because the enumerator is not on the VNet at all.

To actually enable toolbox agents, the MCP must be reachable from Foundry's MCP
connector (see the enablement plan shared alongside this runbook): either expose
an authenticated public ingress for the MCP, co-locate the MCP in a path the
connector can reach, or wait for Foundry support for VNet-injected MCP tool
enumeration.

## Guardrails

- Do not change networking (VNets, peering, private endpoints, DNS, public IPs).
- Keep ACR private; only open it for a build and re-lock in the same session.
- Do not add Azure components beyond what exists (no Search, Cosmos, Storage).
- Pin Container Apps to image digests, not `latest`.
- After any Easy Auth edit, re-run [Part C](#part-c-verify-end-to-end).
