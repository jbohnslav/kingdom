"""Cursor Agent CLI council member."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .base import CouncilMember


@dataclass
class CursorAgentMember(CouncilMember):
    """Council member using Cursor Agent CLI."""

    name: str = field(default="agent", init=False)

    def build_command(self, prompt: str) -> list[str]:
        """Build cursor agent CLI command.

        Note: --print is required for non-interactive use, prompt is positional.
        """
        cmd = ["cursor", "agent", "--print", "--output-format", "json", prompt]
        if self.session_id:
            cmd.extend(["--resume", self.session_id])
        return cmd

    def parse_response(
        self, stdout: str, stderr: str, code: int
    ) -> tuple[str, str | None, str]:
        """Parse cursor agent CLI JSON output.

        Expected format varies, handle multiple possibilities:
        {
            "text": "...",
            "conversation_id": "..."
        }
        or
        {
            "response": "...",
            "session_id": "..."
        }
        """
        raw = stdout
        try:
            data = json.loads(stdout)
            if not isinstance(data, dict):
                return stdout.strip(), None, raw
            # Cursor uses "result" for response text (primary), fallback to others
            text = data.get("result") or data.get("text") or data.get("response") or ""
            # Cursor uses "session_id" (primary), fallback to conversation_id
            session_id = data.get("session_id") or data.get("conversation_id")
            return text, session_id, raw
        except json.JSONDecodeError:
            # Fall back to raw stdout if JSON parsing fails
            return stdout.strip(), None, raw
