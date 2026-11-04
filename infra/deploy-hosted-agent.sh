#!/bin/bash
# Deploy the demo-4 hosted agent to Foundry Agent Service.
#
# Thin wrapper around code/demos/04_agents/deploy_hosted_agent.py, which is
# where the real work happens -- the deploy path is a Python SDK call, not an
# az command, so the script is Python and this just runs it with the right
# environment.
#
# This is a genuine Foundry HOSTED AGENT: source zipped and uploaded, built
# remotely by Foundry, served on a managed endpoint with autoscale and its own
# Entra identity. Foundry runs your container. That is the claim section 4
# makes, and this is what backs it.
#
# Order matters. Run these first:
#   ./infra/setup.sh
#   ./infra/deploy-mcp-server.sh
#   (cd code && uv run python demos/04_agents/create_toolbox.py)
#
# Usage:
#   ./infra/deploy-hosted-agent.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CODE_DIR="$REPO_ROOT/code"
ENV_FILE="$CODE_DIR/.env"

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

say "Checking prerequisites"

if ! command -v uv > /dev/null 2>&1; then
    echo "ERROR: uv not found. See https://docs.astral.sh/uv/"
    exit 1
fi

if ! az account show > /dev/null 2>&1; then
    echo "ERROR: Not signed in. Run: az login"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: code/.env not found. Run ./infra/setup.sh first."
    exit 1
fi

if ! grep -q '^FOUNDRY_MCP_SERVER_URL=http' "$ENV_FILE"; then
    echo "ERROR: FOUNDRY_MCP_SERVER_URL is not set in code/.env."
    echo "       Run ./infra/deploy-mcp-server.sh first -- the toolbox needs a"
    echo "       server to point at."
    exit 1
fi

echo "    Deploying user needs 'Foundry Project Manager' at project scope."
echo "    The agent gets its OWN identity from Foundry; nothing to assign."

# setup.sh registers CognitiveServices, and deploy-mcp-server.sh registers
# ContainerRegistry. Both are needed here: Foundry builds the agent image
# remotely into a registry. Verify rather than assume, in case this script was
# run on its own.
say "Resource providers"
ensure_providers \
    Microsoft.CognitiveServices \
    Microsoft.ContainerRegistry

say "Deploying"
cd "$CODE_DIR"
uv run python demos/04_agents/deploy_hosted_agent.py

cat <<'DONEEOF'

Re-run the demo question without redeploying:

    cd code && uv run python demos/04_agents/invoke_hosted_agent.py

teardown.sh removes this along with everything else.
DONEEOF
