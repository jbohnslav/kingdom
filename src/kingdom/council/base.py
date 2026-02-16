"""Base classes for Council members."""

from __future__ import annotations

import subprocess
import threading
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

    def thread_body(self) -> str:
        """Format response for writing to a thread message file.

        Note: partial timeout responses (text + error) return just the text.
        This means retry won't detect them as failures. Acceptable because
        timeouts are non-retriable and users see the timeout in watch output.
        See backlog ticket 9124 for frontmatter metadata approach.
        """
        if self.text:
            text = self.text
            # Strip echoed speaker prefix (agents sometimes echo "name: " from history format)
            prefix = f"{self.name}: "
            if text.startswith(prefix):
                text = text[len(prefix) :]
            return text
        if self.error:
            return f"*Error: {self.error}*"
        return "*Empty response — no text or error returned.*"


@dataclass
class CouncilMember:
    """A council member backed by an agent config."""

    config: AgentConfig
    session_id: str | None = None
    log_path: Path | None = None
    agent_prompt: str = ""  # agent.prompt from config (always additive)
    phase_prompt: str = ""  # resolved phase prompt (agent-specific or global)
    preamble: str = ""  # override for COUNCIL_PREAMBLE (empty = use default)
    process: subprocess.Popen | None = None  # live Popen handle during query
    base: Path | None = None  # project root, for PID tracking in AgentState
    branch: str | None = None  # branch name, for PID tracking in AgentState

    @property
    def name(self) -> str:
        return self.config.name

    COUNCIL_PREAMBLE = (
        "You are a council advisor to the King. "
        "Do NOT create, edit, delete, or write source code, tests, configs, or other project files. "
        "Do NOT run git commands that modify state (commit, push, checkout, etc). "
        "You may run `kd` commands and read any files. "
        "Respond with analysis and recommendations — do not implement anything.\n\n"
    )

    def build_command(self, prompt: str) -> list[str]:
        """Build the CLI command to execute.

        Council queries are read-only, so skip_permissions is False.

        Prompt merge order:
            safety preamble (hardcoded) + phase prompt (agent-specific or global)
            + agent prompt (always additive) + user prompt
        """
        parts = [self.preamble or self.COUNCIL_PREAMBLE]
        if self.phase_prompt:
            parts.append(self.phase_prompt + "\n\n")
        if self.agent_prompt:
            parts.append(self.agent_prompt + "\n\n")
        parts.append(prompt)
        full_prompt = "".join(parts)
        return agent_build_command(self.config, full_prompt, self.session_id, skip_permissions=False, streaming=True)

    def parse_response(self, stdout: str, stderr: str, code: int) -> tuple[str, str | None, str]:
        """Parse response from CLI output.

        Returns:
            tuple of (text, session_id, raw_output)
        """
        return agent_parse_response(self.config, stdout, stderr, code)

    # Errors where retrying won't help — broken CLI, bad config, or slow model
    NON_RETRIABLE_PREFIXES = ("Command not found:", "Invalid agent config:", "Timeout after")

    def query(
        self,
        prompt: str,
        timeout: int = 600,
        stream_path: Path | None = None,
        max_retries: int = 2,
    ) -> AgentResponse:
        """Execute a query with automatic retry on failure.

        Retry strategy (when max_retries >= 2):
          1. First attempt with current session.
          2. If retriable error: retry once with same session.
          3. If still failing: reset session and retry once more.

        Non-retriable errors (command not found, invalid config) fail immediately.

        Args:
            prompt: The query prompt.
            timeout: Per-attempt timeout in seconds.
            stream_path: If set, stdout is tee'd to this file line-by-line.
            max_retries: Max retry attempts (0 = no retries, default 2).
        """
        response = self.query_once(prompt, timeout, stream_path)
        if not response.error or max_retries < 1:
            return response

        # Don't retry non-retriable errors
        if any(response.error.startswith(prefix) for prefix in self.NON_RETRIABLE_PREFIXES):
            return response

        # Retry 1: same session
        if stream_path and stream_path.exists():
            stream_path.unlink()
        self.log_retry(prompt, response, reset_session=False)
        response = self.query_once(prompt, timeout, stream_path)
        if not response.error or max_retries < 2:
            return response

        # Retry 2: reset session
        if stream_path and stream_path.exists():
            stream_path.unlink()
        self.log_retry(prompt, response, reset_session=True)
        self.reset_session()
        return self.query_once(prompt, timeout, stream_path)

    def query_once(self, prompt: str, timeout: int = 600, stream_path: Path | None = None) -> AgentResponse:
        """Execute a single query attempt and return the response."""
        start = time.monotonic()
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        stream_file = None

        def read_stdout(pipe: object) -> None:
            for line in pipe:
                stdout_lines.append(line)
                if stream_file:
                    stream_file.write(line)
                    stream_file.flush()

        def read_stderr(pipe: object) -> None:
            for line in pipe:
                stderr_lines.append(line)

        try:
            command = self.build_command(prompt)

            if stream_path:
                stream_file = stream_path.open("a", encoding="utf-8")

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                stdin=subprocess.DEVNULL,
                env=clean_agent_env(role="council", agent_name=self.name),
            )
            self.process = process

            # Write PID to AgentState for external monitoring
            if self.base and self.branch:
                from kingdom.session import update_agent_state

                update_agent_state(self.base, self.branch, self.name, pid=process.pid)

            out_thread = threading.Thread(target=read_stdout, args=(process.stdout,), daemon=True)
            err_thread = threading.Thread(target=read_stderr, args=(process.stderr,), daemon=True)
            out_thread.start()
            err_thread.start()

            # Wait for process with timeout, polling so threads can collect output
            while process.poll() is None:
                if time.monotonic() - start > timeout:
                    process.kill()
                    process.wait()
                    raise subprocess.TimeoutExpired(command, timeout)
                time.sleep(0.1)

            # Process exited — wait for reader threads to drain pipes
            out_thread.join(timeout=5)
            err_thread.join(timeout=5)

            stdout = "".join(stdout_lines)
            stderr = "".join(stderr_lines)

            text, new_session_id, raw = self.parse_response(stdout, stderr, process.returncode)
            if new_session_id:
                self.session_id = new_session_id

            elapsed = time.monotonic() - start
            error = None
            if process.returncode != 0 and not text:
                error = stderr.strip() or f"Exit code {process.returncode}"
            elif not text and process.returncode == 0:
                # Process exited cleanly but produced no extractable text
                snippet = stderr.strip()[:200] if stderr.strip() else stdout.strip()[:200]
                error = f"Empty response from {self.name}"
                if snippet:
                    error += f": {snippet}"

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

            # Reader threads may still have buffered lines — give them a moment
            out_thread.join(timeout=2)
            err_thread.join(timeout=2)

            partial = "".join(stdout_lines)

            response = AgentResponse(
                name=self.name,
                text=partial,
                error=error,
                elapsed=elapsed,
                raw=partial,
            )
            self.log(prompt, partial, error, elapsed)
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

        finally:
            self.process = None
            if stream_file:
                stream_file.close()

    def reset_session(self) -> None:
        """Clear the session ID."""
        self.session_id = None

    def log_retry(self, prompt: str, failed: AgentResponse, reset_session: bool) -> None:
        """Log a retry attempt."""
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        action = "retry with session reset" if reset_session else "retry with same session"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp}] RETRY ({action}) — previous error: {failed.error}\n")

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
