#!/bin/bash
# Build the demo environment for "Microsoft Foundry for the Skeptical Developer".
#
# Creates a resource group, a Foundry resource with project management enabled,
# a project, a model deployment, and an Application Insights resource for the
# tracing demo. Then writes code/.env so the demo scripts just run.
#
# Safe to re-run: every step checks before it creates.
#
# Usage:
#   ./infra/setup.sh
#   FOUNDRY_LOCATION=eastus ./infra/setup.sh     # override any setting below
#
# Tear it down afterward with ./infra/teardown.sh -- see the note on cost there.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration. Override any of these as environment variables.
# ---------------------------------------------------------------------------

# West US 3 is the default deliberately: instant access (demo 3) is limited to
# that region during preview. Change it and instant_access.py will fail while
# deployed_call.py keeps working.
LOCATION="${FOUNDRY_LOCATION:-westus3}"

RESOURCE_GROUP="${FOUNDRY_RESOURCE_GROUP:-rg-foundry-skeptic}"
PROJECT_NAME="${FOUNDRY_PROJECT_NAME:-proj-foundry-skeptic}"
MODEL_NAME="${FOUNDRY_MODEL_NAME:-gpt-5-mini}"
DEPLOYMENT_NAME="${FOUNDRY_DEPLOYMENT_NAME:-gpt-5-mini}"
SKU_NAME="${FOUNDRY_SKU_NAME:-GlobalStandard}"
# Capacity is a RATE LIMIT on a GlobalStandard deployment, not reserved
# hardware: billing is per token either way, so a higher ceiling costs nothing.
# Each unit is 1 request and 1,000 tokens per minute. 10 looked generous and was
# not: the demo-5 evaluation runs two agents plus two LLM judges against this
# one deployment, and at 10 it lost 7 of 24 scores to HTTP 429.
SKU_CAPACITY="${FOUNDRY_SKU_CAPACITY:-100}"
APP_INSIGHTS_NAME="${FOUNDRY_APP_INSIGHTS_NAME:-appi-foundry-skeptic}"

# The resource name doubles as the custom domain, which must be globally
# unique. A random suffix avoids collisions with everyone else who ran this.
# Pin it by exporting FOUNDRY_RESOURCE_NAME if you want a stable name.
RESOURCE_NAME="${FOUNDRY_RESOURCE_NAME:-foundry-skeptic-$(whoami | tr -cd 'a-z0-9' | cut -c1-8)}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/code/.env"

