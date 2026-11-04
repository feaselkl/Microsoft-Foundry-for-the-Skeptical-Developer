"""
Demo 5 -- Observability: continuous evaluation, for the screenshot.

evaluate.py scores a fixed test set before release. Continuous evaluation scores
LIVE traffic after release: a rule fires every time the agent completes a
response, and the scores land in Application Insights next to the traces. A
conference room has no live traffic, so the talk shows a screenshot -- and this
script manufactures the traffic that screenshot needs.

What it does:
  1. Creates an evaluation over the agent's responses, plus a continuous
     evaluation rule that runs it on every completed response from one agent.
     Re-running reuses the existing rule instead of creating another.
  2. Sends the twelve demo-5 questions through that agent, one conversation
     each, so the "live traffic" is the same questions the room just saw.
  3. Waits for the continuous runs to come back and prints what they found.

Then take the screenshot: Build -> open the agent -> Monitor tab.

Prerequisites:
    ./infra/setup.sh       # connects App Insights, grants the project Foundry User
    uv run python demos/04_agents/agent_with_mcp.py    # creates the agent

Run:  uv run python demos/05_observability/continuous_eval.py
      uv run python demos/05_observability/continuous_eval.py --questions 4
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AzureAIDataSourceConfig,
    ContinuousEvaluationRuleAction,
    EvaluationRule,
    EvaluationRuleEventType,
    EvaluationRuleFilter,
    TestingCriterionAzureAIEvaluator,
)
from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from openai import APITimeoutError

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-5-mini")
AGENT = os.environ.get("FOUNDRY_TOOLED_AGENT_NAME", "SkepticWithRegistry")
RULE_ID = "skeptic-continuous-eval"
DATA_FILE = Path(__file__).parent / "eval_data" / "foundry_questions.jsonl"
WAIT_SECONDS = 600


def is_not_found(error: HttpResponseError) -> bool:
    # Missing rules come back as a generic UserError rather than a 404 type,
    # so check the status and the message both.
    return error.status_code == 404 or "not found" in str(error).lower()


def ensure_rule(project, client) -> str:
    """Return the eval id the rule runs, creating the eval and rule if needed."""
    try:
        rule = project.evaluation_rules.get(RULE_ID)
        print(f"Reusing continuous evaluation rule '{RULE_ID}' (eval {rule.action.eval_id})")
        return rule.action.eval_id
    except HttpResponseError as error:
        if not is_not_found(error):
            raise

    print(f"Creating a continuous evaluation for '{AGENT}'...")
    evaluation = client.evals.create(
        name=f"Continuous evaluation: {AGENT}",
        # "responses" scenario: score each response the agent completes.
        data_source_config=AzureAIDataSourceConfig(type="azure_ai_source", scenario="responses"),
        testing_criteria=[
            # A quality judge and a safety check, so the dashboard shows both
            # kinds of score beside latency and token usage.
            TestingCriterionAzureAIEvaluator(
                type="azure_ai_evaluator",
                name="Coherence",
                evaluator_name="builtin.coherence",
                initialization_parameters={"deployment_name": MODEL},
            ),
            TestingCriterionAzureAIEvaluator(
                type="azure_ai_evaluator",
                name="Violence",
                evaluator_name="builtin.violence",
            ),
        ],
    )
    project.evaluation_rules.create_or_update(
        id=RULE_ID,
        evaluation_rule=EvaluationRule(
            display_name="Skeptic continuous evaluation",
            description=f"Scores every completed response from {AGENT}",
            action=ContinuousEvaluationRuleAction(eval_id=evaluation.id, max_hourly_runs=100),
            event_type=EvaluationRuleEventType.RESPONSE_COMPLETED,
            filter=EvaluationRuleFilter(agent_name=AGENT),
            enabled=True,
        ),
    )
    print(f"  Evaluation {evaluation.id}, rule '{RULE_ID}'")
    return evaluation.id


def send_traffic(client, agent, questions: list[str]) -> int:
    """One conversation per question, the way separate employees would ask."""
    sent = 0
    for i, question in enumerate(questions, 1):
        conversation = client.conversations.create(
            items=[{"type": "message", "role": "user", "content": question}],
        )
        try:
            client.responses.create(
                conversation=conversation.id,
                extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
                timeout=120,
            )
            sent += 1
            print(f"  [{i:>2}/{len(questions)}] {question}")
        except APITimeoutError:
            print(f"  [{i:>2}/{len(questions)}] TIMED OUT: {question}")
    return sent


def wait_for_runs(client, eval_id: str, since: int, expected: int) -> list:
    """Poll for continuous runs created after `since` until `expected` finish."""
    began = time.monotonic()
    last_count = -1
    while time.monotonic() - began < WAIT_SECONDS:
        runs = [r for r in client.evals.runs.list(eval_id=eval_id, order="desc", limit=50)
                if (r.created_at or 0) >= since]
        done = [r for r in runs if r.status in ("completed", "failed", "canceled")]
        if len(done) != last_count:
            print(f"  {len(done)} of {expected} scored after {int(time.monotonic() - began)}s")
            last_count = len(done)
        if len(done) >= expected:
            return done
        time.sleep(15)
    print(f"  Stopped waiting after {WAIT_SECONDS}s; runs can keep arriving after this.")
    return [r for r in client.evals.runs.list(eval_id=eval_id, order="desc", limit=50)
            if (r.created_at or 0) >= since and r.status in ("completed", "failed", "canceled")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--questions", type=int, default=12, help="how many questions to send (default 12)")
    args = parser.parse_args()

    questions = [json.loads(line)["query"] for line in DATA_FILE.read_text().splitlines() if line.strip()]
    questions = questions[: max(1, args.questions)]

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project,
        project.get_openai_client() as client,
    ):
        try:
            agent = project.agents.get(agent_name=AGENT)
        except HttpResponseError as error:
            if not is_not_found(error):
                raise
            sys.exit(f"ERROR: agent '{AGENT}' not found. Run demos/04_agents/agent_with_mcp.py first.")

        eval_id = ensure_rule(project, client)

        since = int(time.time()) - 5
        print(f"\nSending {len(questions)} questions to '{AGENT}' as live traffic...")
        sent = send_traffic(client, agent, questions)

        print("\nWaiting for continuous evaluation to score them...")
        runs = wait_for_runs(client, eval_id, since, sent)

        failed = [r for r in runs if r.status != "completed"]
        totals: dict[str, list[int]] = {}
        for run in runs:
            for c in (run.model_dump().get("per_testing_criteria_results") or []):
                t = totals.setdefault(c.get("testing_criteria", "?"), [0, 0])
                t[0] += c.get("passed") or 0
                t[1] += c.get("failed") or 0
        print(f"\n{len(runs)} responses scored, {len(failed)} runs did not complete")
        for name, (passed, failed_n) in totals.items():
            print(f"  {name:<12} passed {passed}  failed {failed_n}")

        report = next((r.report_url for r in runs if getattr(r, "report_url", None)), None)
        if report:
            # Microsoft's sample trims run/<id> to land on the evaluation's page.
            print(f"\nEvaluation page: {'/'.join(report.split('/')[:-2])}")
        print(f"\nScreenshot: Build -> open '{AGENT}' -> Monitor tab. Charts can lag the runs by a few minutes.")
        if failed:
            print("If runs failed with an authorization error, the project's Foundry User role may still be\n"
                  "propagating. Wait a few minutes and re-run; the rule is reused.")


if __name__ == "__main__":
    main()
