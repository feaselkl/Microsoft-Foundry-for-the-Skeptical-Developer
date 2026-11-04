"""
Demo 3 -- The Model Catalog: instant access (PREVIEW)

Same call, same result, no deployment. You name the model directly and it
works. No deployment resource, no deployment-type dropdown, nothing to clean
up afterward.

This is the genuinely nice thing nobody announced loudly enough -- and it is
in preview, so say so on stage.

IMPORTANT: during preview, instant access requires a project in West US 3.
If this fails and deployed_call.py works, check your project's region first.

Run:  uv run python demos/03_catalog/instant_access.py
"""

import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

# A model NAME, not a deployment name. Nothing was deployed to make this work.
INSTANT_MODEL = os.environ.get("FOUNDRY_INSTANT_MODEL", "gpt-5-mini")

PROMPT = "Name three things a skeptical developer should check before adopting an AI platform."


def main() -> None:
    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )
    openai = project.get_openai_client()

    response = openai.responses.create(model=INSTANT_MODEL, input=PROMPT)

    print(f"\n[instant access]  model name: {INSTANT_MODEL}  (no deployment)\n")
    print(response.output_text)


if __name__ == "__main__":
    main()
