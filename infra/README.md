# Demo Environment

Scripts to build and tear down the Azure resources the demos need.

## The Scripts

| Script | Builds |
| --- | --- |
| `setup.sh` | Resource group, Foundry resource, project, model deployment, Application Insights |
| `deploy-mcp-server.sh` | The demo-4 feature registry MCP server, on Container Apps |
| `deploy-hosted-agent.sh` | The demo-4 hosted agent, on Foundry Agent Service |
| `teardown.sh` | Deletes everything |

Run them in that order. `deploy-hosted-agent.sh` also needs the toolbox to exist:

```bash
./infra/setup.sh
./infra/deploy-mcp-server.sh
(cd code && uv run python demos/04_agents/create_toolbox.py)
./infra/deploy-hosted-agent.sh
```

**Deploy the hosted agent the morning of the talk.** Foundry builds it remotely and that
takes minutes, not seconds.

## What `setup.sh` Creates

| Resource | Purpose | Demo |
| --- | --- | --- |
| Resource group | Holds everything, so teardown is one command | all |
| Foundry resource (`AIServices`, S0) | The account, with project management enabled | all |
| Project | The thing the SDK connects to | all |
| Model deployment (`gpt-5-mini`, GlobalStandard) | A model to call by deployment name | 2, 3, 4, 5 |
| Application Insights | Trace destination | 5 |

`deploy-mcp-server.sh` adds a Container Apps environment and the MCP server.
`deploy-hosted-agent.sh` adds a hosted agent version inside the Foundry project itself,
so there is no separate compute resource for it &mdash; Foundry runs it.

It then writes `code/.env` with the project endpoint and deployment name, so the
demo scripts run without further configuration.

## Prerequisites

- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) **2.80.0 or later**.
  The `az cognitiveservices account project` commands do not exist before that, and the
  failure mode on an older CLI is a confusing `unrecognized arguments`. The script checks.
- **Contributor** or **Owner** on the resource group.
- For a subscription that has not used these services before, enough rights to register
  resource providers — see below.
- Signed in: `az login`

## Resource Providers

Azure resource providers are registered **per subscription**, and a fresh subscription has
most of them switched off. Creating a resource under an unregistered namespace fails with:

```
(MissingSubscriptionRegistration) The subscription is not registered to use
namespace 'Microsoft.CognitiveServices'
```

which tells you nothing about how to fix it. The scripts register what they need up front
instead, via `ensure_providers` in [`_lib.sh`](_lib.sh):

| Script | Registers |
| --- | --- |
| `setup.sh` | `Microsoft.CognitiveServices`, `Microsoft.Insights`, `Microsoft.OperationalInsights` |
| `deploy-mcp-server.sh` | `Microsoft.App`, `Microsoft.OperationalInsights`, `Microsoft.ContainerRegistry` |
| `deploy-hosted-agent.sh` | verifies `Microsoft.CognitiveServices`, `Microsoft.ContainerRegistry` |

It checks state before registering, so it costs nothing once they are on. First run on a
new subscription can take a few minutes per provider.

### The data-plane trap

This one catches everyone exactly once, and it produces **HTTP 403 with an empty
response body** — no message, no hint.

`Owner` is `actions: ["*"]` with `dataActions: []`. So is `Contributor`. Those are
**control-plane** roles: they let you create, configure and delete a Foundry resource, and
they do not let you make a single inference call against it. Verify for yourself:

```bash
az role definition list --name Owner --query "[0].permissions[0].dataActions"
# []
```

Calling the project endpoint needs a role granting `Microsoft.CognitiveServices/*` as a
**data** action. All three Foundry roles do:

| Role | GUID |
| --- | --- |
| Foundry User | `53ca6127-db72-4b80-b1b0-d745d6d5456d` |
| Foundry Project Manager | `eadc314b-1a2d-4efa-be10-5d325db5065e` |
| Foundry Owner | `c883944f-8b7b-4483-af10-35834be79c4a` |

`setup.sh` assigns **Foundry Project Manager** at account scope, because it grants the data
actions *and* `accounts/projects/*`, which the demo-4 hosted agent deploy needs. Referenced
by GUID because these roles were renamed recently and the old names still appear in places.

There is **no API key fallback** — the project client is Entra-only. So this is not a
degraded-mode problem; nothing works until the role is right.

`setup.sh` then makes a real inference call before declaring success. If provisioning
succeeds but the call does not, it says so instead of leaving you to find out inside a demo.

**Budget time for propagation.** Azure RBAC is eventually consistent, and measured on this
setup the first successful call came **5 minutes 12 seconds** after `az role assignment
create` returned. The script waits up to 10 minutes after a fresh assignment, and only 2
when the role was already there — because in that case a 403 means something else is wrong
and there is no point waiting. Either way, do not run `setup.sh` five minutes before you
need a working demo.

### The permissions trap

