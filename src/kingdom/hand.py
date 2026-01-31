"""Hand orchestrator: dispatch prompts to Council and display responses."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from kingdom.council import Council, AgentResponse
from kingdom.state import (
    append_jsonl,
    ensure_run_layout,
    logs_root,
    resolve_current_run,
    sessions_root,
)


COUNCIL_MODELS = ["claude", "codex", "agent"]


def format_response(response: AgentResponse) -> str:
    """Format a single agent response for display."""
    header = f"[{response.name}] ({response.elapsed:.1f}s)"
    lines = [header]
    if response.error:
        lines.append(f"ERROR: {response.error}")
    if response.text:
        lines.append(response.text)
    return "\n".join(lines)


def synthesize(prompt: str, responses: dict[str, AgentResponse]) -> str:
    """Format all responses for display."""
    header = ["SYNTHESIS (MVP)", "", f"Prompt: {prompt}", ""]
    parts = []
    for model in COUNCIL_MODELS:
        response = responses.get(model)
        if response:
            parts.append(format_response(response))
        else:
            parts.append(f"[{model}]")
            parts.append("No response")
        parts.append("")
    return "\n".join(header + parts).strip()


def main() -> None:
    base = Path.cwd()
    feature = resolve_current_run(base)
    paths = ensure_run_layout(base, feature)

    logs_dir = logs_root(base, feature)
    sessions_dir = sessions_root(base, feature)
    hand_log = logs_dir / "hand.jsonl"

    # Create council and load any existing sessions
    council = Council.create(logs_dir=logs_dir)
    council.load_sessions(sessions_dir)

    print(f"Hand ready. Council members: {', '.join(m.name for m in council.members)}")
    print("Commands: /reset (clear sessions), exit/quit (leave)")
    print()

    while True:
        try:
            prompt = input("hand> ").strip()
        except EOFError:
            break
        except KeyboardInterrupt:
            print()
            continue

        if not prompt:
            continue

        # Handle commands
        if prompt.lower() in {"exit", "quit"}:
            break

        if prompt.lower() == "/reset":
            council.reset_sessions()
            council.save_sessions(sessions_dir)
            print("Sessions cleared.")
            continue

        if prompt.startswith("/"):
            print(f"Unknown command: {prompt}")
            continue

        # Query council
        request_id = uuid4().hex
        responses = council.query(prompt)
        council.save_sessions(sessions_dir)

        # Display results
        synthesis = synthesize(prompt, responses)
        print(synthesis)

        # Log to hand.jsonl
        log_record = {
            "id": request_id,
            "prompt": prompt,
            "responses": {
                name: {
                    "text": r.text,
                    "error": r.error,
                    "elapsed": r.elapsed,
                }
                for name, r in responses.items()
            },
            "synthesis": synthesis,
        }
        append_jsonl(hand_log, log_record)


if __name__ == "__main__":
    main()
