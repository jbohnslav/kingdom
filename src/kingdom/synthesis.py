"""Synthesis prompt builder for Hand-as-synthesizer pattern."""

from __future__ import annotations

from kingdom.council.base import AgentResponse


def build_synthesis_prompt(
    user_prompt: str,
    responses: dict[str, AgentResponse],
    member_names: list[str] | None = None,
) -> str:
    if member_names is None:
        member_names = list(responses)

    parts = [
        f'The user asked: "{user_prompt}"',
        "",
        "I consulted my advisors. Here are their responses:",
    ]

    for name in member_names:
        resp = responses.get(name)
        parts.append(f"\n=== {name.title()} ===")
        if resp and resp.text:
            parts.append(resp.text)
        elif resp and resp.error:
            parts.append(f"[Failed: {resp.error}]")
        else:
            parts.append("[No response]")

    parts.append("")
    parts.append("Synthesize these perspectives into a unified response for the user.")
    parts.append("Consider:")
    parts.append("- Points of agreement across advisors")
    parts.append("- Unique insights from each")
    parts.append("- Any contradictions to resolve")
    parts.append("- The most actionable recommendation")
    parts.append("")
    parts.append("Respond directly to the user (don't mention 'the advisors' explicitly).")

    return "\n".join(parts)
