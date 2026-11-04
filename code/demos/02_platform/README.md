# Demo 2 &mdash; What Foundry Is Now

**Talk section:** 2. What Foundry Is Now (8 min)

## The Point

Show the current resource model to people who have never opened Foundry, and make one model call with the unified SDK. This demo exists to orient the room, not to impress it.

## The Narrative

1. Start in the Azure portal. Show the **Foundry resource** as a single Azure resource with projects underneath it. Say once that the old way was a hub plus an Azure OpenAI resource plus Azure AI Services, and that this replaces it.
2. Move to the Foundry portal. Walk the project: models, agents, tracing. Keep it short; they will see each area properly later.
3. Show the **project endpoint** on the Overview page. This is the one URL the SDK needs, and it is the thing that replaced five endpoints.
4. Run `first_call.py`. Fifteen lines, one endpoint, `DefaultAzureCredential`.
5. Bounce to the **classic** portal for ten seconds so they see the seam exists. Do not explain it yet; that is section 3.

## To Build

- [x] `first_call.py` &mdash; `AIProjectClient` from the project endpoint, one Responses call, print the output
- [ ] Decide whether to create the project live or pre-create it (see Stage Risks)

## Run It

```bash
uv run python demos/02_platform/first_call.py
```

## Stage Risks

- **Creating a project live takes longer than it looks.** Resource provisioning is not reliably fast enough for an 8-minute section. Run [`infra/setup.sh`](../../../infra/setup.sh) beforehand, then show the creation blade in the portal without submitting it and cut to the provisioned project.
- **A 403 with an empty body means RBAC, not auth.** `Owner` and `Contributor` are
  control-plane roles (`dataActions: []`); calling the endpoint needs a Foundry role.
  `infra/setup.sh` assigns it and verifies with a real call, so this should be settled
  before you ever run this demo. If it recurs on the day, check the role assignment first
  and remember assignments take a couple of minutes to propagate.
- **`DefaultAzureCredential` picks the wrong tenant** if you are signed in to more than one. Run `az account show` before the talk and pin the subscription with `az account set`. There is no API key fallback -- Entra is the only auth path -- so a credential problem is a dead demo, not a degraded one.
- **Portal UI churn.** Screenshot this walkthrough the week of the talk as a fallback. The portal has moved things between deliveries before.
