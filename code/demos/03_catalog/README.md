# Demo 3 &mdash; The Model Catalog

**Talk section:** 3. The Model Catalog: Read the Fine Print (10 min)

## The Point

The catalog count is marketing. What you actually live with is the commercial tier, the deployment type, and which portal the model forces you into.

## The Narrative

1. Open the catalog. Note the scale, then immediately move off it.
2. Open two model cards side by side: **`gpt-6-sol`** (sold by Azure) and **`claude-opus-5-5`** (partners and community). Both are in `westus3`. Walk the slide's table: seller, SLA, terms for your data, billing, and content filtering all differ. Then the surprise: **support does not**. Microsoft's Claude hosting comparison says to contact Microsoft Support for both Claude versions.
3. Deploy a serverless model. When the deployment type dropdown appears, stop and let the room look at it. This is the nine-types slide made real.
4. Hit the endpoint with `deployed_call.py`.
5. Run `instant_access.py` against a model you never deployed. Same result, no deployment, no dropdown.
6. **The seam moved.** Filter the catalog to the Hugging Face collection and show that an ungated model now deploys to managed compute from the new portal (preview). Then open a *gated* model's card and show the **Continue in Foundry (classic)** button. The seam is still there; it just moved. Do not actually deploy: managed compute bills per accelerator-hour and needs GPU quota.

## To Build

- [x] `deployed_call.py` &mdash; call a serverless deployment by its deployment name
- [x] `instant_access.py` &mdash; call a model by name with no deployment (preview)
- [x] Pick the two model cards to compare: `gpt-6-sol` and `claude-opus-5-5`. Tiers checked against
      Microsoft Learn, 2026-10-16: Claude is partners and community for both hosting versions, sold and
      SLA-backed by Anthropic, billed through Azure Marketplace in Claude Consumption Units, supported
      through Microsoft Support, with no built-in Foundry content filtering.

## Run It

```bash
uv run python demos/03_catalog/deployed_call.py
uv run python demos/03_catalog/instant_access.py
```

## Stage Risks

- **Instant access requires a project in West US 3** during preview. If `instant_access.py` fails while `deployed_call.py` works, check the region before anything else.
- **Instant access is in preview.** Confirm it still works, and is still called that, the week of the talk. If it has changed, this demo needs rewriting and the corresponding slide needs a new claim.
- **Deploying live burns time.** Have a deployment already made. Show the dropdown, cancel, and switch to the pre-made one.
- **Marketplace models need a subscription step** the first time in a given subscription. Do this in advance or the demo stalls on a terms-acceptance dialog.
- **Regional availability.** Not every model is deployable in every region. Verify your demo region has both models you plan to compare.
