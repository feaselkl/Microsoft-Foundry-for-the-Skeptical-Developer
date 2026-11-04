"""
Demo 3 -- The Model Catalog: the deployment path

Call a model you deployed yourself. This is the normal path: pick a model,
pick one of nine serverless deployment types, name the deployment, wait for
it, then call it by that deployment name.

Contrast with instant_access.py, which skips all of that.

Run:  uv run python demos/03_catalog/deployed_call.py
"""

import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

# The name YOU gave the deployment, which need not match the model name.
# That indirection is the point: it is what lets you swap the model underneath
# without touching application code.
DEPLOYMENT = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-5-mini")

PROMPT = "Name three things a skeptical developer should check before adopting an AI platform."


def main() -> None:
    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )
    openai = project.get_openai_client()

    response = openai.responses.create(model=DEPLOYMENT, input=PROMPT)

    print(f"\n[deployed]  deployment name: {DEPLOYMENT}\n")
    print(response.output_text)


if __name__ == "__main__":
    main()
