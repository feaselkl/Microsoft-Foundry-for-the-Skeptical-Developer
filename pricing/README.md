# Cost Model &mdash; Help Desk Agent on Foundry

An interactive cost model for section 6. Open [`index.html`](index.html) and move the
sliders.

Self-contained: no CDN, no build step, no network at runtime. That is deliberate &mdash;
it has to work on conference wifi.

## The Scenario

A help desk agent for a moderately large company, mirroring the app in the
*Practical AI Integration* repo. Four features on one agent:

1. **Triage** &mdash; classify and route every new ticket
2. **Knowledge base** &mdash; embeddings over historical tickets, served through file search
3. **Research assist** &mdash; multi-step investigation for resolvers, with web grounding
4. **Self-service chat** &mdash; a multi-turn front door that deflects some tickets entirely

Defaults: 2,000 employees, 3 tickets each per month, 35% start in self-service, 40% of
those resolve without creating a ticket, 60% of remaining tickets get a research pass.

## The Base Case

| Line | Monthly | Share |
| --- | ---: | ---: |
| Web grounding | $65.02 | 42% |
| Container compute (0.5 vCPU, 1 GiB, 24/7) | $48.52 | 31% |
| Model tokens (input + cached + output) | $30.97 | 20% |
| Code interpreter | $9.29 | 6% |
| File search storage | $0.30 | &lt;1% |
| Tracing &rarr; Log Analytics | $0.12 | &lt;1% |
| Embeddings | $0.04 | &lt;1% |
| **Total with hosted agent** | **$154.26** | **$0.077/employee** |
| Total without hosted agent | $105.74 | $0.053/employee |

**The model is 20% of the bill.** Web search costs roughly twice what the model does.
That is the slide's punchline, and it is the opposite of what most people budget for.

## Model Choice

The model dropdown swaps the chat model with every other input held constant:

| Model | Model cost | Total (with hosted agent) | Model share |
| --- | ---: | ---: | ---: |
| gpt-6-luna | $9.54 | $132.83 | 7% |
| **gpt-5-mini** (default) | **$30.97** | **$154.26** | **20%** |
| gpt-5.4-mini | $78.66 | $201.95 | 39% |
| gpt-6.1-sol | $187.77 | $311.07 | 60% |

Two things to say about it. Price does not track recency: gpt-6-luna is the newest model
here and the cheapest, and gpt-5.4-mini costs three times what gpt-5-mini does. And "the model
is the cheap part" holds for small models and stops holding for frontier ones, which is the
honest version of the claim.

gpt-5-mini stays the default because it is what the demo environment deploys and what the
section-6 slide quotes. It retires 2027-02-09, so revisit the default before any delivery
after that.

## Three Things To Show On Stage

1. **2,000 &rarr; 2,400 employees:** $154 &rarr; $175. Linear and boring, which is the point.
2. **3 &rarr; 5 tickets per employee:** $154 &rarr; $225. Volume hurts more than headcount.
3. **Self-service 35% &rarr; 70%:** $154 &rarr; **$150. It goes down.** Deflection removes a
   ticket, which removes its triage, its research pass, and its web search calls. The
   feature that looks like added cost is a net saving.

Let the room notice the third one before explaining it.

Then scale the hosted agent to 4 replicas at 2 vCPU / 4 GiB: **$882/month**, where compute
is 88% of the bill &mdash; and still identical at zero tickets. That is the concrete
argument for starting with the Responses API instead of a hosted agent.

## Prices

Every rate comes from the public
[Azure Retail Prices API](https://prices.azure.com/api/retail/prices), pulled
**2026-10-11** and re-verified unchanged **2026-10-16**, USD, Global Standard deployment where a choice exists. No auth, no
subscription &mdash; which makes it the honest answer to "where did you get those numbers?"
from the floor, because anyone can check.

Refresh before each delivery:

```bash
python3 refresh-prices.py
```

It prints ready-to-paste `PRICES` and `MODELS` blocks and names any meter that has been
renamed or retired. The API rate-limits with HTTP 429 on a full pull, so the script backs off
and retries, honoring `Retry-After`. A run can take a minute or two because of that. Paste the output over the `PRICES` constant in `index.html` and update the date
in the footer.

| Key | Rate | Meter |
| --- | --- | --- |
| `modelIn` | $0.25 / 1M | `GPT 5 Mini Inpt Glbl 1M Tokens` |
| `modelCached` | $0.025 / 1M | `GPT 5 Mini cchd Inpt Glbl 1M Tokens` |
| `modelOut` | $2.00 / 1M | `GPT 5 Mini outpt Glbl 1M Tokens` |
| `embed` | $0.02 / 1M | `text-embedding-3-small-glbl Tokens` |
| `fileSearch` | $0.10 / GB-day | `Assistants-File Search-glbl GB` |
| `webGrounding` | $14.00 / 1K calls | `Web Grounding Calls` |
| `codeSession` | $0.03 each | `Code-Interpreter-global Session` |
| `vcpuHour` | $0.10934 / vCPU-hour | `Hosted vCPU Usage` |
| `memHour` | $0.0118 / GiB-hour | `Hosted Memory Usage` |
| `logGB` | $2.30 / GB | Log Analytics `Standard Data Analyzed` |

Data Zone deployments run roughly 10% higher than Global. Regional varies.

## Shareable Version

A theme-aware copy lives at <https://claude.ai/artifact/JpCKRm7FhW1wuCSfqU8SHN>, with the same
arithmetic plus one-click presets for the moves above, for people who were not in the room.
It is private until shared from its Share menu. Use the local `index.html` on stage; it needs no
network.

## What Is Not Modelled

Say this if someone asks, because it is the difference between a shape-of-the-bill model
and a quote:

- **Provisioned throughput** &mdash; a capacity reservation, not a per-token rate
- **Agent Commit Units** &mdash; the reserved tiers (20K ACU is $19,000, 100K is $90,000, 500K is $425,000)
- **Managed compute** &mdash; VM core-hours, billed whether you call the model or not
- **Azure AI Search** &mdash; if the knowledge base outgrows file search
- **Log retention** beyond ingestion, and egress

## A Note On The Token Assumptions

The rates are facts. The token counts per operation are **estimates**, and they are the
largest source of error in the total. They live in the collapsible *Per-operation
assumptions* panel precisely so that someone who disagrees can change them on stage
rather than argue about them.

If challenged: the defensible claim is not "your bill will be $154." It is "the model is
not the expensive part, and a 24/7 container is a fixed floor." Both survive wide
variation in the token estimates.
