"""
Demo 5 -- Observability: evaluation.

Demo 4 showed the with-tool / without-tool contrast on ONE question, and it made
the point anecdotally. This measures it. Same twelve questions, both agents, one
yardstick, two numbers.

That progression is the argument of section 5: a demo is an anecdote, and
evaluation is what turns an anecdote into something you can put in a pull
request. It is also why evaluation is the part of this platform worth paying
for.

How it works:
  1. Upload a small JSONL test set as a project dataset.
  2. Generate a RUBRIC evaluator from the tool-equipped agent's own context --
     its name, instructions, and tools -- so the scoring dimensions come from
     what the agent is actually supposed to do.
  3. Create ONE evaluation. It is a container: every run under it shares a
     schema and produces the same metrics, which is what makes runs comparable.
  4. Run it twice, once per agent, against the SAME rubric.
  5. Print both scorecards side by side.

Prerequisites:
    ./infra/setup.sh
    ./infra/deploy-mcp-server.sh
    uv run python demos/04_agents/agent_with_mcp.py    # creates both agents

Run:  uv run python demos/05_observability/evaluate.py
      uv run python demos/05_observability/evaluate.py --reuse-rubric
      uv run python demos/05_observability/evaluate.py --rubric lifecycle-accuracy-1a2b3c4d

Generating the rubric is the step you can skip. The rubric is saved in the
project, so after one full run, --reuse-rubric picks up the newest one and
--rubric NAME picks a specific one. Every step prints its elapsed time, so a
single rehearsal run shows where the minutes go.
"""

import argparse
import os
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentEvaluatorGenerationJobSource,
    EvaluatorGenerationInputs,
    EvaluatorGenerationJob,
    TestingCriterionAzureAIEvaluator,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from openai.types.eval_create_params import DataSourceConfigCustom

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-5-mini")

# The two agents from demo 4. Identical model, identical instructions; one has
# the feature registry attached and one does not.
BARE_AGENT = os.environ.get("FOUNDRY_BARE_AGENT_NAME", "SkepticNoTools")
TOOLED_AGENT = os.environ.get("FOUNDRY_TOOLED_AGENT_NAME", "SkepticWithRegistry")

DATA_FILE = Path(__file__).parent / "eval_data" / "foundry_questions.jsonl"
POLL_SECONDS = 10
RUBRIC_PREFIX = "lifecycle-accuracy-"

# Step name -> seconds, filled in as the script runs and printed at the end.
TIMINGS: dict[str, float] = {}
START = time.monotonic()


