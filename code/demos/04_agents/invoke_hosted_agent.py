"""
Talk to the deployed hosted agent.

Separate from deploy_hosted_agent.py on purpose: deploying takes minutes, and
you do not want to be doing it on stage. Deploy in the morning, run this
during the session.

Run:  uv run python demos/04_agents/invoke_hosted_agent.py
      uv run python demos/04_agents/invoke_hosted_agent.py "your own question"
"""

import os
import sys

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_NAME = os.environ.get("FOUNDRY_HOSTED_AGENT_NAME", "skeptic-assessor")

# The demo question. Three features, three different lifecycle answers, one
# deterministic verdict -- and every fact in the reply came from the toolbox
# rather than from the model's memory.
DEFAULT_QUESTION = (
    "I want to build a RAG pipeline on Prompt Flow, deploy the embedding model "
    "to managed compute, and use instant access for the chat model. "
    "Is that a good plan?"
)


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project,
        project.get_openai_client(agent_name=AGENT_NAME) as openai,
    ):
        print(f"\nQ: {question}\n")
        response = openai.responses.create(input=question)
        print("=" * 70)
        print(response.output_text)
        print("=" * 70)


if __name__ == "__main__":
    main()
