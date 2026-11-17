"""Delete every agent and toolbox in the given Foundry projects.

Called by teardown.sh BEFORE it deletes the resource group, because these
objects outlive it. Observed 2026-11-17: after a resource-group delete and an
account purge, recreating the resource and project under the same names brought
back October's agents and toolbox. The resurrected hosted agent pointed at Entra
identities that no longer existed, so every call returned 500 -- and the service
then refused to delete it. Deleting them while the identities still exist avoids
all of that.

Usage (teardown.sh does this for you):
    uv run --project code python infra/delete-agent-objects.py ENDPOINT [ENDPOINT ...]
    uv run --project code python infra/delete-agent-objects.py --dry-run ENDPOINT

Exit status: 0 if everything listed was deleted (or --dry-run), 2 if anything
was left behind, 1 if a project could not be reached at all.
"""

import argparse
import sys

from azure.ai.projects import AIProjectClient
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential


def first_line(error: Exception) -> str:
    return (str(error).strip().splitlines() or [type(error).__name__])[0][:200]


def clean(project: AIProjectClient, dry_run: bool) -> list[str]:
    """Delete agents, then toolboxes. Returns what could not be deleted."""
    agents = sorted(a.name for a in project.agents.list())
    toolboxes = sorted(t.name for t in project.toolboxes.list())
    print(f"    agents ({len(agents)}): {', '.join(agents) or '-'}")
    print(f"    toolboxes ({len(toolboxes)}): {', '.join(toolboxes) or '-'}")
    if dry_run:
        return []

    left = []
    # Agents first: a hosted agent may be consuming a toolbox. force=True also
    # deletes the agent's sessions, which otherwise block deletion until they
    # expire.
    for name in agents:
        try:
            project.agents.delete(agent_name=name, force=True)
            print(f"    deleted agent {name}")
        except ResourceNotFoundError:
            pass
        except HttpResponseError as error:
            print(f"    COULD NOT delete agent {name}: {first_line(error)}")
            left.append(f"agent {name}")
    for name in toolboxes:
        try:
            project.toolboxes.delete(name)
            print(f"    deleted toolbox {name}")
        except ResourceNotFoundError:
            pass
        except HttpResponseError as error:
            print(f"    COULD NOT delete toolbox {name}: {first_line(error)}")
            left.append(f"toolbox {name}")
    return left


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("endpoints", nargs="+", help="project endpoints")
    parser.add_argument("--dry-run", action="store_true", help="list, delete nothing")
    args = parser.parse_args()

    left, unreachable = [], []
    with DefaultAzureCredential() as credential:
        for endpoint in args.endpoints:
            print(f"  {endpoint}")
            try:
                with AIProjectClient(endpoint=endpoint, credential=credential) as project:
                    left += clean(project, args.dry_run)
            except Exception as error:  # noqa: BLE001 -- report and keep going
                print(f"    COULD NOT reach the project: {first_line(error)}")
                unreachable.append(endpoint)

    if unreachable:
        return 1
    return 2 if left else 0


if __name__ == "__main__":
    sys.exit(main())