def clock(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}m {seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


@contextmanager
def step(name: str):
    """Time one step and say how long it took."""
    began = time.monotonic()
    yield
    TIMINGS[name] = time.monotonic() - began
    print(f"  ({name}: {clock(TIMINGS[name])})")


def require_agents(project: AIProjectClient) -> None:
    """Fail fast, before anything is uploaded, if demo 4 has not been run.

    This script evaluates demo 4's agents rather than creating its own, because
    measuring the exact contrast the room just watched is the point. So without
    them there is nothing to evaluate -- and the service's error for that ("agent
    resource is not found") arrives only after a dataset has been uploaded.
    """
    present = {a.name for a in project.agents.list()}
    missing = [n for n in (BARE_AGENT, TOOLED_AGENT) if n not in present]
    if missing:
        sys.exit(
            f"ERROR: agent(s) not found in this project: {', '.join(missing)}\n\n"
            "evaluate.py scores the two agents demo 4 creates. Run these first:\n"
            "  ./infra/deploy-mcp-server.sh                     # from the repo root\n"
            "  uv run python demos/04_agents/agent_with_mcp.py  # from code/"
        )


def upload_dataset(project: AIProjectClient):
    """Upload the test set. Version it so re-runs do not collide."""
    version = time.strftime("%Y%m%d%H%M%S")
    print(f"Uploading {DATA_FILE.name} as version {version}...")
    dataset = project.datasets.upload_file(
        name="foundry-lifecycle-questions",
        version=version,
        file_path=str(DATA_FILE),
    )
    print(f"  Dataset: {dataset.id}")
    return dataset


def generate_rubric(project: AIProjectClient):
    """Generate a rubric evaluator from the tool-equipped agent's own context.

    A rubric is the recommended primary measure for agents: weighted scoring
    dimensions an LLM judge applies to every response. Generating it from the
    agent means the dimensions come from what the agent is supposed to do,
    rather than from a generic notion of "good answer."

    Show the printed dimensions on stage. Seeing the judge's criteria is what
    stops evaluation looking like a black box scoring another black box.
    """
    print(f"\nGenerating a rubric from '{TOOLED_AGENT}'...")
    job = EvaluatorGenerationJob(
        inputs=EvaluatorGenerationInputs(
            model=MODEL,
            evaluator_name=f"{RUBRIC_PREFIX}{uuid.uuid4().hex[:8]}",
            evaluator_display_name="Lifecycle Accuracy",
            sources=[AgentEvaluatorGenerationJobSource(agent_name=TOOLED_AGENT)],
        ),
    )
    began = time.monotonic()
    poller = project.beta.evaluators.begin_create_generation_job(job=job)
    while not poller.done():
        print(f"  status={poller.status()}  ({clock(time.monotonic() - began)})")
        time.sleep(POLL_SECONDS)

    rubric = poller.result()
    show_rubric(rubric)
    print(f"  Skip this step next time with:  --rubric {rubric.name}  (or --reuse-rubric)")
    return rubric


def find_rubric(project: AIProjectClient, name: str | None):
    """Load a saved rubric instead of generating one.

    With a name, use that rubric's newest version. Without one, use the most
    recently created rubric this script has generated.
    """
    evaluators = project.beta.evaluators
    if name:
        print(f"\nReusing rubric '{name}'...")
        versions = list(evaluators.list_versions(name))
        if not versions:
            sys.exit(f"ERROR: no rubric named '{name}' in this project.")
    else:
        print(f"\nReusing the newest '{RUBRIC_PREFIX}*' rubric...")
        versions = [e for e in evaluators.list(type="all") if (e.name or "").startswith(RUBRIC_PREFIX)]
        if not versions:
            sys.exit(
                "ERROR: no saved rubric found. Run once without --reuse-rubric to generate one."
            )
    rubric = max(versions, key=lambda e: str(e.created_at or ""))
    show_rubric(rubric)
    return rubric


def show_rubric(rubric) -> None:
    print(f"  Rubric: {rubric.name} v{rubric.version}")
    dimensions = getattr(getattr(rubric, "definition", None), "dimensions", None) or []
    for dim in dimensions:
        print(f"    - {dim.id} (weight {dim.weight}): {dim.description}")


def build_criteria(rubric):
    """The rubric as primary measure, plus one built-in for contrast."""
    return [
        TestingCriterionAzureAIEvaluator(
            type="azure_ai_evaluator",
            name="Lifecycle Accuracy",
            evaluator_name=rubric.name,
            initialization_parameters={"deployment_name": MODEL},
            data_mapping={
                "query": "{{item.query}}",
                # output_items includes tool calls, so the judge can see
                # WHETHER the agent looked anything up -- not just what it said.
                "response": "{{sample.output_items}}",
            },
        ),
        TestingCriterionAzureAIEvaluator(
            type="azure_ai_evaluator",
            name="Coherence",
            evaluator_name="builtin.coherence",
            initialization_parameters={"deployment_name": MODEL},
            data_mapping={
                "query": "{{item.query}}",
                "response": "{{sample.output_text}}",
            },
        ),
    ]


def run_against(client, evaluation, dataset, agent_name: str):
    """Start one evaluation run targeting one agent."""
    print(f"\nRunning against '{agent_name}'...")
    run = client.evals.runs.create(
        eval_id=evaluation.id,
        name=f"{agent_name} run",
        data_source={
            "type": "azure_ai_target_completions",
            "source": {"type": "file_id", "id": dataset.id},
            "input_messages": {
                "type": "template",
                "template": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": {"type": "input_text", "text": "{{item.query}}"},
                    }
                ],
            },
            # Omitting "version" targets the latest.
            "target": {"type": "azure_ai_agent", "name": agent_name},
        },
    )
    print(f"  Run: {run.id}")
    return run


