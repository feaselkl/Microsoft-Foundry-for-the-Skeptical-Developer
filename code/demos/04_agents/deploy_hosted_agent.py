"""
Deploy the demo-4 hosted agent to Foundry Agent Service.

This is the real thing, not a container-hosting substitute: the source is zipped,
uploaded, built remotely by Foundry, and served on a managed endpoint with
autoscale and its own Entra identity.

What it does, in order:
  1. Zips hosted_agent/ with main.py and requirements.txt at the ROOT of the
     archive (the runtime requires that; nesting them is the most common cause
     of "provisioning failed").
  2. Creates a new agent version from that code.
  3. Polls until the version is active. This takes minutes, not seconds --
     Foundry is resolving dependencies and building remotely.
  4. Routes 100% of the agent endpoint's traffic to the new version.
  5. Sends one smoke-test question.

Unlike the Microsoft quickstart, this KEEPS the deployed version rather than
deleting it afterward. You want it alive for the talk. Clean up with
infra/teardown.sh.

Prerequisites:
    ./infra/setup.sh
    ./infra/deploy-mcp-server.sh
    uv run python demos/04_agents/create_toolbox.py

Run:  uv run python demos/04_agents/deploy_hosted_agent.py
"""

import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentEndpointConfig,
    CodeConfiguration,
    CodeDependencyResolution,
    FixedRatioVersionSelectionRule,
    HostedAgentDefinition,
    ProtocolConfiguration,
    ProtocolVersionRecord,
    ResponsesProtocolConfiguration,
    VersionSelector,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-5-mini")
TOOLBOX_NAME = os.environ.get("FOUNDRY_TOOLBOX_NAME", "skeptic-tools")
AGENT_NAME = os.environ.get("FOUNDRY_HOSTED_AGENT_NAME", "skeptic-assessor")

SOURCE_DIR = Path(__file__).parent / "hosted_agent"

# Keep the archive to what the runtime needs. A stray .env would ship local
# secrets into the build.
EXCLUDED = {".git", ".venv", "__pycache__", ".env", ".env.example", ".pytest_cache"}


def build_zip(source: Path) -> Path:
    """Zip the agent source with main.py and requirements.txt at the archive root."""
    out = Path(tempfile.gettempdir()) / f"{AGENT_NAME}.zip"
    written = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            if any(part in EXCLUDED for part in path.parts):
                continue
            arcname = path.relative_to(source)
            zf.write(path, arcname)
            written.append(str(arcname))

    if "main.py" not in written or "requirements.txt" not in written:
        sys.exit(
            f"ERROR: main.py and requirements.txt must be at the root of the zip.\n"
            f"       Found: {sorted(written)}"
        )

    print(f"Packaged {len(written)} files: {', '.join(sorted(written))}")
    return out


def wait_until_active(project: AIProjectClient, version: str, attempts: int = 60) -> None:
    """Poll the version until it is active. Remote build takes minutes."""
    last = None
    for i in range(1, attempts + 1):
        time.sleep(10)
        details = project.agents.get_version(agent_name=AGENT_NAME, agent_version=version)
        status = details["status"]
        if status != last:
            print(f"  [{i:>2}/{attempts}] {status}")
            last = status
        if status == "active":
            return
        if status == "failed":
            raise RuntimeError(
                f"Provisioning failed: {dict(details)}\n"
                "Check that main.py and requirements.txt are at the zip root and "
                "that the model deployment name exists in this project."
            )
    raise RuntimeError("Timed out waiting for the hosted agent version to become active.")


def main() -> None:
    code_zip = build_zip(SOURCE_DIR)

    with (
        code_zip.open("rb") as code,
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project,
    ):
        print(f"\nCreating a version of '{AGENT_NAME}'...")
        created = project.agents.create_version_from_code(
            agent_name=AGENT_NAME,
            description="Assesses whether a proposed design is safe to build on.",
            definition=HostedAgentDefinition(
                cpu="0.5",
                memory="1Gi",
                code_configuration=CodeConfiguration(
                    runtime="python_3_14",
                    entry_point=["python", "main.py"],
                    # Foundry resolves requirements.txt and builds the image.
                    dependency_resolution=CodeDependencyResolution.REMOTE_BUILD,
                ),
                environment_variables={
                    "FOUNDRY_PROJECT_ENDPOINT": PROJECT_ENDPOINT,
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME": MODEL,
                    # FoundryToolbox builds the consumer endpoint from this,
                    # so promoting a toolbox version needs no redeploy here.
                    "TOOLBOX_NAME": TOOLBOX_NAME,
                },
                protocol_versions=[ProtocolVersionRecord(protocol="responses", version="2.0.0")],
            ),
            code=code,
        )
        print(f"Created version {created.version}. Building remotely, this takes a few minutes.")

        wait_until_active(project, created.version)
        print("Active.")

        print("\nRouting 100% of endpoint traffic to this version...")
        project.agents.update_details(
            agent_name=AGENT_NAME,
            agent_endpoint=AgentEndpointConfig(
                version_selector=VersionSelector(
                    version_selection_rules=[
                        FixedRatioVersionSelectionRule(
                            agent_version=created.version,
                            traffic_percentage=100,
                        ),
                    ]
                ),
                protocol_configuration=ProtocolConfiguration(
                    responses=ResponsesProtocolConfiguration()
                ),
            ),
        )
        print("Routed.")

        # The traffic-percentage rule above is worth a sentence on stage: it is
        # how you do a canary. Two versions, 90/10, watch the traces.

        print("\nSmoke test...")
        with project.get_openai_client(agent_name=AGENT_NAME) as openai:
            response = openai.responses.create(
                input=(
                    "I want to build a RAG pipeline on Prompt Flow, deploy the "
                    "embedding model to managed compute, and use instant access "
                    "for the chat model. Is that a good plan?"
                ),
            )
        print(f"\n{'=' * 70}\n{response.output_text}\n{'=' * 70}")

    print(
        f"\nAgent '{AGENT_NAME}' version {created.version} is live and routed.\n"
        "It stays deployed for the talk. infra/teardown.sh removes it."
    )


if __name__ == "__main__":
    main()