Registering a provider needs rights on the **subscription**. Creating resources only needs
them on the **resource group**. You can have enough access to run everything else in
`setup.sh` and still fail at this line — and no amount of resource-group permission fixes
it.

If that happens, the script says so and prints the command for someone with subscription
access to run. Or do it in the portal under **Subscriptions → your subscription →
Settings → Resource providers**.

## Usage

```bash
./infra/setup.sh
```

Re-running is safe. Every step checks for the resource before creating it, so you can
run it again after a partial failure without cleaning up by hand.

### Overrides

Every setting is an environment variable:

```bash
FOUNDRY_LOCATION=eastus \
FOUNDRY_RESOURCE_GROUP=rg-my-demo \
FOUNDRY_MODEL_NAME=gpt-5-mini \
./infra/setup.sh
```

| Variable | Default |
| --- | --- |
| `FOUNDRY_LOCATION` | `westus3` |
| `FOUNDRY_RESOURCE_GROUP` | `rg-foundry-skeptic` |
| `FOUNDRY_RESOURCE_NAME` | `foundry-skeptic-<user>` |
| `FOUNDRY_PROJECT_NAME` | `proj-foundry-skeptic` |
| `FOUNDRY_MODEL_NAME` | `gpt-5-mini` |
| `FOUNDRY_DEPLOYMENT_NAME` | `gpt-5-mini` |
| `FOUNDRY_SKU_NAME` | `GlobalStandard` |
| `FOUNDRY_SKU_CAPACITY` | `100` |
| `FOUNDRY_APP_INSIGHTS_NAME` | `appi-foundry-skeptic` |
| `FOUNDRY_ACA_ENVIRONMENT` | `aca-foundry-skeptic` |
| `FOUNDRY_MCP_APP_NAME` | `mcp-feature-registry` |
| `FOUNDRY_HOSTED_AGENT_NAME` | `skeptic-assessor` |
| `FOUNDRY_TOOLBOX_NAME` | `skeptic-tools` |

### Why West US 3 by default

Instant access — the no-deployment demo in section 3 — is limited to **West US 3**
during preview. Deploy anywhere else and `instant_access.py` fails while
`deployed_call.py` keeps working, which is a confusing five minutes to debug on stage.
The script warns if you override it.

If that regional limit lifts, this default stops mattering. It is on the watch list in
the talk's Notion page.

## Application Insights Connection

Creating an Application Insights resource is not enough. Foundry only sends traces there,
and the SDK only finds it, once it is a **connection** on the project. `setup.sh` creates
it, following Microsoft's own template
([`connection-application-insights.bicep`](https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/01-connections)):

- An `AppInsights` connection on the Foundry account and on the project, keyed with the
  Application Insights connection string. It is sent as ARM `PUT`s through `az rest`, because
  the `--file` format for `az cognitiveservices account project connection create` is not
  documented.
- **Log Analytics Reader** and **Privileged Monitoring Data Reader** on Application Insights,
  for the project's managed identity (so evaluation can read traces) and for you (so you can
  view them). The second is a data-plane role, the same trap as `Owner` on the Foundry
  resource: Owner can manage Application Insights but cannot read the GenAI content in a
  trace without it.

It also grants the project's managed identity **Foundry User** on the Foundry account.
Continuous evaluation runs as the project rather than as you, and Microsoft's sample makes this
role a prerequisite.

A project allows only one Application Insights connection. If it is already connected to a
different one, the script leaves it alone and says so.

If you ever need the portal route instead: **Manage** (upper right) → **Project details** →
**Connected resources** → **Add connection** → **Application Insights**. The documented
*Agents → Traces → Connect* path did not match the portal on 2026-10-16.

## Teardown

```bash
./infra/teardown.sh
```

Deletes the whole resource group. It lists the contents first and requires you to type
the resource group name to confirm. It then **waits** for the deletion to finish, usually
several minutes, because two clean-up steps depend on it:

- **Purging the Foundry account.** Azure soft-deletes Foundry accounts and blocks the name
  for 48 hours. `setup.sh` always uses the same name, so without a purge a rebuild within two
  days fails. Purging needs Contributor or Owner at subscription scope.
- **Removing managed resource groups.** Application Insights keeps its Log Analytics workspace
  in a separate managed group outside the resource group. Azure usually removes it with its
  parent; the script deletes it if Azure did not.

**Run this after every delivery.** The model deployment is pay-per-token, so idle
inference is cheap, but the resource and Application Insights ingestion are not free.
A forgotten demo environment is a monthly line item you will not notice for a year.

Teardown also renames the generated `code/.env` to `code/.env.stale`, since it would
otherwise point at deleted resources and make the next run fail in a confusing way.

## Rebuild Cadence

Rebuild from scratch rather than reusing a months-old environment before each delivery.
Both the platform and the model versions move, and a stale environment hides breakage
that will surface on stage instead. The script asks the region which model version it
currently has rather than hard-coding one, so a rebuild picks up the current version
automatically.