def wait_for_both(client, evaluation, runs: dict) -> dict:
    """Poll both runs together and report each one as it finishes.

    They run concurrently, so waiting on one and then the other would hide
    which was actually slower. Prints a status line every 30 seconds so a long
    wait never looks like a hang.
    """
    began = time.monotonic()
    done, last_report = {}, 0.0
    while len(done) < len(runs):
        for label, run in runs.items():
            if label in done:
                continue
            current = client.evals.runs.retrieve(run_id=run.id, eval_id=evaluation.id)
            if current.status in ("completed", "failed", "canceled"):
                done[label] = current
                TIMINGS[f"run: {label}"] = time.monotonic() - began
                print(f"  {label} {current.status} after {clock(TIMINGS[f'run: {label}'])}")
        waited = time.monotonic() - began
        if len(done) < len(runs) and waited - last_report >= 30:
            pending = ", ".join(label for label in runs if label not in done)
            print(f"  still running after {clock(waited)}: {pending}")
            last_report = waited
        if len(done) < len(runs):
            time.sleep(5)
    return done


def scorecard(label: str, run) -> None:
    print(f"\n{'-' * 62}\n{label}  [{run.status}]\n{'-' * 62}")
    counts = getattr(run, "result_counts", None)
    if counts:
        print(f"  passed {counts.passed} / failed {counts.failed} / errored {counts.errored}")
    for criterion in getattr(run, "per_testing_criteria_results", []) or []:
        name = getattr(criterion, "testing_criteria", "?")
        print(
            f"  {name:<22} pass {getattr(criterion, 'passed', '?'):>3}   "
            f"fail {getattr(criterion, 'failed', '?'):>3}"
        )
    if getattr(run, "report_url", None):
        print(f"  Report: {run.report_url}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--reuse-rubric", action="store_true",
                       help="use the newest saved rubric instead of generating one")
    group.add_argument("--rubric", metavar="NAME",
                       help="use this saved rubric instead of generating one")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project,
    ):
        client = project.get_openai_client()

        with step("check agents"):
            require_agents(project)
        with step("upload dataset"):
            dataset = upload_dataset(project)
        if args.reuse_rubric or args.rubric:
            with step("load rubric"):
                rubric = find_rubric(project, args.rubric)
        else:
            with step("generate rubric"):
                rubric = generate_rubric(project)

        # ONE evaluation, TWO runs. The shared schema is what makes the two
        # scorecards comparable -- and the reason this is an evaluation object
        # rather than two unrelated scripts.
        with step("create evaluation"):
            print("\nCreating the evaluation...")
            evaluation = client.evals.create(
                name="Foundry lifecycle accuracy: tools vs. no tools",
                data_source_config=DataSourceConfigCustom(
                    type="custom",
                    item_schema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                    include_sample_schema=True,
                ),
                testing_criteria=build_criteria(rubric),
            )
            print(f"  Evaluation: {evaluation.id}")

        # Start both, then wait. Running them concurrently roughly halves the
        # time you stand there, which matters in an 11-minute section.
        with step("start runs"):
            runs = {
                BARE_AGENT: run_against(client, evaluation, dataset, BARE_AGENT),
                TOOLED_AGENT: run_against(client, evaluation, dataset, TOOLED_AGENT),
            }

        print("\nWaiting for both runs...")
        with step("both runs"):
            results = wait_for_both(client, evaluation, runs)

        print(f"\n\n{'=' * 62}\nSAME QUESTIONS.  SAME RUBRIC.  ONE DIFFERENCE.\n{'=' * 62}")
        scorecard(f"WITHOUT TOOLS   ({BARE_AGENT})", results[BARE_AGENT])
        scorecard(f"WITH REGISTRY   ({TOOLED_AGENT})", results[TOOLED_AGENT])

        print(
            "\nOpen both runs in the portal to show the per-row reasoning.\n"
            "The rubric explains WHY each answer scored what it did, which is\n"
            "the part that makes this usable as a quality gate rather than a\n"
            "vanity metric."
        )

        print(f"\n{'-' * 62}\nTiming")
        for name, seconds in TIMINGS.items():
            print(f"  {name:<34} {clock(seconds):>8}")
        print(f"  {'total':<34} {clock(time.monotonic() - START):>8}")


if __name__ == "__main__":
    main()
