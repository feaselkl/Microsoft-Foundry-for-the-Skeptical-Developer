# Demo 4 &mdash; Agents

**Talk section:** 4. Agents: The Actual Product (14 min)

The longest demo in the talk, because it carries the thesis: Foundry is an agent
platform now, and everything else is in service of that.

## The Scenario

The agent **audits Microsoft Foundry's own feature lifecycle** &mdash; what is GA, what
is preview, what is retired, what is stranded in the classic portal.

That choice is doing real work. The room is never learning a toy domain and a product
at the same time. The tool has an answer attendees can check. And it produces the line
that ties section 4 back to section 1:

> **Prompt Flow: RETIRED. Full retirement 2027-04-20. Replacement: Microsoft Agent Framework.**

The agent tells the room the thing the talk opened with. Let it land.

## The Arc

### 1. A prompt agent, nothing attached

`prompt_agent.py` &mdash; instructions, a model, a two-turn conversation. No code, no
container, no scaling. Build it in the portal first, then run the script to show that
portal-first and code-first produce the same object.

### 2. The same agent, plus one tool &mdash; **this is the demo**

`agent_with_mcp.py` builds two agents with **identical model and identical instructions**.
One has no tools; one has the feature registry attached. Both get:

> "Should I build my RAG pipeline on Prompt Flow?"

The tool-less agent answers from training data and sounds reasonable either way &mdash;
which is the point, because the room cannot tell from the answer whether it is right.
The tool-equipped agent returns a retirement date.

Say *before* running it that the only difference is the tool, or the contrast reads as luck.

What a tool buys is not "the agent can do more things." It is **the agent stops guessing
about things it cannot know.**

### 3. Curate a toolbox

`create_toolbox.py`. Step 2 wired the server to one agent, which does not scale: every
agent carries its own URL, approval policy, and auth config.

A toolbox curates once behind a single managed MCP endpoint. Show the two endpoints it
prints &mdash; *consumer* always serves the default version, so promoting updates every
agent without redeploying; *developer* is pinned, for validating before you promote.

**Then the fine print, which is the best skeptic moment in the section.** Toolbox tools
carry `require_approval`. Set it to `always` and you would expect the platform to stop
the call. It does not: per the docs, the toolbox MCP endpoint does not block
`tools/call`, and *your runtime* must enforce it. A system-prompt instruction is not
enforcement. The feature is real and the docs are honest about it &mdash; you would just
never learn it from the marketing.

### 4. The hosted agent, on Microsoft Agent Framework

`hosted_agent/main.py`. Our code, running on Foundry's managed runtime with an endpoint,
autoscale, and its own Entra identity. `deploy_hosted_agent.py` zips the source, uploads
it, Foundry builds it remotely, then routes 100% of endpoint traffic to the new version.

Two things to point at on screen:

- **`FoundryToolbox(credential)` &mdash; there is no server URL in the file.** The toolbox
  arrives by name. Promote a toolbox version and this agent picks it up with no redeploy.
  That is the payoff for step 3.
- **`assess_adoption_risk` is a plain dict and a function.** "Retired means BLOCK" is not
  a sentence in a prompt the model might reinterpret. It is code, it is testable, it
  returns the same verdict every run. That is what the full-code end buys you.

Then the section 6 seed: apart from two imports, this is an Agent Framework agent. It
would run elsewhere.

The traffic-percentage rule in the deploy script is worth a sentence too &mdash; it is how
you canary. Two versions, 90/10, watch the traces.

## Build

```bash
./infra/setup.sh                 # resource group, Foundry resource, project, model
./infra/deploy-mcp-server.sh     # feature registry -> Container Apps

cd code
uv run python demos/04_agents/create_toolbox.py

cd .. && ./infra/deploy-hosted-agent.sh   # zip, remote build, route traffic
```

**Deploy the hosted agent the morning of the talk, not during it.** The remote build takes
minutes. On stage you run `invoke_hosted_agent.py`, never `deploy_hosted_agent.py`.

## Run On Stage

```bash
cd code
uv run python demos/04_agents/prompt_agent.py        # 1
uv run python demos/04_agents/agent_with_mcp.py      # 2  <- the one that matters
uv run python demos/04_agents/create_toolbox.py      # 3
uv run python demos/04_agents/invoke_hosted_agent.py # 4
```

## Contents

| Path | What it is |
| --- | --- |
| `prompt_agent.py` | Step 1: bare prompt agent |
| `agent_with_mcp.py` | Step 2: the with/without contrast |
| `create_toolbox.py` | Step 3: curate and version the tool set |
| `mcp_server/` | Feature registry MCP server, containerized |
| `mcp_server/features.json` | The curated lifecycle data |
| `hosted_agent/main.py` | Step 4: Agent Framework agent + FoundryToolbox |
| `deploy_hosted_agent.py` | Zip, upload, remote build, route traffic |
| `invoke_hosted_agent.py` | Talk to the deployed agent (use this on stage) |

## Still To Do

- [x] **Verify the mixed `tools` list.** Deployed with `deploy-hosted-agent.sh` and invoked with
      `invoke_hosted_agent.py` on 2026-10-16 without error, so Agent Framework accepts
      `tools=[toolbox, assess_adoption_risk]`. A `VERDICT:` line in the reply is the sign the
      local policy function ran.
- [x] Steps 1 to 4 all run: `prompt_agent.py`, `agent_with_mcp.py`, `create_toolbox.py`,
      `invoke_hosted_agent.py` (2026-10-16).
- [ ] Rehearse the step 1 &rarr; step 2 transition. That is where a 14-minute section drags.

## Stage Risks

- **`features.json` is dated.** Verified 2026-09-19, re-checked 2026-10-16, same watch list as the planning notes.
  The re-check found managed compute and fine-tuning had left the classic portal, which
  had made two of the twelve demo-5 questions wrong in the registry itself.
  A demo telling the room stale facts *about staleness* is the worst possible failure here.
  Re-verify before every delivery.
- **The tool-less answer is not deterministic.** The model may hedge, be confidently wrong,
  or happen to know. All three make the point; rehearse framing for each. If it gets it
  right: *"It guessed well. It still guessed, and it cannot tell you which of its answers
  are guesses."*
- **Remote build takes minutes and can fail late.** `main.py` and `requirements.txt` must
  be at the **root** of the zip; the deploy script checks and refuses otherwise. Deploy the
  morning of, and keep the previous version routed until the new one is active.
- **Deploying needs `Foundry Project Manager` at project scope.** The agent's own identity
  is issued by Foundry, so there is nothing to assign for the agent itself.
- **Scope creep.** Agent *design* belongs to "Build an Agent, Not a Chatbot." Keep this
  about hosting, tooling, and governance.
