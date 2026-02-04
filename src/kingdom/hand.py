"""Hand orchestrator: AI session that synthesizes Council responses."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from kingdom.council import Council, AgentResponse
from kingdom.breakdown import (
    build_breakdown_council_prompt,
    build_breakdown_update_prompt,
    ensure_breakdown_initialized,
    parse_breakdown_update_response,
    read_breakdown,
    write_breakdown,
)
from kingdom.design import (
    build_design_council_prompt,
    build_design_update_prompt,
    ensure_design_initialized,
    parse_design_update_response,
    read_design,
    write_design,
)
from kingdom.state import (
    append_jsonl,
    ensure_run_layout,
    hand_session_path,
    logs_root,
    resolve_current_run,
    sessions_root,
)
from kingdom.synthesis import build_synthesis_prompt


@dataclass
class HandSession:
    """The Hand as a Claude session with conversation continuity."""

    session_id: str | None = None
    log_path: Path | None = None

    def query(self, prompt: str, timeout: int = 300) -> AgentResponse:
        """Send prompt to Hand's Claude session."""
        start = time.monotonic()
        cmd = ["claude", "--print", "--output-format", "json"]
        if self.session_id:
            cmd.extend(["--resume", self.session_id])
        cmd.extend(["-p", prompt])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            text, new_session_id, raw = self._parse_response(
                result.stdout, result.stderr, result.returncode
            )
            if new_session_id:
                self.session_id = new_session_id

            elapsed = time.monotonic() - start
            error = None
            if result.returncode != 0 and not text:
                error = result.stderr.strip() or f"Exit code {result.returncode}"

            return AgentResponse(
                name="hand",
                text=text,
                error=error,
                elapsed=elapsed,
                raw=raw,
            )

        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            return AgentResponse(
                name="hand",
                text="",
                error=f"Timeout after {timeout}s",
                elapsed=elapsed,
                raw="",
            )

        except FileNotFoundError:
            elapsed = time.monotonic() - start
            return AgentResponse(
                name="hand",
                text="",
                error="Command not found: claude",
                elapsed=elapsed,
                raw="",
            )

    def _parse_response(
        self, stdout: str, stderr: str, code: int
    ) -> tuple[str, str | None, str]:
        """Parse claude CLI JSON output."""
        raw = stdout
        try:
            data = json.loads(stdout)
            if not isinstance(data, dict):
                return stdout.strip(), None, raw
            text = data.get("result", "")
            session_id = data.get("session_id")
            return text, session_id, raw
        except json.JSONDecodeError:
            return stdout.strip(), None, raw

    def reset_session(self) -> None:
        """Clear the session ID."""
        self.session_id = None

    def load_session(self, session_file: Path) -> None:
        """Load session ID from file."""
        if session_file.exists():
            content = session_file.read_text(encoding="utf-8").strip()
            if content:
                self.session_id = content

    def save_session(self, session_file: Path) -> None:
        """Save session ID to file."""
        session_file.parent.mkdir(parents=True, exist_ok=True)
        if self.session_id:
            session_file.write_text(f"{self.session_id}\n", encoding="utf-8")
        elif session_file.exists():
            session_file.unlink()


class Spinner:
    """Simple spinner for progress indication."""

    def __init__(self, message: str):
        self.message = message
        self.running = False
        self.thread: threading.Thread | None = None

    def _spin(self) -> None:
        chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        i = 0
        while self.running:
            sys.stdout.write(f"\r{chars[i % len(chars)]} {self.message}")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1
        # Clear the line
        sys.stdout.write("\r" + " " * (len(self.message) + 3) + "\r")
        sys.stdout.flush()

    def __enter__(self) -> "Spinner":
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.running = False
        if self.thread:
            self.thread.join()


def format_council_response(response: AgentResponse) -> str:
    """Format a single council response for verbose display."""
    header = f"[{response.name}] ({response.elapsed:.1f}s)"
    lines = [header]
    if response.error:
        lines.append(f"ERROR: {response.error}")
    if response.text:
        lines.append(response.text)
    return "\n".join(lines)


