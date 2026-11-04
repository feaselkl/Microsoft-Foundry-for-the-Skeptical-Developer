# Demo 5 &mdash; Observability

**Talk section:** 5. Observability: Where Foundry Earns Its Keep (11 min)

## The Point

This is the part of the product you would actually pay for, and the one the keynotes
undersell. Forty minutes of honest criticism is what earns this section its credibility:
when the talk says something is genuinely good, the room believes it.

The section has an arc of its own. **Demo 4 made an argument with one anecdote. This
section turns it into a number.**

## The Arc

### 1. Trace one run

`trace_agent.py` instruments the agent, runs it, and exports to Application Insights.
Walk one request end to end: the model call, the tool invocations, the custom function.

The point to land: **tracing is OpenTelemetry.** These spans would go to Datadog, Grafana
Tempo, Jaeger, or Honeycomb just as readily. That is why it also covers agents you did
not build in Foundry &mdash; and it is the most concrete evidence in the talk that
lock-in really is low at the framework layer.

### 2. Measure what demo 4 only showed

`evaluate.py` takes the two agents from demo 4 &mdash; identical model, identical
instructions, one with the feature registry and one without &mdash; and scores both
against the same twelve questions with the same rubric.

That progression is the argument of the section:

> A demo is an anecdote. Evaluation is what turns an anecdote into something you can put
> in a pull request.

Mechanically it does four things worth narrating:

- **Uploads a dataset.** Twelve questions, small enough to finish while you talk.
- **Generates a rubric from the agent's own context** &mdash; its name, instructions, and
  tools. Print the dimensions on stage. Seeing the judge's criteria is what stops
  evaluation from looking like one black box scoring another.
- **Creates one evaluation, runs it twice.** The evaluation is a *container*: every run
  under it shares a schema and produces the same metrics. That shared schema is the
  entire reason the two scorecards are comparable, and it is worth saying out loud.
- **Maps `response` to `{{sample.output_items}}`, not `{{sample.output_text}}`**, so the
  judge sees the tool calls and can tell whether the agent looked anything up at all.

### 3. Continuous evaluation

Same evaluators, pointed at sampled production traffic, writing scores into Application
Insights next to the traces. Evaluate and trace become two views of one event, and the
loop from "quality problem detected" to "problem diagnosed" closes without leaving the
tool. **That is the actual differentiator.**

**Show a screenshot, not a live demo.** Continuous evaluation scores live traffic, and a
conference room has none. `continuous_eval.py` makes the traffic for the screenshot: it creates
an evaluation over the agent's responses (Coherence and Violence) and a rule that runs it on
every completed `SkepticWithRegistry` response, then sends the twelve demo-5 questions through
the agent as twelve separate conversations.

Take the screenshot at **Build → open `SkepticWithRegistry` → Monitor**: evaluation scores
beside token usage, latency and run success, all from the same traffic. Optionally a second
one at **Build → Evaluations → Recurring Configs**, showing the rule itself. Charts can lag
the runs by a few minutes.

The rule runs as the project, not as you, so the project's managed identity needs
**Foundry User**. `infra/setup.sh` grants it; allow a few minutes after a fresh grant.

## Build and Run

```bash
./infra/setup.sh
./infra/deploy-mcp-server.sh

cd code
uv run python demos/04_agents/agent_with_mcp.py    # creates both agents
uv run python demos/05_observability/trace_agent.py
uv run python demos/05_observability/evaluate.py                  # first run: generates the rubric
uv run python demos/05_observability/evaluate.py --reuse-rubric   # later runs: skips that step
```

Every step prints its elapsed time, with a timing summary at the end, so one rehearsal run
shows where the minutes go. The rubric is saved in the project, so on stage use
`--reuse-rubric` (newest saved rubric) or `--rubric NAME` (a specific one).

## Contents

| Path | What it is |
| --- | --- |
| `trace_agent.py` | Instrumented run, custom function span, App Insights export |
| `evaluate.py` | Rubric generation, one evaluation, two runs, side-by-side scorecards |
| `continuous_eval.py` | Continuous evaluation rule plus generated traffic, for the Monitor screenshot |
| `eval_data/foundry_questions.jsonl` | Twelve lifecycle questions the registry can answer |

