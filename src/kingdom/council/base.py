"""Base classes for Council members."""

from __future__ import annotations

import json
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentResponse:
    """Response from a council member."""

    name: str
    text: str
    error: str | None = None
    elapsed: float = 0.0
    raw: str = ""


@dataclass
class CouncilMember(ABC):
    """Abstract base class for council members."""

    name: str = field(init=False)
    session_id: str | None = None
    log_path: Path | None = None

    @abstractmethod
    def build_command(self, prompt: str) -> list[str]:
        """Build the CLI command to execute."""
        ...

    @abstractmethod
    def parse_response(
        self, stdout: str, stderr: str, code: int
    ) -> tuple[str, str | None, str]:
        """Parse response from CLI output.

        Returns:
            tuple of (text, session_id, raw_output)
        """
        ...

    def query(self, prompt: str, timeout: int = 300) -> AgentResponse:
        """Execute a query and return the response."""
        start = time.monotonic()
        command = self.build_command(prompt)

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            text, new_session_id, raw = self.parse_response(
                result.stdout, result.stderr, result.returncode
            )
            if new_session_id:
                self.session_id = new_session_id

            elapsed = time.monotonic() - start
            error = None
            if result.returncode != 0 and not text:
                error = result.stderr.strip() or f"Exit code {result.returncode}"

            response = AgentResponse(
                name=self.name,
                text=text,
                error=error,
                elapsed=elapsed,
                raw=raw,
            )
            self._log(prompt, text, error, elapsed)
            return response

        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            error = f"Timeout after {timeout}s"
            response = AgentResponse(
                name=self.name,
                text="",
                error=error,
                elapsed=elapsed,
                raw="",
            )
            self._log(prompt, "", error, elapsed)
            return response

        except FileNotFoundError:
            elapsed = time.monotonic() - start
            error = f"Command not found: {command[0]}"
            response = AgentResponse(
                name=self.name,
                text="",
                error=error,
                elapsed=elapsed,
                raw="",
            )
            self._log(prompt, "", error, elapsed)
            return response

    def reset_session(self) -> None:
        """Clear the session ID."""
        self.session_id = None

    def _log(
        self, prompt: str, text: str, error: str | None, elapsed: float
    ) -> None:
        """Log the interaction to the log file."""
        if not self.log_path:
            return

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"[{timestamp}] Query ({elapsed:.1f}s)\n")
            f.write(f"{'='*60}\n")
            f.write(f"PROMPT:\n{prompt}\n\n")
            if error:
                f.write(f"ERROR: {error}\n\n")
            f.write(f"RESPONSE:\n{text}\n")
