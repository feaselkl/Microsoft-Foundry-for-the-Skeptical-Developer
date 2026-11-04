"""
Demo 4, step 2 -- the same agent, with and without a tool.

THIS IS THE DEMO THAT HAS TO LAND. Everything else in section 4 is setup.

It builds two agents with identical instructions and the identical model. One
has no tools. One has the Foundry Feature Registry MCP server attached. Both get
the same question:

    "Should I build my RAG pipeline on Prompt Flow?"

The tool-less agent answers from training data. Depending on the model's cutoff
it will sound confident, hedge, or be quietly wrong -- and to the room it will
look perfectly reasonable either way. That is the point. The tool-equipped agent
comes back with a retirement date.

Two things land at once:

  1. What a tool actually buys you. Not "the agent can do more things," but
     "the agent stops guessing about things it cannot know."
  2. The talk's own thesis, demonstrated by the platform on itself. The agent
     tells the room that Prompt Flow is retired -- the same fact that opened
     the talk in section 1.

Prerequisites:
    ./infra/setup.sh
    ./infra/deploy-mcp-server.sh

Run:  uv run python demos/04_agents/agent_with_mcp.py
"""

import os
import sys

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from openai import APITimeoutError

load_dotenv()

# The OpenAI client's default timeout is 10 minutes. When the MCP server is
# down, Foundry waits on it and this script appears to hang with no output --
# the worst possible failure mode on stage. Two minutes is ample for a tool
# call that works.
REQUEST_TIMEOUT_SECONDS = 120

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-5-mini")
MCP_SERVER_URL = os.environ.get("FOUNDRY_MCP_SERVER_URL")

# Same instructions for both agents. The ONLY difference is the tool, and
# saying so out loud before you run it is what makes the contrast credible.
INSTRUCTIONS = (
    "You are a blunt technical advisor helping developers decide what to build "
    "on. Answer in at most four sentences. If you can verify a platform "
    "feature's lifecycle status, cite the status and any dates. If you cannot "
    "verify it, say so explicitly rather than guessing."
)

QUESTION = "Should I build my RAG pipeline on Prompt Flow?"

BARE_AGENT = "SkepticNoTools"
TOOLED_AGENT = "SkepticWithRegistry"


def ask(project, openai, agent, question: str) -> str:
    conversation = openai.conversations.create()
    try:
        response = openai.responses.create(
            conversation=conversation.id,
            input=question,
            extra_body={
                "agent_reference": {
                    "name": agent.name,
                    "id": agent.id,
                    "type": "agent_reference",
                }
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except APITimeoutError:
        sys.exit(
            f"\nERROR: no answer from '{agent.name}' within {REQUEST_TIMEOUT_SECONDS}s.\n"
            "If this is the agent with tools, the MCP server is probably not answering.\n"
            "Re-run ./infra/deploy-mcp-server.sh -- it now refuses to finish unless the\n"
            "server answers a real MCP call -- or check its revision health with:\n"
            "  az containerapp revision list -n mcp-feature-registry -g rg-foundry-skeptic -o table"
        )
    finally:
        openai.conversations.delete(conversation_id=conversation.id)
    return response.output_text


def banner(text: str) -> None:
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def main() -> None:
    if not MCP_SERVER_URL:
        print(
            "ERROR: FOUNDRY_MCP_SERVER_URL is not set.\n"
            "       Run ./infra/deploy-mcp-server.sh first -- it writes the value\n"
            "       into code/.env for you.",
            file=sys.stderr,
        )
        sys.exit(1)

    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )
    openai = project.get_openai_client()

    print(f"Question: {QUESTION}")
    print(f"Model:    {MODEL}  (identical for both agents)")

    # ---- Agent 1: no tools -------------------------------------------------
    bare = project.agents.create_version(
        agent_name=BARE_AGENT,
        definition=PromptAgentDefinition(model=MODEL, instructions=INSTRUCTIONS),
    )

    banner("WITHOUT TOOLS -- answering from training data")
    print(ask(project, openai, bare, QUESTION))

    # ---- Agent 2: same thing, plus the feature registry --------------------
    registry = MCPTool(
        server_label="foundry_feature_registry",
        server_url=MCP_SERVER_URL,
        # "never" keeps the demo moving. In production this is a real
        # governance decision: "always" puts a human in front of every tool
        # call, which is what you want for anything that writes. Worth one
        # sentence on stage -- it is the kind of control the skeptics ask about.
        require_approval="never",
    )

    tooled = project.agents.create_version(
        agent_name=TOOLED_AGENT,
        definition=PromptAgentDefinition(
            model=MODEL,
            instructions=INSTRUCTIONS,
            tools=[registry],
        ),
    )

    banner("WITH THE FEATURE REGISTRY -- same model, same instructions")
    print(ask(project, openai, tooled, QUESTION))

    # ---- The follow-up that widens it --------------------------------------
    banner("FOLLOW-UP -- how much of this platform is preview?")
    print(ask(project, openai, tooled, "How much of Foundry is still in preview?"))

    print(
        f"\n\nBoth agents are still in the project ({BARE_AGENT}, {TOOLED_AGENT}).\n"
        "Open them in the portal to show that code-first and portal-first\n"
        "produce the same object."
    )


if __name__ == "__main__":
    main()