## Still To Do

- [x] **Run `evaluate.py` once end to end and time it.** Done 2026-10-16; results under
      *First Full Run* below. At 11m36s it does not fit live in an 11-minute section.
- [x] **Re-run after raising the deployment's capacity** to 100, with `--reuse-rubric`.
      Done 2026-10-16: zero errors, about 2.5 minutes. Results under *Second Run* below.
- [x] Decide live demo vs. screenshot for continuous evaluation: screenshot, made with
      `continuous_eval.py`.
- [ ] Optional: instrument a non-Foundry agent via OTel to prove the framework-agnostic
      claim rather than asserting it.

## First Full Run (2026-10-16)

| Step | Time |
| --- | ---: |
| Upload dataset | 2s |
| Generate rubric | 1m 14s |
| Run: SkepticNoTools | 9m 25s |
| Run: SkepticWithRegistry | 10m 08s |
| **Total** | **11m 36s** |

| Lifecycle Accuracy (rubric) | Passed | Failed | Errored |
| --- | ---: | ---: | ---: |
| SkepticNoTools | 6 | 4 | 2 |
| SkepticWithRegistry | 5 | 2 | 5 |

Coherence passed 12 of 12 for **both** agents, the outcome the speaker notes predict:
coherence measures whether an answer reads well, not whether it is true, so it cannot tell
the two agents apart.

**Every errored row was HTTP 429** from `gpt-5-mini`. The agents and both judges share one
deployment, which `setup.sh` created at capacity 10, meaning 10 requests and 10,000 tokens a
minute. The tools agent errored more because its answers carry tool output and use more
tokens. Throttling and retries probably account for much of the run time too, so the times
above are likely pessimistic.

**Do not quote these as the result.** With 7 of 24 rubric scores missing, the comparison is
noise: of the rows that did score, the tools agent passed 5 of 7 and the bare agent 6 of 10.
Re-run after the capacity change. If the gap is still small, the generated rubric may not
reward lifecycle accuracy specifically, and a hand-written rubric would make the point
more directly.

## Second Run (2026-10-16): capacity 100, `--reuse-rubric`

| Run | Time | Rubric passed | Rubric failed | Errored |
| --- | ---: | ---: | ---: | ---: |
| SkepticNoTools | 2m 14s | 7 | 5 | 0 |
| SkepticWithRegistry | 2m 28s | **11** | 1 | 0 |

Coherence passed 12 of 12 for both agents again.

This is the result to show: **11 of 12 with the tool, 7 of 12 without**, while a fluency judge
scores them identically. With the rubric reused it fits live in the section: about two and a
half minutes of waiting, which you can fill by walking through a trace. LLM judges vary run to
run, so expect the numbers to move a little on stage; the size of the gap is the point.

## Stage Risks

- **Trace ingestion lag is 2&ndash;5 minutes**, per the docs. Run `trace_agent.py` at the
  *start* of the section and come back to it, or have a trace already populated.
- **Application Insights must be connected to the project.** `infra/setup.sh` now does this
  (connection plus read roles). If traces are missing on the day, re-run it; it skips what already
  exists.
- **Evaluations cost tokens and take minutes.** Keep the dataset small. Have a completed
  run saved to fall back on.
- **Rubric generation has regional restrictions**, along with synthetic dataset creation
  and the risk/safety evaluators. Verify yours works in the demo region before you rely
  on it.
- **The comparison could come out flat.** If the tool-less agent happens to score well on
  coherence, that is a teaching moment, not a failure: coherence measures whether an
  answer reads well, not whether it is true. Point at the rubric's accuracy dimensions
  instead. Rehearse that line &mdash; it is the difference between a metric and a
  *useful* metric.
- **Do not teach evaluation methodology here.** That belongs to *Trust, but Verify*. This
  demo is about whether Foundry's tooling is worth buying.
