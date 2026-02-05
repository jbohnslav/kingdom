"""Codex CLI council member."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .base import CouncilMember


@dataclass
class CodexMember(CouncilMember):
    """Council member using Codex CLI.

    Codex uses JSONL output (--json) and session resumption via:
    - First call: `codex exec --json "prompt"`
    - Resume: `codex exec resume <thread_id> --json "prompt"`
    """

    name: str = field(default="codex", init=False)

    def build_command(self, prompt: str) -> list[str]:
        """Build codex CLI command."""
        if self.session_id:
            # Resume existing session
            return ["codex", "exec", "resume", self.session_id, "--json", prompt]
        else:
            # New session
            return ["codex", "exec", "--json", prompt]

    def parse_response(
        self, stdout: str, stderr: str, code: int
    ) -> tuple[str, str | None, str]:
        """Parse codex JSONL output.

        Extracts:
        - thread_id from {"type":"thread.started","thread_id":"..."}
        - response text from {"type":"item.completed","item":{"type":"agent_message","text":"..."}}
        """
        raw = stdout
        thread_id = None
        text_parts = []

        for line in stdout.strip().split("\n"):
            if not line:
                continue
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    continue

                event_type = event.get("type")

                if event_type == "thread.started":
                    thread_id = event.get("thread_id")

                elif event_type == "item.completed":
                    item = event.get("item", {})
                    if item.get("type") == "agent_message":
                        text = item.get("text", "")
                        if text:
                            text_parts.append(text)

            except json.JSONDecodeError:
                continue

        return "\n".join(text_parts), thread_id, raw
