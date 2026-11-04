#!/bin/bash
# Tear down the demo environment for "Microsoft Foundry for the Skeptical Developer".
#
# Deletes the ENTIRE resource group created by setup.sh, including the Foundry
# resource, the project, every model deployment, and Application Insights.
# This cannot be undone.
#
# Run this after every delivery. The model deployment is pay-per-token so idle
# inference costs little, but the resource and Application Insights ingestion
# are not free, and a forgotten demo environment is a monthly line item you
# will not notice until it has run for a year.
#
# Usage:
#   ./infra/teardown.sh
#   FOUNDRY_RESOURCE_GROUP=rg-something-else ./infra/teardown.sh

set -euo pipefail

RESOURCE_GROUP="${FOUNDRY_RESOURCE_GROUP:-rg-foundry-skeptic}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/code/.env"

if ! command -v az > /dev/null 2>&1; then
    echo "ERROR: Azure CLI not found."
    exit 1
fi

if ! az account show > /dev/null 2>&1; then
    echo "ERROR: Not signed in. Run: az login"
    exit 1
fi

if [ "$(az group exists --name "$RESOURCE_GROUP")" != "true" ]; then
    echo "Resource group '$RESOURCE_GROUP' does not exist. Nothing to do."
    exit 0
fi

SUBSCRIPTION=$(az account show --query name --output tsv)
SUB_ID=$(az account show --query id --output tsv)

# Record what deleting the group will NOT fully remove, before it is gone and
# can no longer be listed.
#
# 1. Foundry accounts are SOFT-deleted and held for 48 hours. Until they are
#    purged, nothing new can be created with the same name -- and setup.sh
#    always uses the same name, so a rebuild inside two days would fail.
FOUNDRY_ACCOUNTS=$(az cognitiveservices account list --resource-group "$RESOURCE_GROUP" \
    --query "[].[name, location]" --output tsv 2>/dev/null || true)
# 2. Managed resource groups that resources in this group created elsewhere.
#    Workspace-based Application Insights puts its Log Analytics workspace in
#    one, outside this group.
MANAGED_RGS=$(az group list \
    --query "[?managedBy && contains(managedBy, '/resourceGroups/${RESOURCE_GROUP}/')].name" \
    --output tsv 2>/dev/null || true)

# Show exactly what is about to be destroyed, rather than asking the user to
# take it on faith.
echo ""
echo "About to DELETE this resource group and everything in it."
echo ""
echo "  Subscription:   $SUBSCRIPTION"
echo "  Resource group: $RESOURCE_GROUP"
echo ""
echo "Contents:"
az resource list --resource-group "$RESOURCE_GROUP" \
    --query "[].{Name:name, Type:type}" --output table 2>/dev/null || echo "  (unable to list)"
if [ -n "$MANAGED_RGS" ]; then
    echo ""
    echo "Also outside the group, created by resources in it (removed if Azure leaves them):"
    echo "$MANAGED_RGS" | sed 's/^/  /'
fi
if [ -n "$FOUNDRY_ACCOUNTS" ]; then
    echo ""
    echo "Foundry accounts to PURGE afterwards, skipping the 48-hour recovery window:"
    echo "$FOUNDRY_ACCOUNTS" | awk '{print "  " $1 " (" $2 ")"}'
fi
echo ""
echo "This cannot be undone."
echo ""

printf 'Type the resource group name to confirm: '
read -r CONFIRM

if [ "$CONFIRM" != "$RESOURCE_GROUP" ]; then
    echo "Input did not match. Nothing deleted."
    exit 1
fi

echo ""
echo "Deleting '$RESOURCE_GROUP'. This usually takes several minutes."
az group delete --name "$RESOURCE_GROUP" --yes --no-wait

# Wait for it: the purge below only works once the account is actually gone.
DELETED=0
for i in $(seq 1 120); do
    if [ "$(az group exists --name "$RESOURCE_GROUP" 2>/dev/null)" = "false" ]; then
        DELETED=1
        break
    fi
    [ $((i % 4)) -eq 0 ] && echo "    still deleting ($((i * 15 / 60)) min)..."
    sleep 15
done

if [ "$DELETED" -ne 1 ]; then
    echo ""
    echo "Still deleting after 30 minutes. Once 'az group exists --name $RESOURCE_GROUP'"
    echo "reports false, re-run this script's cleanup by hand:"
    echo "$FOUNDRY_ACCOUNTS" | while read -r NAME LOC; do
        [ -n "$NAME" ] && echo "  az resource delete --ids /subscriptions/$SUB_ID/providers/Microsoft.CognitiveServices/locations/$LOC/resourceGroups/$RESOURCE_GROUP/deletedAccounts/$NAME"
    done
    echo "$MANAGED_RGS" | while read -r G; do [ -n "$G" ] && echo "  az group delete --name $G --yes"; done
    exit 1
fi
echo "    Resource group deleted."

# Purge the soft-deleted Foundry accounts so their names are free again. Needs
# Contributor (or Owner) at SUBSCRIPTION scope, per Microsoft's docs.
if [ -n "$FOUNDRY_ACCOUNTS" ]; then
    echo ""
    echo "Purging soft-deleted Foundry accounts..."
    echo "$FOUNDRY_ACCOUNTS" | while read -r NAME LOC; do
        [ -z "$NAME" ] && continue
        PURGE_ID="/subscriptions/$SUB_ID/providers/Microsoft.CognitiveServices/locations/$LOC/resourceGroups/$RESOURCE_GROUP/deletedAccounts/$NAME"
        PURGED=0
        # The deleted account can take a moment to become purgeable.
        for attempt in 1 2 3 4 5 6; do
            if az resource delete --ids "$PURGE_ID" --output none 2>/dev/null; then
                PURGED=1
                break
            fi
            sleep 20
        done
        if [ "$PURGED" -eq 1 ]; then
            echo "    Purged $NAME. The name can be reused immediately."
        else
            echo "    WARNING: could not purge $NAME. It frees itself after 48 hours, or retry with:"
            echo "      az resource delete --ids $PURGE_ID"
        fi
    done
fi

# Managed groups: Azure usually removes these with their parent; delete any it left.
if [ -n "$MANAGED_RGS" ]; then
    echo ""
    echo "Checking managed resource groups..."
    echo "$MANAGED_RGS" | while read -r G; do
        [ -z "$G" ] && continue
        if [ "$(az group exists --name "$G" 2>/dev/null)" = "true" ]; then
            az group delete --name "$G" --yes --no-wait
            echo "    $G was left behind; deletion started."
        else
            echo "    $G was removed with its parent."
        fi
    done
fi

# The generated .env now points at resources that are going away. Leaving it in
# place makes the next run fail confusingly.
if [ -f "$ENV_FILE" ] && grep -q 'Generated by infra/setup.sh' "$ENV_FILE" 2>/dev/null; then
    mv "$ENV_FILE" "$ENV_FILE.stale"
    echo ""
    echo "Moved the generated code/.env to code/.env.stale (it points at deleted resources)."
fi
