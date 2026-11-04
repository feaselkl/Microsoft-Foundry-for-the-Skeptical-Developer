#!/bin/bash
# Deploy the demo-4 MCP server (Foundry Feature Registry) to Azure Container Apps.
#
# Foundry's toolbox connects to REMOTE MCP servers over HTTPS, so a local stdio
# server will not work -- it needs a public endpoint. Container Apps gives one
# with managed TLS, and `az containerapp up --source` builds the image in Azure,
# so you do not need Docker installed locally.
#
# Run this AFTER infra/setup.sh. It appends the resulting URL to code/.env.
#
# Usage:
#   ./infra/deploy-mcp-server.sh

set -euo pipefail

RESOURCE_GROUP="${FOUNDRY_RESOURCE_GROUP:-rg-foundry-skeptic}"
LOCATION="${FOUNDRY_LOCATION:-westus3}"
ENVIRONMENT="${FOUNDRY_ACA_ENVIRONMENT:-aca-foundry-skeptic}"
APP_NAME="${FOUNDRY_MCP_APP_NAME:-mcp-feature-registry}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$REPO_ROOT/code/demos/04_agents/mcp_server"
ENV_FILE="$REPO_ROOT/code/.env"

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

say "Checking prerequisites"

if ! command -v az > /dev/null 2>&1; then
    echo "ERROR: Azure CLI not found."
    exit 1
fi

if ! az account show > /dev/null 2>&1; then
    echo "ERROR: Not signed in. Run: az login"
    exit 1
fi

if [ "$(az group exists --name "$RESOURCE_GROUP")" != "true" ]; then
    echo "ERROR: Resource group '$RESOURCE_GROUP' does not exist."
    echo "       Run ./infra/setup.sh first."
    exit 1
fi

if [ ! -f "$SOURCE_DIR/Dockerfile" ]; then
    echo "ERROR: No Dockerfile at $SOURCE_DIR"
    exit 1
fi

if ! az extension show --name containerapp > /dev/null 2>&1; then
    echo "    Installing the containerapp CLI extension..."
    az extension add --name containerapp --only-show-errors --output none
fi

# Container Apps providers.
#
#   Microsoft.App                Container Apps itself
#   Microsoft.OperationalInsights  the environment's Log Analytics workspace
#   Microsoft.ContainerRegistry  `containerapp up --source` builds the image in
#                                a registry it creates for you -- easy to miss
#                                until it fails halfway through a build
say "Resource providers"
ensure_providers \
    Microsoft.App \
    Microsoft.OperationalInsights \
    Microsoft.ContainerRegistry

say "Container Apps environment: $ENVIRONMENT"
if az containerapp env show --name "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
    echo "    (exists, skipping)"
else
    az containerapp env create \
        --name "$ENVIRONMENT" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --output none
    echo "    Created."
fi

say "Building and deploying: $APP_NAME"
echo "    Source: $SOURCE_DIR"
echo "    This builds the image in Azure and takes a few minutes."

# --source builds remotely, so no local Docker required.
# --ingress external gives a public HTTPS URL, which the toolbox needs.
az containerapp up \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT" \
    --source "$SOURCE_DIR" \
    --ingress external \
    --target-port 8000
# No --output here: `containerapp up` rejects it (extension 1.3.0b5), since it
# streams the remote build log. That log is worth seeing during a long build.

FQDN=$(az containerapp show \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query properties.configuration.ingress.fqdn --output tsv)

MCP_URL="https://$FQDN/mcp"

say "Deployed"
echo "    MCP endpoint: $MCP_URL"

# Record it for create_toolbox.py.
if [ -f "$ENV_FILE" ]; then
    # Replace any previous value rather than appending a duplicate.
    if grep -q '^FOUNDRY_MCP_SERVER_URL=' "$ENV_FILE"; then
        sed -i.bak "s|^FOUNDRY_MCP_SERVER_URL=.*|FOUNDRY_MCP_SERVER_URL=$MCP_URL|" "$ENV_FILE"
        rm -f "$ENV_FILE.bak"
    else
        printf '\nFOUNDRY_MCP_SERVER_URL=%s\n' "$MCP_URL" >> "$ENV_FILE"
    fi
    echo "    Written to code/.env"
else
    echo ""
    echo "    NOTE: code/.env not found. Add this line yourself:"
    echo "          FOUNDRY_MCP_SERVER_URL=$MCP_URL"
fi

say "Verifying the server speaks MCP"
# A real MCP initialize call, and only HTTP 200 counts. Any-response-at-all is
# not good enough: a crashed container gives no response, and a server that
# rejects the public Host header answers 421 -- which looks "up" and still
# fails every call from Foundry. Retries, because a new revision can take a
# minute or two to activate after `containerapp up` returns.
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"deploy-check","version":"1"}}}'
CODE="000"
for attempt in $(seq 1 12); do
    CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -X POST "$MCP_URL" \
        -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' \
        -d "$INIT" || true)
    [ -z "$CODE" ] && CODE="000"
    [ "$CODE" = "200" ] && break
    echo "    HTTP $CODE, waiting for the revision to come up ($attempt/12)..."
    sleep 15
done

if [ "$CODE" != "200" ]; then
    echo ""
    echo "ERROR: the MCP server is not answering an MCP initialize call (last HTTP $CODE)."
    case "$CODE" in
        000) echo "       No response: the container is probably crashing on startup." ;;
        421) echo "       421 Invalid Host header: the server is rejecting the public hostname." ;;
    esac
    echo ""
    echo "       Do not run agent_with_mcp.py yet -- it will hang waiting on this server."
    echo "       Revision health:"
    echo "         az containerapp revision list -n $APP_NAME -g $RESOURCE_GROUP -o table"
    echo "       Startup events (crash loops show up here, not in the console log):"
    echo "         az containerapp logs show -n $APP_NAME -g $RESOURCE_GROUP --type system --tail 30"
    exit 1
fi
echo "    MCP initialize returned HTTP 200. The server is live."

cat <<DONEEOF

Next:
    cd code
    uv run python demos/04_agents/agent_with_mcp.py
    uv run python demos/04_agents/create_toolbox.py

teardown.sh removes this along with everything else in the resource group.
DONEEOF
