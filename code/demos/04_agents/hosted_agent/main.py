"""
Demo 4, step 4 -- the hosted agent, on Microsoft Agent Framework.

This is the full-code end of the spectrum. Steps 1-3 were declarative:
configuration in, agent out, Foundry runs it. This is our code, running on
Foundry's managed runtime with an endpoint, autoscale, and its own Entra
identity.

Two things make this worth the extra work, and both should be said out loud
while this file is on screen:

1. THE TOOLBOX ARRIVES BY NAME. `FoundryToolbox(credential)` resolves the
   endpoint from TOOLBOX_NAME, authenticates every MCP request, and forwards
   the runtime's per-request call id. There is no server URL in this file. Add
   a tool to the toolbox, promote the version, and this agent picks it up
   WITHOUT a redeploy. That is the governance payoff from step 3.

2. THE POLICY IS CODE. `assess_adoption_risk` below is a plain Python function.
   The rule that says "retired means BLOCK" is not a sentence in a prompt the
   model might reinterpret -- it is a dict, it is testable, and it returns the
   same answer every time. That is the thing a declarative agent cannot give
   you, and it is why this step exists.

The wider argument for section 6: apart from two imports, nothing here is
Foundry-shaped. It is an Agent Framework agent. It would run somewhere else.

Entry point contract: the hosted runtime expects `main.py` and
`requirements.txt` at the ROOT of the uploaded zip, and runs `python main.py`.
The server listens on port 8088.
"""

import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryToolbox, ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

# Our policy, not the model's. Change the business rule here, not in a prompt.
RISK_POLICY: dict[str, tuple[str, str]] = {
    "retired": ("BLOCK", "Retired or retiring. Do not start new work here."),
    "replaced": ("BLOCK", "Superseded. Use the replacement."),
    "classic": ("CAUTION", "Stranded in the classic portal. Expect a migration."),
    "preview": ("CAUTION", "Preview. No SLA, and the API may change."),
    "mixed": ("CAUTION", "Partly GA, partly preview. Check the specific version."),
    "ga": ("OK", "Generally available."),
}

INSTRUCTIONS = """\
You help developers decide whether a proposed design is safe to build on.

Your process, in order:
1. For every platform feature the user names, call the feature registry to get
   its lifecycle status. Never guess a status.
2. Pass the statuses you found to assess_adoption_risk to get the verdict.
3. Report the verdict, then list each feature with its risk level and why.

Report what the tools return. Do not soften a BLOCK, and do not invent dates.
If the registry has no entry for something, say so plainly.
"""


def assess_adoption_risk(statuses: str) -> str:
    """Apply the adoption risk policy to a set of feature lifecycle statuses.

    Deterministic. Given the same statuses it returns the same verdict every
    time, which is the point of putting it in code rather than in a prompt.

    Args:
        statuses: Comma-separated "feature=status" pairs, for example
            "Prompt Flow=retired, Toolbox=ga, instant access=preview".
    """
    findings = []
    for pair in statuses.split(","):
        if "=" not in pair:
            continue
        feature, _, status = pair.partition("=")
        feature = feature.strip()
        status = status.strip().lower()
        level, note = RISK_POLICY.get(status, ("UNKNOWN", "Not found in the registry."))
        findings.append((feature, status, level, note))

    if not findings:
        return "No feature statuses supplied. Look each feature up in the registry first."

    blocked = [f for f in findings if f[2] == "BLOCK"]
    caution = [f for f in findings if f[2] == "CAUTION"]

    if blocked:
        verdict = (
            f"DO NOT PROCEED as designed. {len(blocked)} of {len(findings)} "
            "components are retired or superseded."
        )
    elif caution:
        verdict = (
            f"PROCEED WITH CARE. {len(caution)} of {len(findings)} components "
            "are preview or classic-only."
        )
    else:
        verdict = f"PROCEED. All {len(findings)} components are generally available."

    lines = [f"VERDICT: {verdict}", ""]
    lines += [f"  [{level}] {feature} ({status}) -- {note}" for feature, status, level, note in findings]
    return "\n".join(lines)


async def main() -> None:
    credential = DefaultAzureCredential()

    # Resolves from TOOLBOX_ENDPOINT, or FOUNDRY_PROJECT_ENDPOINT + TOOLBOX_NAME.
    # Note what is absent: no MCP server URL, no auth wiring, no tool list.
    toolbox = FoundryToolbox(credential)

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    agent = Agent(
        client=client,
        instructions=INSTRUCTIONS,
        # Toolbox tools (discovered at runtime) alongside our local policy
        # function. The upstream sample passes the toolbox alone; this mixed
        # list was confirmed working on a deployed hosted agent, 2026-10-16.
        tools=[toolbox, assess_adoption_risk],
        # The hosting infrastructure manages history, so the service does not
        # need to store it.
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
