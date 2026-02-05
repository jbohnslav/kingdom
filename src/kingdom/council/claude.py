"""Claude CLI council member."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .base import CouncilMember


@dataclass
class ClaudeMember(CouncilMember):
    """Council member using Claude CLI."""

    name: str = field(default="claude", init=False)

    def build_command(self, prompt: str) -> list[str]:
        """Build claude CLI command.

        Note: Use --resume (not --continue) to resume a specific session.
        --continue just continues the most recent conversation in the directory.
        --resume must come before -p for proper argument parsing.
        """
        cmd = ["claude", "--print", "--output-format", "json"]
        if self.session_id:
            cmd.extend(["--resume", self.session_id])
        cmd.extend(["-p", prompt])
        return cmd

    def parse_response(
        self, stdout: str, stderr: str, code: int
    ) -> tuple[str, str | None, str]:
        """Parse claude CLI JSON output.

        Expected format:
        {
            "result": "response text",
            "session_id": "abc123"
        }
        """
        raw = stdout
        try:
            data = json.loads(stdout)
            if not isinstance(data, dict):
                return stdout.strip(), None, raw
            text = data.get("result", "")
            session_id = data.get("session_id")
            return text, session_id, raw
        except json.JSONDecodeError:
            # Fall back to raw stdout if JSON parsing fails
            return stdout.strip(), None, raw
