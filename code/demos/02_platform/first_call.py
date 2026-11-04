"""
Demo 2 -- What Foundry Is Now

One model call, one endpoint, fifteen lines.

The point of this script is how *little* there is to it. The previous
generation needed azure-ai-inference or azure-ai-generative or azure-ai-ml,
each against its own endpoint. Now there is one project endpoint and one
client, and the client it hands back is just an OpenAI client.

Run:  uv run python demos/02_platform/first_call.py
"""

import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

# Portal -> your project -> Overview -> Endpoints
# Format: https://<resource>.services.ai.azure.com/api/projects/<project>
PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-5-mini")


def main() -> None:
    # One client, built from one endpoint. `az login` supplies the credential.
    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    # The project hands back a plain OpenAI client. Note what this means for
    # the lock-in conversation in section 6: this is the OpenAI-compatible
    # Responses API, not a bespoke Azure surface.
    openai = project.get_openai_client()

    response = openai.responses.create(
        model=MODEL,
        input="In two sentences, what is Microsoft Foundry, the new AI platform by Microsoft?",
    )

    print(f"\nModel: {MODEL}")
    print(f"Endpoint: {PROJECT_ENDPOINT}\n")
    print(response.output_text)


if __name__ == "__main__":
    main()
