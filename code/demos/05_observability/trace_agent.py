"""
Demo 5 -- Observability: tracing

Run the agent and capture an end-to-end trace: the model call, the tool
invocations, and any custom functions you decorate.

The point to land on stage: this is **OpenTelemetry**. The spans go to
Application Insights here, but they would go to Datadog, Grafana Tempo,
Jaeger, or Honeycomb just as happily. That is why this also works for agents
you did not build in Foundry -- and it is the strongest single piece of
evidence that lock-in is low at the framework layer.

NOTE: GenAI tracing instrumentation is an EXPERIMENTAL PREVIEW feature.
Spans and attributes may change. Say so on stage.

Run:  uv run python demos/05_observability/trace_agent.py
"""

import os

# Must be set BEFORE importing the instrumentor. If it is missing or not
# "true", instrumentation silently does not engage and you get a warning
# instead of spans -- the single most common reason this demo shows nothing.
os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "true"

# Captures prompts and completions in the spans. Fine for a demo, and exactly
# what you want the audience to see. Do NOT do this in production without
# checking your privacy obligations first -- worth saying out loud.
os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"

# Names this process in the trace. Without it the spans from this script show
# up as "unknown_service" right beside Foundry's own server-side spans, which
# reads badly on a projector. The Azure Monitor exporter sends service.name as
# the cloud role name. setdefault, so a value from the environment still wins.
os.environ.setdefault("OTEL_SERVICE_NAME", "skeptical-developer-demo")

from azure.ai.projects import AIProjectClient  # noqa: E402
from azure.ai.projects.models import PromptAgentDefinition  # noqa: E402
from azure.ai.projects.telemetry import trace_function  # noqa: E402
from azure.identity import DefaultAzureCredential  # noqa: E402
from azure.monitor.opentelemetry import configure_azure_monitor  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from opentelemetry import trace  # noqa: E402

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-5-mini")
AGENT_NAME = os.environ.get("FOUNDRY_AGENT_NAME", "SkepticalDeveloperAgent")


@trace_function("check-platform-maturity")
def check_platform_maturity(platform: str) -> str:
    """A stand-in for your own business logic.

    The decorator puts this on the trace as its own span, with the parameter
    and return value attached. This is how you show the audience that tracing
    covers *your* code, not just the model call.
    """
    return f"{platform}: several load-bearing features still in preview."


def main() -> None:
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project,
    ):
        # Foundry hands you the connection string for the Application Insights
        # resource already attached to the project. No portal copy-paste.
        connection_string = project.telemetry.get_application_insights_connection_string()
        configure_azure_monitor(connection_string=connection_string)

        tracer = trace.get_tracer(__name__)

        # One parent span wrapping the whole scenario, so the trace reads as a
        # single unit in the portal rather than a scatter of orphans.
        with tracer.start_as_current_span("skeptical-developer-scenario"):
            with project.get_openai_client() as openai:
                agent = project.agents.create_version(
                    agent_name=AGENT_NAME,
                    definition=PromptAgentDefinition(
                        model=MODEL,
                        instructions=(
                            "You are a blunt technical advisor. Answer in at "
                            "most three sentences."
                        ),
                    ),
                )
                print(f"Agent: {agent.name} (version {agent.version})")

                # Your own code, traced alongside the model call.
                finding = check_platform_maturity("Microsoft Foundry")
                print(f"Local check: {finding}")

                conversation = openai.conversations.create()
                response = openai.responses.create(
                    conversation=conversation.id,
                    # agent_reference is what ties the trace to this agent in
                    # the portal. Leave it out and the trace still records,
                    # but it will not be attributed to the agent.
                    extra_body={
                        "agent_reference": {
                            "name": agent.name,
                            "id": agent.id,
                            "type": "agent_reference",
                        }
                    },
                    input=f"Given this finding, should I adopt it? {finding}",
                )
                print(f"\nResponse: {response.output_text}")

                openai.conversations.delete(conversation_id=conversation.id)

    print(
        "\nTrace sent. It takes 2-5 minutes to appear in the Foundry portal's "
        "Traces view.\nRun this at the START of the section and come back to it."
    )


if __name__ == "__main__":
    main()