# shellcheck source=_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
skip() { printf '    (exists, skipping) %s\n' "$1"; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

say "Checking prerequisites"

if ! command -v az > /dev/null 2>&1; then
    echo "ERROR: Azure CLI not found. See https://learn.microsoft.com/cli/azure/install-azure-cli"
    exit 1
fi

# The `az cognitiveservices account project` commands landed in 2.80.0. On an
# older CLI this script fails later with a confusing "unrecognized arguments".
AZ_VERSION=$(az version --query '"azure-cli"' --output tsv)
if [ "$(printf '%s\n2.80.0\n' "$AZ_VERSION" | sort -V | head -1)" != "2.80.0" ]; then
    echo "ERROR: Azure CLI $AZ_VERSION is too old. Version 2.80.0 or later is required"
    echo "       for the 'az cognitiveservices account project' commands. Run: az upgrade"
    exit 1
fi

if ! az account show > /dev/null 2>&1; then
    echo "ERROR: Not signed in. Run: az login"
    exit 1
fi

SUBSCRIPTION=$(az account show --query name --output tsv)
echo "    Azure CLI:    $AZ_VERSION"
echo "    Subscription: $SUBSCRIPTION"
echo "    Location:     $LOCATION"
echo "    Resource:     $RESOURCE_NAME"

if [ "$LOCATION" != "westus3" ]; then
    echo ""
    echo "    NOTE: Location is not westus3. Instant access (demo 3) is preview-limited"
    echo "          to West US 3, so instant_access.py will likely fail."
fi

# ---------------------------------------------------------------------------
# Resource providers
# ---------------------------------------------------------------------------
# Must happen before any resource is created. A subscription that has never used
# these services will otherwise fail with MissingSubscriptionRegistration.
#
#   Microsoft.CognitiveServices  the Foundry resource (kind AIServices)
#   Microsoft.Insights           Application Insights
#   Microsoft.OperationalInsights  the Log Analytics workspace App Insights uses

say "Resource providers"
ensure_providers \
    Microsoft.CognitiveServices \
    Microsoft.Insights \
    Microsoft.OperationalInsights

# ---------------------------------------------------------------------------
# Resource group
# ---------------------------------------------------------------------------

say "Resource group: $RESOURCE_GROUP"
if [ "$(az group exists --name "$RESOURCE_GROUP")" = "true" ]; then
    skip "$RESOURCE_GROUP"
else
    az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
    echo "    Created."
fi

# ---------------------------------------------------------------------------
# Foundry resource
# ---------------------------------------------------------------------------

say "Foundry resource: $RESOURCE_NAME"
if az cognitiveservices account show \
        --name "$RESOURCE_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
    skip "$RESOURCE_NAME"
else
    # --assign-identity is required for project management; without it the
    # project create below fails. --allow-project-management cannot be changed
    # after creation, so getting it right here matters.
    az cognitiveservices account create \
        --name "$RESOURCE_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --kind AIServices \
        --sku S0 \
        --location "$LOCATION" \
        --custom-domain "$RESOURCE_NAME" \
        --assign-identity \
        --allow-project-management true \
        --yes \
        --output none
    echo "    Created."
fi

STATE=$(az cognitiveservices account show \
    --name "$RESOURCE_NAME" --resource-group "$RESOURCE_GROUP" \
    --query properties.provisioningState --output tsv)
if [ "$STATE" != "Succeeded" ]; then
    echo "ERROR: Resource is in state '$STATE', expected 'Succeeded'."
    exit 1
fi

# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

say "Project: $PROJECT_NAME"
if az cognitiveservices account project show \
        --name "$RESOURCE_NAME" --resource-group "$RESOURCE_GROUP" \
        --project-name "$PROJECT_NAME" > /dev/null 2>&1; then
    skip "$PROJECT_NAME"
else
    az cognitiveservices account project create \
        --name "$RESOURCE_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --project-name "$PROJECT_NAME" \
        --location "$LOCATION" \
        --output none
    echo "    Created."
fi

# ---------------------------------------------------------------------------
# Model deployment
# ---------------------------------------------------------------------------

say "Model deployment: $DEPLOYMENT_NAME ($MODEL_NAME)"
if az cognitiveservices account deployment show \
        --name "$RESOURCE_NAME" --resource-group "$RESOURCE_GROUP" \
        --deployment-name "$DEPLOYMENT_NAME" > /dev/null 2>&1; then
    CURRENT_CAPACITY=$(az cognitiveservices account deployment show \
        --name "$RESOURCE_NAME" --resource-group "$RESOURCE_GROUP" \
        --deployment-name "$DEPLOYMENT_NAME" --query sku.capacity --output tsv)
    if [ "${CURRENT_CAPACITY:-0}" -ge "$SKU_CAPACITY" ]; then
        skip "$DEPLOYMENT_NAME (capacity $CURRENT_CAPACITY)"
    else
        # There is no `deployment update`; create on an existing name updates it
        # in place, keeping the model version already deployed.
        EXISTING_VERSION=$(az cognitiveservices account deployment show \
            --name "$RESOURCE_NAME" --resource-group "$RESOURCE_GROUP" \
            --deployment-name "$DEPLOYMENT_NAME" --query properties.model.version --output tsv)
        echo "    Raising capacity $CURRENT_CAPACITY -> $SKU_CAPACITY (no extra cost on $SKU_NAME)"
        az cognitiveservices account deployment create \
            --name "$RESOURCE_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --deployment-name "$DEPLOYMENT_NAME" \
            --model-name "$MODEL_NAME" \
            --model-version "$EXISTING_VERSION" \
            --model-format OpenAI \
            --sku-capacity "$SKU_CAPACITY" \
            --sku-name "$SKU_NAME" \
            --output none
        echo "    Updated."
    fi
else
    # Model versions move. Ask the region what it actually has rather than
    # hard-coding a version that will rot.
    MODEL_VERSION=$(az cognitiveservices model list \
        --location "$LOCATION" \
        --query "[?model.name=='$MODEL_NAME'] | [0].model.version" \
        --output tsv 2>/dev/null || true)

    if [ -z "$MODEL_VERSION" ] || [ "$MODEL_VERSION" = "None" ]; then
        echo "ERROR: Model '$MODEL_NAME' is not available in $LOCATION."
        echo "       See what is, with:"
        echo "         az cognitiveservices model list --location $LOCATION --output table"
        exit 1
    fi

    echo "    Version in $LOCATION: $MODEL_VERSION"
    az cognitiveservices account deployment create \
        --name "$RESOURCE_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --deployment-name "$DEPLOYMENT_NAME" \
        --model-name "$MODEL_NAME" \
        --model-version "$MODEL_VERSION" \
        --model-format OpenAI \
        --sku-capacity "$SKU_CAPACITY" \
        --sku-name "$SKU_NAME" \
        --output none
    echo "    Created."
fi

# ---------------------------------------------------------------------------
# Application Insights (demo 5)
# ---------------------------------------------------------------------------

say "Application Insights: $APP_INSIGHTS_NAME"
if ! az extension show --name application-insights > /dev/null 2>&1; then
    echo "    Installing the application-insights CLI extension..."
    az extension add --name application-insights --only-show-errors --output none
fi

if az monitor app-insights component show \
        --app "$APP_INSIGHTS_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
    skip "$APP_INSIGHTS_NAME"
else
    az monitor app-insights component create \
        --app "$APP_INSIGHTS_NAME" \
        --location "$LOCATION" \
        --resource-group "$RESOURCE_GROUP" \
        --application-type web \
        --output none
    echo "    Created."
fi

# ---------------------------------------------------------------------------
# Data-plane access
# ---------------------------------------------------------------------------
# The trap that catches everyone once.
#
# Owner and Contributor are CONTROL-plane roles. Owner is literally
# actions:["*"], dataActions:[]. You can create, configure and delete this
# resource and you cannot make one inference call against it. Entra-based
# data-plane access needs a role that grants Microsoft.CognitiveServices/* as a
# DATA action -- and since the project client is Entra-only, with no API key
# path, there is no fallback. You just get 403.
#
# Foundry Project Manager grants the data actions AND accounts/projects/*,
# which the demo-4 hosted agent deploy needs. Referenced by GUID because these
# roles were renamed recently and the old names still appear in places.

say "Data-plane access"

FOUNDRY_PROJECT_MANAGER="eadc314b-1a2d-4efa-be10-5d325db5065e"
ROLE_JUST_ASSIGNED=0
ACCOUNT_ID=$(az cognitiveservices account show \
    --name "$RESOURCE_NAME" --resource-group "$RESOURCE_GROUP" \
    --query id --output tsv)

PRINCIPAL_ID=$(az ad signed-in-user show --query id --output tsv 2>/dev/null || true)
PRINCIPAL_TYPE="User"

if [ -z "$PRINCIPAL_ID" ]; then
    # Signed in as a service principal rather than a user.
    SP_APP_ID=$(az account show --query user.name --output tsv 2>/dev/null || true)
    PRINCIPAL_ID=$(az ad sp show --id "$SP_APP_ID" --query id --output tsv 2>/dev/null || true)
    PRINCIPAL_TYPE="ServicePrincipal"
fi

if [ -z "$PRINCIPAL_ID" ]; then
    echo "    WARNING: could not resolve the signed-in principal, so no role was"
    echo "    assigned. If the demos return 403, assign 'Foundry Project Manager'"
    echo "    ($FOUNDRY_PROJECT_MANAGER) to yourself on:"
    echo "      $ACCOUNT_ID"
else
    EXISTING=$(az role assignment list \
        --assignee "$PRINCIPAL_ID" --scope "$ACCOUNT_ID" \
        --query "[?roleDefinitionId!=null] | [?contains(roleDefinitionId, '$FOUNDRY_PROJECT_MANAGER')].id" \
        --output tsv 2>/dev/null || true)

    if [ -n "$EXISTING" ]; then
        skip "Foundry Project Manager already assigned"
    else
        ROLE_JUST_ASSIGNED=1
        if az role assignment create \
                --role "$FOUNDRY_PROJECT_MANAGER" \
                --assignee-object-id "$PRINCIPAL_ID" \
                --assignee-principal-type "$PRINCIPAL_TYPE" \
                --scope "$ACCOUNT_ID" \
                --output none 2>/dev/null; then
            echo "    Assigned Foundry Project Manager at account scope."
        else
            cat <<'ROLEERR'
    WARNING: could not create the role assignment.

    Creating one needs Microsoft.Authorization/roleAssignments/write -- Owner or
    User Access Administrator. Being Contributor is not enough, and neither is
    any amount of resource-group access.

    Ask someone with that right to assign 'Foundry Project Manager' to you on
    the Foundry account, or do it in the portal under Access control (IAM).
    Without it every demo returns 403.
ROLEERR
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Connect Application Insights to the project (demo 5 tracing)
# ---------------------------------------------------------------------------
# Creating the Application Insights resource is not enough: Foundry only sends
# traces to it, and the SDK only finds it, once it is a CONNECTION on the
# project. This mirrors Microsoft's own template, foundry-samples
# infrastructure/infrastructure-setup-bicep/01-connections/
# connection-application-insights.bicep: an AppInsights connection on both the
# account and the project, keyed with the connection string, plus two read
# roles on Application Insights.
#
# Sent as ARM PUTs with `az rest` rather than `az ... connection create --file`,
# whose file format is undocumented; the body below is the template's verbatim.

say "Connect Application Insights to the project"

CONN_API="2025-04-01-preview"
APPI_ID=$(az monitor app-insights component show \
    --app "$APP_INSIGHTS_NAME" --resource-group "$RESOURCE_GROUP" --query id --output tsv)
APPI_CONN=$(az monitor app-insights component show \
    --app "$APP_INSIGHTS_NAME" --resource-group "$RESOURCE_GROUP" --query connectionString --output tsv)
PROJECT_ID=$(az cognitiveservices account project show \
    --name "$RESOURCE_NAME" --resource-group "$RESOURCE_GROUP" \
    --project-name "$PROJECT_NAME" --query id --output tsv)
PROJECT_PRINCIPAL=$(az cognitiveservices account project show \
    --name "$RESOURCE_NAME" --resource-group "$RESOURCE_GROUP" \
    --project-name "$PROJECT_NAME" --query identity.principalId --output tsv)

# A project allows only one Application Insights connection. Leave a different
# one alone rather than fight it.
EXISTING_APPI_TARGET=$(az rest --method get \
    --url "https://management.azure.com${PROJECT_ID}/connections?api-version=${CONN_API}" \
    --query "value[?properties.category=='AppInsights'] | [0].properties.target" \
    --output tsv 2>/dev/null || true)

connection_body() {
    # JSON-escape the connection string (backslash, then double quote).
    local key=${APPI_CONN//\\/\\\\}; key=${key//\"/\\\"}
    printf '{"properties":{"category":"AppInsights","target":"%s","authType":"ApiKey","isSharedToAll":true,"credentials":{"key":"%s"},"metadata":{"ApiType":"Azure","ResourceId":"%s"}}}' \
        "$APPI_ID" "$key" "$APPI_ID"
}

if [ -n "$EXISTING_APPI_TARGET" ] && [ "${EXISTING_APPI_TARGET,,}" = "${APPI_ID,,}" ]; then
    skip "connection to $APP_INSIGHTS_NAME"
elif [ -n "$EXISTING_APPI_TARGET" ]; then
    echo "    WARNING: the project is already connected to a different Application Insights:"
    echo "      $EXISTING_APPI_TARGET"
    echo "    Leaving it in place. Demo 5 traces will go there instead."
else
    BODY_FILE=$(mktemp)
    connection_body > "$BODY_FILE"
    az rest --method put \
        --url "https://management.azure.com${ACCOUNT_ID}/connections/${RESOURCE_NAME}-appinsights?api-version=${CONN_API}" \
        --body "@$BODY_FILE" --headers "Content-Type=application/json" --output none
    az rest --method put \
        --url "https://management.azure.com${PROJECT_ID}/connections/${APP_INSIGHTS_NAME}?api-version=${CONN_API}" \
        --body "@$BODY_FILE" --headers "Content-Type=application/json" --output none
    rm -f "$BODY_FILE"   # it holds the connection string
    echo "    Connected on the account and the project."
fi

# Log Analytics Reader + Privileged Monitoring Data Reader, by GUID like the
# template. The second is a DATA-plane role (tables/data/read) -- the same trap
# as Owner on the Foundry resource: Owner can manage Application Insights but
# cannot read the GenAI content in the traces without it. The project's
# identity needs both so evaluation can read traces; you need both to view them.
grant_appi_role() {
    local principal=$1 type=$2 role=$3 label=$4 who=$5
    if [ -z "$principal" ]; then
        echo "    WARNING: no principal for $who; skipping $label"
        return
    fi
    if [ "$(az role assignment list --assignee "$principal" --role "$role" --scope "$APPI_ID" \
            --query 'length(@)' --output tsv 2>/dev/null || echo 0)" != "0" ]; then
        skip "$label for $who"
    elif az role assignment create --assignee-object-id "$principal" \
            --assignee-principal-type "$type" --role "$role" --scope "$APPI_ID" --output none 2>/dev/null; then
        echo "    Granted $label to $who."
    else
        echo "    WARNING: could not grant $label to $who (needs Owner or User Access Administrator)."
    fi
}

for ROLE in "73c42c96-874c-492b-b04d-ab87d138a893:Log Analytics Reader" \
            "dbc9c667-e97f-4491-aee6-90b9cf960190:Privileged Monitoring Data Reader"; do
    grant_appi_role "$PROJECT_PRINCIPAL" ServicePrincipal "${ROLE%%:*}" "${ROLE#*:}" "the project"
    grant_appi_role "${PRINCIPAL_ID:-}" "${PRINCIPAL_TYPE:-User}" "${ROLE%%:*}" "${ROLE#*:}" "you"
done

# Continuous evaluation (demo 5) runs AS THE PROJECT, not as you: the service
# calls the agent's traffic and the judge model under the project's managed
# identity. Microsoft's continuous-evaluation sample makes Foundry User on the
# project's identity a prerequisite. Account scope covers the project.
FOUNDRY_USER="53ca6127-db72-4b80-b1b0-d745d6d5456d"
if [ -z "$PROJECT_PRINCIPAL" ]; then
    echo "    WARNING: the project has no managed identity; continuous evaluation will not run."
elif [ "$(az role assignment list --assignee "$PROJECT_PRINCIPAL" --role "$FOUNDRY_USER" --scope "$ACCOUNT_ID" \
        --query 'length(@)' --output tsv 2>/dev/null || echo 0)" != "0" ]; then
    skip "Foundry User for the project (continuous evaluation)"
elif az role assignment create --assignee-object-id "$PROJECT_PRINCIPAL" \
        --assignee-principal-type ServicePrincipal --role "$FOUNDRY_USER" --scope "$ACCOUNT_ID" --output none 2>/dev/null; then
    echo "    Granted Foundry User to the project (continuous evaluation). Allow a few minutes to propagate."
else
    echo "    WARNING: could not grant Foundry User to the project (needs Owner or User Access Administrator)."
fi

# ---------------------------------------------------------------------------
# Write code/.env
# ---------------------------------------------------------------------------

say "Writing $ENV_FILE"

PROJECT_ENDPOINT=$(az cognitiveservices account project show \
    --name "$RESOURCE_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --project-name "$PROJECT_NAME" \
    --query 'properties.endpoints."AI Foundry API"' --output tsv)

HAD_ENV=0
if [ -f "$ENV_FILE" ]; then
    cp "$ENV_FILE" "$ENV_FILE.bak"
    HAD_ENV=1
    echo "    Existing .env backed up to .env.bak"
fi

cat > "$ENV_FILE" <<ENVEOF
# Generated by infra/setup.sh on $(date -u '+%Y-%m-%d %H:%M UTC')
# Resource group: $RESOURCE_GROUP

FOUNDRY_PROJECT_ENDPOINT=$PROJECT_ENDPOINT
FOUNDRY_MODEL_DEPLOYMENT=$DEPLOYMENT_NAME
FOUNDRY_INSTANT_MODEL=$MODEL_NAME
FOUNDRY_AGENT_NAME=SkepticalDeveloperAgent
ENVEOF

# Keep what other scripts wrote. deploy-mcp-server.sh appends
# FOUNDRY_MCP_SERVER_URL; dropping it on a re-run of this script would leave
# demo 4 pointing at nothing.
if [ "$HAD_ENV" -eq 1 ]; then
    OWN='^(FOUNDRY_PROJECT_ENDPOINT|FOUNDRY_MODEL_DEPLOYMENT|FOUNDRY_INSTANT_MODEL|FOUNDRY_AGENT_NAME)='
    KEPT=$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE.bak" | grep -vE "$OWN" || true)
    if [ -n "$KEPT" ]; then
        printf '\n# Kept from the previous .env (written by other scripts)\n%s\n' "$KEPT" >> "$ENV_FILE"
        echo "    Kept: $(echo "$KEPT" | cut -d= -f1 | tr '\n' ' ')"
    fi
fi

echo "    Endpoint: $PROJECT_ENDPOINT"

# ---------------------------------------------------------------------------
# Verify the data plane actually works
# ---------------------------------------------------------------------------
# Provisioning succeeding tells you nothing about whether you can CALL any of
# it. Make one real inference call here, so a 403 surfaces now with an
# explanation instead of later inside a demo script.

say "Verifying data-plane access"

# Role assignments are eventually consistent, so retry rather than fail on the
# first 403. See the window sizing below for how long that actually takes.
TOKEN=$(az account get-access-token --scope https://ai.azure.com/.default \
    --query accessToken --output tsv 2>/dev/null || true)

if [ -z "$TOKEN" ]; then
    echo "    WARNING: could not get a token for https://ai.azure.com/.default"
    echo "    Skipping verification. If the demos 403, start here."
else
    # Sizing this window matters. Measured on a fresh assignment: the first
    # successful call came 5m12s after `az role assignment create` returned.
    # A two-minute window reports failure on a perfectly good environment, which
    # is worse than no check at all.
    #
    # So: be patient after a fresh assignment, brisk when the role was already
    # there and a 403 means something else is wrong.
    if [ "$ROLE_JUST_ASSIGNED" -eq 1 ]; then
        MAX_ATTEMPTS=20          # 20 x 30s = 10 minutes
        echo "    Role was just assigned. Azure RBAC is eventually consistent and"
        echo "    this typically takes 5-6 minutes. Waiting up to 10."
    else
        MAX_ATTEMPTS=4           # 4 x 30s = 2 minutes
    fi

    VERIFY_START=$(date +%s)
    VERIFY_OK=0
    for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
        HTTP_CODE=$(curl -s -o /tmp/foundry_verify_body.$$ -w '%{http_code}' \
            --max-time 60 \
            -X POST "$PROJECT_ENDPOINT/openai/v1/responses" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $TOKEN" \
            -d "{\"model\": \"$DEPLOYMENT_NAME\", \"input\": \"Reply with the single word: ready\"}" \
            2>/dev/null || echo "000")

        case "$HTTP_CODE" in
            2*)
                printf '    Inference call succeeded (HTTP %s after %ss).\n' \
                    "$HTTP_CODE" "$(( $(date +%s) - VERIFY_START ))"
                VERIFY_OK=1
                break
                ;;
            401|403)
                ELAPSED=$(( $(date +%s) - VERIFY_START ))
                if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
                    printf '    HTTP %s after %ss -- waiting for RBAC to propagate (%s/%s)\n' \
                        "$HTTP_CODE" "$ELAPSED" "$attempt" "$MAX_ATTEMPTS"
                    sleep 30
                    # Mint a fresh token each attempt; the cached one can outlive
                    # the wait and it costs nothing to re-request.
                    TOKEN=$(az account get-access-token --scope https://ai.azure.com/.default \
                        --query accessToken --output tsv 2>/dev/null || echo "$TOKEN")
                else
                    printf '    HTTP %s after %ss and %s attempts.\n' \
                        "$HTTP_CODE" "$ELAPSED" "$MAX_ATTEMPTS"
                fi
                ;;
            *)
                echo "    HTTP $HTTP_CODE"
                head -c 400 /tmp/foundry_verify_body.$$ 2>/dev/null && echo
                break
                ;;
        esac
    done
    rm -f /tmp/foundry_verify_body.$$

    if [ "$VERIFY_OK" -ne 1 ]; then
        cat <<'VERIFYERR'

    The resources exist but you cannot call them yet.

    If this is 403, it is almost certainly the control-plane / data-plane split:
    Owner and Contributor grant actions:["*"] with dataActions:[], so they let
    you build this resource without letting you use it. Check with:

      az role assignment list --assignee <you> --scope <account id> -o table

    You want 'Foundry Project Manager' or 'Foundry User' there. Nothing else
    will do, and there is no API key fallback -- the project client is
    Entra-only.

    Role assignments can take a few minutes to propagate. If one was just
    created, wait and re-run this script; it is safe to re-run.

VERIFYERR
    fi
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

say "Demo environment ready"
cat <<DONEEOF

Next:
    cd code && uv sync
    uv run python demos/02_platform/first_call.py

Application Insights ($APP_INSIGHTS_NAME) is connected to the project, so
Foundry traces prompt and hosted agents with no code changes. Traces take 2-5
minutes to appear: open an agent in the portal and look at its Traces tab.

When you are done with the talk, tear it all down:

    ./infra/teardown.sh

DONEEOF
