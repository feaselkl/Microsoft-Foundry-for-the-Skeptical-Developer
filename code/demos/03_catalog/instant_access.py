"""
Demo 3 -- The Model Catalog: instant access (PREVIEW)

Same call, same result, no deployment. You name the model directly and it
works. No deployment resource, no deployment-type dropdown, nothing to clean
up afterward.

This is the genuinely nice thing nobody announced loudly enough -- and it is
in preview, so say so on stage.

IMPORTANT: during preview, instant access requires a project in West US 3.
If this fails and deployed_call.py works, check your project's region first.

The model is deliberately one this project has NOT deployed (gpt-6-sol, while
deployed_call.py uses gpt-6-luna). If a deployment's name matches a model name,
the deployment takes precedence and instant access for that name is unavailable
-- so calling the deployed model "instantly" would quietly go through the
deployment and prove nothing. The script refuses to run in that case.

Run:  uv run python demos/03_catalog/instant_access.py
"""

import os
import sys

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

# A model NAME, not a deployment name. Nothing was deployed to make this work.
INSTANT_MODEL = os.environ.get("FOUNDRY_INSTANT_MODEL", "gpt-6-sol")

PROMPT = "Name three things a skeptical developer should check before adopting an AI platform."


def main() -> None:
    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    # The honesty check. Show the room the deployment list if anyone doubts it.
    deployed = sorted(d.name for d in project.deployments.list())
    if INSTANT_MODEL in deployed:
        sys.exit(
            f"ERROR: '{INSTANT_MODEL}' is also a deployment in this project, so this call\n"
            "would go through the deployment, not instant access -- a deployment whose\n"
            "name matches a model name takes precedence. Set FOUNDRY_INSTANT_MODEL to a\n"
            f"model you have not deployed. Deployed here: {', '.join(deployed)}"
        )

    openai = project.get_openai_client()
    response = openai.responses.create(model=INSTANT_MODEL, input=PROMPT)

    print(f"\n[instant access]  model name: {INSTANT_MODEL}  (no deployment)")
    print(f"                  deployed in this project: {', '.join(deployed) or 'nothing'}\n")
    print(response.output_text)


if __name__ == "__main__":
    main()
