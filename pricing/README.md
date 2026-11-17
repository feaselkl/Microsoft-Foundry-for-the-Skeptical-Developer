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
| Web grounding | $65.02 | 49% |
| Container compute (0.5 vCPU, 1 GiB, 24/7) | $48.52 | 37% |
| Model tokens, gpt-6-luna (input + cached + output) | $9.54 | 7% |
| Code interpreter | $9.29 | 7% |
| File search storage | $0.30 | &lt;1% |
| Tracing &rarr; Log Analytics | $0.12 | &lt;1% |
| Embeddings | $0.04 | &lt;1% |
| **Total with hosted agent** | **$132.83** | **$0.066/employee** |
| Total without hosted agent | $84.31 | $0.042/employee |

**The model is 7% of the bill.** Web search costs nearly seven times what the model does,
and code interpreter costs about the same as the model. That is the slide's punchline, and it
is the opposite of what most people budget for.

## Model Choice

The model dropdown swaps the chat model with every other input held constant:

| Model | Model cost | Total (with hosted agent) | Model share |
| --- | ---: | ---: | ---: |
| **gpt-6-luna** (default) | **$9.54** | **$132.83** | **7%** |
| gpt-5-mini | $30.97 | $154.26 | 20% |
| gpt-5.4-mini | $78.66 | $201.95 | 39% |
| gpt-6.1-sol | $187.77 | $311.07 | 60% |

Two things to say about it. Price does not track recency: gpt-6-luna is one of the newest
models here and the cheapest, while gpt-5.4-mini, six months older, costs eight times as much
for this workload. And "the model is the cheap part" holds for small models and stops holding
for frontier ones, which is the honest version of the claim.

gpt-6-luna is the default because it is what the demo environment deploys and what the
section-6 slide quotes. (gpt-5-mini, the previous default, retires 2027-07-13 per the Learn
model retirement schedule.)

## Three Things To Show On Stage

1. **2,000 &rarr; 2,400 employees:** $133 &rarr; $150. Linear and boring, which is the point.
2. **3 &rarr; 5 tickets per employee:** $133 &rarr; $189. Volume hurts more than headcount.
3. **Self-service 35% &rarr; 70%:** $133 &rarr; **$123. It goes down.** Deflection removes a
   ticket, which removes its triage, its research pass, and its web search calls. The
   feature that looks like added cost is a net saving.

Let the room notice the third one before explaining it.

Then scale the hosted agent to 4 replicas at 2 vCPU / 4 GiB: **$861/month**, where compute
($776) is 90% of the bill &mdash; and still identical at zero tickets. That is the concrete
argument for starting with the Responses API instead of a hosted agent.

## Prices

Every rate comes from the public
[Azure Retail Prices API](https://prices.azure.com/api/retail/prices), pulled
**2026-10-11** and re-verified unchanged **2026-11-17**, USD, Global Standard deployment where a choice exists. No auth, no
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
| `modelIn` | $0.10 / 1M | `6-luna ShortCo Inp Std Gl 1M Tokens` |
| `modelCached` | $0.01 / 1M | `6-luna ShortCo Cd Inp Std Gl 1M Tokens` |
| `modelOut` | $0.50 / 1M | `6-luna ShortCo Opt Std Gl 1M Tokens` |
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
- **Prompt cache writes** &mdash; GPT-5.6 and later bill them on their own meter
  (`6-luna ShortCo Cd Wr Std Gl 1M Tokens`, $0.125 per 1M, against $0.10 for fresh input).
  At most that adds a quarter to the fresh-input line: about $1/month at the base case.

## A Note On The Token Assumptions

The rates are facts. The token counts per operation are **estimates**, and they are the
largest source of error in the total. They live in the collapsible *Per-operation
assumptions* panel precisely so that someone who disagrees can change them on stage
rather than argue about them.

If challenged: the defensible claim is not "your bill will be $154." It is "the model is
not the expensive part, and a 24/7 container is a fixed floor." Both survive wide
variation in the token estimates.