def print_council_responses(responses: dict[str, AgentResponse]) -> None:
    """Print all council responses for verbose mode."""
    print("\n--- Council Responses ---")
    for name in ["claude", "codex", "agent"]:
        resp = responses.get(name)
        if resp:
            print(format_council_response(resp))
        else:
            print(f"[{name}]")
            print("No response")
        print()
    print("--- End Council Responses ---\n")


def main() -> None:
    base = Path.cwd()
    feature = resolve_current_run(base)
    paths = ensure_run_layout(base, feature)

    logs_dir = logs_root(base, feature)
    sessions_dir = sessions_root(base, feature)
    hand_log = logs_dir / "hand.jsonl"
    hand_session_file = hand_session_path(base, feature)
    design_path = paths["design_md"]
    breakdown_path = paths["breakdown_md"]

    # Create Hand session and load existing session
    hand = HandSession(log_path=hand_log)
    hand.load_session(hand_session_file)

    # Create council and load any existing sessions
    council = Council.create(logs_dir=logs_dir)
    council.load_sessions(sessions_dir)

    # Track last council responses for /verbose command
    last_council_responses: dict[str, AgentResponse] = {}
    verbose_mode = False
    active_mode: str | None = None

    print(f"Hand ready. Council members: {', '.join(m.name for m in council.members)}")
    print("Commands: /verbose (toggle), /reset, /design, /breakdown, exit/quit")
    print()

    while True:
        try:
            prompt = input("you> ").strip()
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

        if prompt.lower() == "/verbose":
            verbose_mode = not verbose_mode
            print(f"Verbose mode {'enabled' if verbose_mode else 'disabled'}.")
            continue

        if prompt.lower() == "/reset":
            hand.reset_session()
            hand.save_session(hand_session_file)
            council.reset_sessions()
            council.save_sessions(sessions_dir)
            last_council_responses = {}
            print("All sessions cleared.")
            continue

        if prompt.lower().startswith("/design"):
            cmd = prompt.strip().lower()
            if cmd in {"/design", "/design on"}:
                active_mode = "design"
                current = ensure_design_initialized(design_path, feature=feature)
                print(f"Design mode enabled. Editing: {design_path}")
                print("Commands: /design show, /design off, /design approve")
                print()
                print(current.rstrip())
                print()
                continue

            if cmd == "/design show":
                current = ensure_design_initialized(design_path, feature=feature)
                print(current.rstrip())
                print()
                continue

            if cmd in {"/design off", "/design exit"}:
                active_mode = None
                print("Design mode disabled.")
                continue

            if cmd == "/design approve":
                active_mode = "breakdown"
                ensure_design_initialized(design_path, feature=feature)
                current = ensure_breakdown_initialized(breakdown_path, feature=feature)
                print("Design marked approved. Switching to Breakdown mode.")
                print(f"Breakdown mode enabled. Editing: {breakdown_path}")
                print(f"Design source: {design_path}")
                print("Commands: /breakdown show, /breakdown off, /breakdown approve")
                print()
                print(current.rstrip())
                print()
                continue

            print(f"Unknown design command: {prompt}")
            continue

        if prompt.lower().startswith("/breakdown"):
            cmd = prompt.strip()
            if cmd.lower() in {"/breakdown", "/breakdown on"}:
                active_mode = "breakdown"
                ensure_design_initialized(design_path, feature=feature)
                current = ensure_breakdown_initialized(breakdown_path, feature=feature)
                print(f"Breakdown mode enabled. Editing: {breakdown_path}")
                print(f"Design source: {design_path}")
                print("Commands: /breakdown show, /breakdown off, /breakdown approve")
                print()
                print(current.rstrip())
                print()
                continue

            if cmd.lower() == "/breakdown show":
                current = ensure_breakdown_initialized(breakdown_path, feature=feature)
                print(current.rstrip())
                print()
                continue

            if cmd.lower() in {"/breakdown off", "/breakdown exit"}:
                active_mode = None
                print("Breakdown mode disabled.")
                continue

            if cmd.lower() == "/breakdown approve":
                active_mode = None
                print("Breakdown marked approved. Breakdown mode disabled.")
                continue

            print(f"Unknown breakdown command: {prompt}")
            continue

        if prompt.startswith("/"):
            print(f"Unknown command: {prompt}")
            continue

        current_design = read_design(design_path)
        current_breakdown = read_breakdown(breakdown_path)

        if active_mode == "design":
            council_prompt = build_design_council_prompt(
                feature=feature, instruction=prompt, design_text=current_design
            )
        elif active_mode == "breakdown":
            council_prompt = build_breakdown_council_prompt(
                feature=feature,
                instruction=prompt,
                design_text=current_design,
                breakdown_text=current_breakdown,
            )
        else:
            council_prompt = prompt

        # Query council
        request_id = uuid4().hex
        with Spinner("Consulting advisors..."):
            council_responses = council.query(council_prompt)
        council.save_sessions(sessions_dir)
        last_council_responses = council_responses

        # Show individual responses if verbose mode is on
        if verbose_mode:
            print_council_responses(council_responses)

        # Build Hand prompt and query Hand
        if active_mode == "design":
            hand_prompt_type = "design_update"
            hand_prompt = build_design_update_prompt(
                feature=feature,
                instruction=prompt,
                design_text=current_design,
                responses=council_responses,
            )
            with Spinner("Updating design.md..."):
                hand_response = hand.query(hand_prompt)
        elif active_mode == "breakdown":
            hand_prompt_type = "breakdown_update"
            hand_prompt = build_breakdown_update_prompt(
                feature=feature,
                instruction=prompt,
                design_text=current_design,
                breakdown_text=current_breakdown,
                responses=council_responses,
            )
            with Spinner("Updating breakdown.md..."):
                hand_response = hand.query(hand_prompt)
        else:
            hand_prompt_type = "synthesis"
            hand_prompt = build_synthesis_prompt(prompt, council_responses)
            with Spinner("Synthesizing..."):
                hand_response = hand.query(hand_prompt)
        hand.save_session(hand_session_file)

        if active_mode == "design" and hand_response.text and not hand_response.error:
            try:
                update = parse_design_update_response(hand_response.text)
                write_design(design_path, update.markdown)
                print(update.summary.strip() or f"Updated {design_path}")
                print()
                print(read_design(design_path).rstrip())
                print()
            except ValueError as exc:
                print(f"[Design Parse Error] {exc}")
                print(hand_response.text)
                print()
        elif active_mode == "breakdown" and hand_response.text and not hand_response.error:
            try:
                update = parse_breakdown_update_response(hand_response.text)
                write_breakdown(breakdown_path, update.markdown)
                print(update.summary.strip() or f"Updated {breakdown_path}")
                print()
                print(read_breakdown(breakdown_path).rstrip())
                print()
            except ValueError as exc:
                print(f"[Breakdown Parse Error] {exc}")
                print(hand_response.text)
                print()
        else:
            # Display synthesized response
            if hand_response.error:
                print(f"[Hand Error] {hand_response.error}")
            if hand_response.text:
                print(hand_response.text)
            print()

        # Log to hand.jsonl
        log_record = {
            "id": request_id,
            "user_prompt": prompt,
            "council_responses": {
                name: {
                    "text": r.text,
                    "error": r.error,
                    "elapsed": r.elapsed,
                }
                for name, r in council_responses.items()
            },
            "hand_prompt_type": hand_prompt_type,
            "hand_prompt": hand_prompt,
            "hand_response": {
                "text": hand_response.text,
                "error": hand_response.error,
                "elapsed": hand_response.elapsed,
            },
            "design_path": str(design_path),
            "breakdown_path": str(breakdown_path),
            "active_mode": active_mode,
        }
        append_jsonl(hand_log, log_record)


if __name__ == "__main__":
    main()
