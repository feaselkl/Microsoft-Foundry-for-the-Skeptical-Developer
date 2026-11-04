"""
Demo 4 -- Agents: the declarative end of the spectrum

A prompt agent is instructions + a model + (optionally) tools. Foundry runs
it. There is no container, no runtime to maintain, no scaling to think about.

This script creates the agent and then chats with it across two turns, so the
room can see that conversation state is the platform's problem, not yours.

The same agent can be built in the portal. Show it there first, then run this
to make the point that portal-first and code-first produce the same object.

Run:  uv run python demos/04_agents/prompt_agent.py
"""

import os

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-5-mini")
AGENT_NAME = os.environ.get("FOUNDRY_AGENT_NAME", "SkepticalDeveloperAgent")

INSTRUCTIONS = (
    "You are a blunt technical advisor who helps developers evaluate cloud "
    "platforms. Answer in at most three sentences. When something is a "
    "genuine trade-off, say so plainly instead of hedging."
)


def main() -> None:
    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    # Creating a *version*, not just an agent. Every edit snapshots a new
    # version you can roll back to -- part of the governance story that makes
    # this more than a saved prompt.
    agent = project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=PromptAgentDefinition(
            model=MODEL,
            instructions=INSTRUCTIONS,
        ),
    )
    print(f"\nAgent created  (id: {agent.id}, name: {agent.name}, version: {agent.version})\n")

    # Bind an OpenAI client to the agent, then talk to it.
    openai = project.get_openai_client(agent_name=AGENT_NAME)

    # A conversation carries history for you across turns.
    conversation = openai.conversations.create()

    first = openai.responses.create(
        conversation=conversation.id,
        input="Is it a bad idea to build my whole product on one cloud's AI platform?",
    )
    print("Q: Is it a bad idea to build my whole product on one cloud's AI platform?")
    print(f"A: {first.output_text}\n")

    # No history passed in -- the conversation id is doing that work.
    second = openai.responses.create(
        conversation=conversation.id,
        input="Which part of that would be hardest to undo?",
    )
    print("Q: Which part of that would be hardest to undo?")
    print(f"A: {second.output_text}\n")


if __name__ == "__main__":
    main()
