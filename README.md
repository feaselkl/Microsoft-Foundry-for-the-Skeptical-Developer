# Microsoft Foundry for the Skeptical Developer

This repository provides the slides and supporting code for my presentation entitled [Microsoft Foundry for the Skeptical Developer](https://www.catallaxyservices.com/presentations/microsoft-foundry-for-the-skeptical-developer/).

## What's in the Box

An honest evaluation of Microsoft Foundry: what it does well, where it falls short, and whether it is worth your team's time. Four demos, each mapped to a section of the talk.

| # | Demo | What it shows | Code |
| --- | --- | --- | --- |
| **2** | Platform basics | Create a project, navigate the portal, make one model call with the unified SDK | [02_platform](code/demos/02_platform/) |
| **3** | Model catalog | Deploy from the catalog and hit the endpoint, then do the same with instant access and no deployment | [03_catalog](code/demos/03_catalog/) |
| **4** | Agents | A prompt agent answering from training data vs. the same agent with an MCP tool, then a toolbox and a containerized hosted agent | [04_agents](code/demos/04_agents/) |
| **5** | Observability | Trace a run end to end, then score demo 4's two agents against the same rubric to measure what the anecdote showed | [05_observability](code/demos/05_observability/) |

## Audience

Developers, architects, and tech leads deciding whether to build on Foundry. The talk assumes you can read Python and know what an LLM API call does. It does **not** assume prior experience with Foundry, Azure ML, or any agent framework. Familiarity with Azure OpenAI is helpful but not required.

## Building the Demo Environment

Three scripts, run in order. All are safe to re-run.

```bash
./infra/setup.sh                              # Foundry resource, project, model, App Insights
./infra/deploy-mcp-server.sh                  # demo-4 MCP server -> Container Apps
(cd code && uv run python demos/04_agents/create_toolbox.py)
./infra/deploy-hosted-agent.sh                # demo-4 agent -> Foundry Agent Service
```

`setup.sh` writes `code/.env` for you. Deploy the hosted agent **the morning of the talk** —
Foundry builds it remotely and that takes minutes.

Tear it down after every delivery with [`infra/teardown.sh`](infra/teardown.sh). See [infra/README.md](infra/README.md) for overrides, the Application Insights connection, and why the default region is West US 3.

## Running the Code

See [code/README.md](code/README.md) for full setup and usage.

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/), [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.80+, and an Azure subscription.

```bash
./infra/setup.sh     # provisions Azure resources, writes code/.env
cd code
uv sync
uv run python demos/02_platform/first_call.py
```

## Cost Model

[`pricing/index.html`](pricing/index.html) is an interactive cost model for the section-6
pricing slide: a help desk agent for a 2,000-person company, with sliders for headcount,
ticket volume, self-service rate, and hosted-agent sizing.

Self-contained and offline-safe, because it runs on conference wifi. Every rate comes from
the public Azure Retail Prices API; re-pull before each delivery with
`python3 pricing/refresh-prices.py`. See [pricing/README.md](pricing/README.md) for the
base case, the three slider moves worth showing, and what is deliberately not modelled.

## Slides

The deck is [index.html](index.html), built on [reveal.js](https://revealjs.com/). It is deployed automatically to <https://www.catallaxyservices.com/media/Microsoft-Foundry-for-the-Skeptical-Developer/> on every push to `main` via [.github/workflows/deploy-slides.yml](.github/workflows/deploy-slides.yml).

To view the slides locally, this repository expects `reveal.js-6` and `WebsiteAssets` as sibling directories.

## A Note on Currency

This platform changes quickly. Between the first draft of this talk and the current version, Microsoft renamed the product twice, split the portal in two, replaced the Assistants API with the Responses API, and retired Prompt Flow outright.

The **Before We Start** slide carries a date. Check that it is current before every delivery, and re-verify the claims in the talk against [Microsoft Learn](https://learn.microsoft.com/azure/foundry/) before each submission. Session planning notes, including a watch list of features still in preview, live in the talk's Notion page.
