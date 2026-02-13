"""Base classes for Council members."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from kingdom.agent import AgentConfig, clean_agent_env
from kingdom.agent import build_command as agent_build_command
from kingdom.agent import parse_response as agent_parse_response


@dataclass
class AgentResponse:
    """Response from a council member."""

    name: str
    text: str
    error: str | None = None
    elapsed: float = 0.0
    raw: str = ""


@dataclass
class CouncilMember:
    """A council member backed by an agent config."""

    config: AgentConfig
    session_id: str | None = None
    log_path: Path | None = None

    @property
    def name(self) -> str:
        return self.config.name

    COUNCIL_PREAMBLE = (
        "You are a council advisor to the King. Your role is read-only unless directly commanded otherwise. "
        "Answer questions, analyze code, and provide recommendations. "
        "You may read any file in the codebase. "
        "If you need the design doc, run `kd design` to find it. "
        "Do NOT modify source code, tests, configs, or any other files unless the King explicitly asks you to.\n\n"
    )

    def build_command(self, prompt: str) -> list[str]:
        """Build the CLI command to execute.

        Council queries are read-only, so skip_permissions is False.
        The prompt is prefixed with council constraints.
        """
        full_prompt = self.COUNCIL_PREAMBLE + prompt
        return agent_build_command(self.config, full_prompt, self.session_id, skip_permissions=False)

    def parse_response(self, stdout: str, stderr: str, code: int) -> tuple[str, str | None, str]:
        """Parse response from CLI output.

        Returns:
            tuple of (text, session_id, raw_output)
        """
        return agent_parse_response(self.config, stdout, stderr, code)

    def query(self, prompt: str, timeout: int = 300) -> AgentResponse:
        """Execute a query and return the response."""
        start = time.monotonic()

        try:
            command = self.build_command(prompt)
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                env=clean_agent_env(),
            )
            text, new_session_id, raw = self.parse_response(result.stdout, result.stderr, result.returncode)
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
            self.log(prompt, text, error, elapsed)
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
            self.log(prompt, "", error, elapsed)
            return response

        except FileNotFoundError:
            elapsed = time.monotonic() - start
            cmd_name = self.config.cli.split()[0] if self.config.cli else "unknown"
            error = f"Command not found: {cmd_name}"
            response = AgentResponse(
                name=self.name,
                text="",
                error=error,
                elapsed=elapsed,
                raw="",
            )
            self.log(prompt, "", error, elapsed)
            return response

        except ValueError as e:
            elapsed = time.monotonic() - start
            error = f"Invalid agent config: {e}"
            response = AgentResponse(
                name=self.name,
                text="",
                error=error,
                elapsed=elapsed,
                raw="",
            )
            self.log(prompt, "", error, elapsed)
            return response

    def reset_session(self) -> None:
        """Clear the session ID."""
        self.session_id = None

    def log(self, prompt: str, text: str, error: str | None, elapsed: float) -> None:
        """Log the interaction to the log file."""
        if not self.log_path:
            return

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"[{timestamp}] Query ({elapsed:.1f}s)\n")
            f.write(f"{'=' * 60}\n")
            f.write(f"PROMPT:\n{prompt}\n\n")
            if error:
                f.write(f"ERROR: {error}\n\n")
            f.write(f"RESPONSE:\n{text}\n")
