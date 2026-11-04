# Microsoft Foundry for the Skeptical Developer &mdash; Python Demos

Demo code for the "Microsoft Foundry for the Skeptical Developer" presentation, organized by talk section.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.80 or later
- An Azure subscription, with Contributor or Owner on the resource group

## Setup

Let [`infra/setup.sh`](../infra/setup.sh) build the Azure side. It provisions the resource group, Foundry resource, project, model deployment, and Application Insights, then writes `.env` here with the right values.

```bash
az login
./infra/setup.sh     # from the repo root

cd code
uv sync
```

To configure by hand instead, copy `.env.example` to `.env` and fill it in.

Authentication is **Entra ID only** -- the project client has no API key option, so `az login` is not a convenience, it is the mechanism. If your account spans multiple tenants, pin the subscription first with `az account set --subscription <name>`.

`setup.sh` also connects Application Insights to the project, which demo 5's tracing needs. See [infra/README.md](../infra/README.md#application-insights-connection).

## Demos

Each directory maps to a section of the talk and has its own README with the narrative, the commands to run, and the things that can go wrong on stage.

| Directory | Talk section | Demo |
| --- | --- | --- |
| [demos/02_platform](demos/02_platform/) | 2. What Foundry Is Now | Project structure and a first model call |
| [demos/03_catalog](demos/03_catalog/) | 3. The Model Catalog | Deployment vs. instant access |
| [demos/04_agents](demos/04_agents/) | 4. Agents | Prompt agent, toolbox, hosted agent |
| [demos/05_observability](demos/05_observability/) | 5. Observability | Tracing and evaluation |

## SDK Note

These demos use `azure-ai-projects` 2.x with a single project endpoint, which is the current unified surface. If you are following along from older material, you may have seen `azure-ai-inference`, `azure-ai-generative`, or `azure-ai-ml` against separate endpoints. Those are the previous generation and are not used here.
