"""
Demo 4, step 3a -- curate a toolbox.

Step 2 attached the MCP server directly to one agent. That works, and for one
agent it is the simplest thing. It also does not scale: every agent that needs
these tools carries its own copy of the server URL, its own approval policy,
and its own auth configuration. Change the server and you go rewire each one.

A toolbox curates the set ONCE and serves it behind a single managed MCP
endpoint, with centralized auth, governance, and versioning. Agents point at the
toolbox instead of at the individual tools. Promote a new version and every
consumer picks it up without redeploying.

Hosted-agent toolboxes are GA. Prompt-agent toolboxes went to public preview on
2026-09-24, so a prompt agent CAN consume one now -- but the GA path is the
hosted agent, which is why this script comes after step 2 and before the hosted
agent: it is the bridge between them.

Run:  uv run python demos/04_agents/create_toolbox.py
"""

import os
import sys

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPToolboxTool
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MCP_SERVER_URL = os.environ.get("FOUNDRY_MCP_SERVER_URL")
TOOLBOX_NAME = os.environ.get("FOUNDRY_TOOLBOX_NAME", "skeptic-tools")


def main() -> None:
    if not MCP_SERVER_URL:
        print(
            "ERROR: FOUNDRY_MCP_SERVER_URL is not set.\n"
            "       Run ./infra/deploy-mcp-server.sh first.",
            file=sys.stderr,
        )
        sys.exit(1)

    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    version = project.toolboxes.create_version(
        name=TOOLBOX_NAME,
        description="Foundry lifecycle facts for evaluating what is safe to build on.",
        tools=[
            MCPToolboxTool(
                server_label="foundry_feature_registry",
                server_url=MCP_SERVER_URL,
                require_approval="never",
            ),
        ],
    )

    print(f"Toolbox: {version.name}")
    print(f"Version: {version.version}")

    # Two endpoints, and the difference matters on stage.
    #
    #   consumer  -> always serves default_version. This is what agents use, so
    #                you can promote a new version without touching agent code.
    #   developer -> pinned to one version. For validating a version BEFORE you
    #                promote it.
    #
    # That split is the versioning story in one slide.
    consumer = f"{PROJECT_ENDPOINT}/toolboxes/{version.name}/mcp?api-version=v1"
    developer = (
        f"{PROJECT_ENDPOINT}/toolboxes/{version.name}"
        f"/versions/{version.version}/mcp?api-version=v1"
    )

    print(f"\nConsumer endpoint  (agents use this, always the default version):\n  {consumer}")
    print(f"\nDeveloper endpoint (pinned to v{version.version}, for testing):\n  {developer}")
    print(
        f"\nSet this for the hosted agent:\n"
        f"  FOUNDRY_TOOLBOX_NAME={version.name}"
    )


if __name__ == "__main__":
    main()
