"""
Foundry Feature Registry -- a small MCP server for demo 4.

Exposes a curated set of Microsoft Foundry lifecycle facts: what is GA, what is
preview, what has been retired, and what is stranded in the classic portal.

Why this, and not a weather tool? Two reasons.

1. It is deterministic. No third-party API, no conference wifi dependency, no
   rate limit. It returns the same answer every time you demo it.
2. It is on-theme. The agent ends up auditing the platform it runs on, which is
   the whole argument of the talk. Ask the model about Prompt Flow WITHOUT this
   tool and it answers from training data. Ask it WITH the tool and it gives you
   a retirement date. That contrast is the reason toolboxes exist, and it is the
   point demo 4 has to land.

Runs as a streamable-HTTP MCP server, which is what Foundry's toolbox connects
to. Deploy with infra/deploy-mcp-server.sh.
"""

import json
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

DATA = json.loads((Path(__file__).parent / "features.json").read_text())
FEATURES = DATA["features"]
VERIFIED = DATA["_verified"]

mcp = MCPServer("foundry-feature-registry")


def _find(name: str) -> dict | None:
    needle = name.strip().lower()
    for f in FEATURES:
        if f["name"].lower() == needle:
            return f
    # Fall back to substring matching so "prompt flow retirement" still lands.
    for f in FEATURES:
        if needle in f["name"].lower() or f["name"].lower() in needle:
            return f
    return None


@mcp.tool()
def lookup_feature(name: str) -> str:
    """Look up the lifecycle status of a Microsoft Foundry feature.

    Returns whether the feature is generally available, in preview, retired, or
    only reachable through the Foundry (classic) portal, along with the relevant
    dates and any replacement.

    Args:
        name: The feature name, for example "Prompt Flow" or "instant access".
    """
    hit = _find(name)
    if hit is None:
        known = ", ".join(f["name"] for f in FEATURES)
        return f"No registry entry for '{name}'. Known features: {known}"

    lines = [
        f"Feature: {hit['name']}",
        f"Status: {hit['status'].upper()}",
        f"Detail: {hit['detail']}",
    ]
    if "replacement" in hit:
        lines.append(f"Replacement: {hit['replacement']}")
    if "retirement_date" in hit:
        lines.append(f"Retirement date: {hit['retirement_date']}")
    if "ga_date" in hit:
        lines.append(f"GA date: {hit['ga_date']}")
    lines.append(f"(Registry verified {VERIFIED})")
    return "\n".join(lines)


@mcp.tool()
def list_features_by_status(status: str) -> str:
    """List Microsoft Foundry features in a given lifecycle status.

    Args:
        status: One of "ga", "preview", "retired", "replaced", "classic", or "mixed".
    """
    wanted = status.strip().lower()
    hits = [f for f in FEATURES if f["status"].lower() == wanted]
    if not hits:
        statuses = sorted({f["status"] for f in FEATURES})
        return f"No features with status '{status}'. Valid statuses: {', '.join(statuses)}"

    out = [f"Features with status '{wanted}' ({len(hits)}):"]
    out += [f"  - {f['name']}: {f['detail']}" for f in hits]
    out.append(f"(Registry verified {VERIFIED})")
    return "\n".join(out)


@mcp.tool()
def assess_adoption_risk() -> str:
    """Summarize how much of Microsoft Foundry is not yet stable.

    Returns a count of features by lifecycle status, for judging how much of the
    platform is resting on preview functionality.
    """
    counts: dict[str, int] = {}
    for f in FEATURES:
        counts[f["status"]] = counts.get(f["status"], 0) + 1

    total = len(FEATURES)
    preview = counts.get("preview", 0)
    out = [
        f"Registry covers {total} tracked features (verified {VERIFIED}).",
        "",
        "By status:",
    ]
    out += [f"  {status}: {n}" for status, n in sorted(counts.items())]
    out += [
        "",
        f"{preview} of {total} tracked features are in preview. "
        "Preview features carry no SLA and their APIs may change.",
    ]
    return "\n".join(out)


if __name__ == "__main__":
    # Serves streamable HTTP at /mcp. In mcp 2.x every transport setting goes to
    # run(); the constructor no longer takes host or port.
    mcp.run(
        transport="streamable-http",
        # All interfaces: ingress reaches the container from outside it.
        host="0.0.0.0",
        # The Dockerfile sets PORT=8000 to match the Container Apps target
        # port. Container Apps does not inject PORT itself.
        port=int(os.environ.get("PORT", "8000")),
        # No per-client session state, so any replica can answer any request.
        stateless_http=True,
        # DNS-rebinding protection guards LOCAL servers from malicious web pages,
        # and it switches itself on for a localhost host. Behind Container Apps
        # every request carries the public *.azurecontainerapps.io Host header,
        # which it would reject with 421 -- including every call from Foundry.
        # Allowlisting does not rescue it: entries must be host:port, and
        # ingress forwards a bare hostname. This server is public, read-only and
        # unauthenticated by design, so turn it off explicitly rather than lean
        # on the library's guess from the host value.
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
            allowed_hosts=[],
            allowed_origins=[],
        ),
    )
