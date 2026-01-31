"""Council orchestration for multi-agent queries."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from .base import AgentResponse, CouncilMember
from .claude import ClaudeMember
from .codex import CodexMember
from .cursor import CursorAgentMember


@dataclass
class Council:
    """Orchestrates queries to multiple council members."""

    members: list[CouncilMember] = field(default_factory=list)
    timeout: int = 300

    @classmethod
    def create(cls, logs_dir: Path | None = None) -> Council:
        """Create a council with default members."""
        members: list[CouncilMember] = [
            ClaudeMember(),
            CodexMember(),
            CursorAgentMember(),
        ]

        if logs_dir:
            for member in members:
                member.log_path = logs_dir / f"council-{member.name}.log"

        return cls(members=members)

    def query(self, prompt: str) -> dict[str, AgentResponse]:
        """Query all members in parallel and return responses."""
        responses: dict[str, AgentResponse] = {}

        with ThreadPoolExecutor(max_workers=len(self.members)) as executor:
            futures = {
                executor.submit(member.query, prompt, self.timeout): member
                for member in self.members
            }

            for future in as_completed(futures):
                member = futures[future]
                try:
                    response = future.result()
                    responses[member.name] = response
                except Exception as e:
                    responses[member.name] = AgentResponse(
                        name=member.name,
                        text="",
                        error=str(e),
                        elapsed=0.0,
                        raw="",
                    )

        return responses

    def reset_sessions(self) -> None:
        """Reset all member sessions."""
        for member in self.members:
            member.reset_session()

    def get_member(self, name: str) -> CouncilMember | None:
        """Get a member by name."""
        for member in self.members:
            if member.name == name:
                return member
        return None

    def load_sessions(self, sessions_dir: Path) -> None:
        """Load session IDs from files."""
        if not sessions_dir.exists():
            return

        for member in self.members:
            session_file = sessions_dir / f"{member.name}.session"
            if session_file.exists():
                content = session_file.read_text(encoding="utf-8").strip()
                if content:
                    member.session_id = content

    def save_sessions(self, sessions_dir: Path) -> None:
        """Save session IDs to files."""
        sessions_dir.mkdir(parents=True, exist_ok=True)

        for member in self.members:
            session_file = sessions_dir / f"{member.name}.session"
            if member.session_id:
                session_file.write_text(f"{member.session_id}\n", encoding="utf-8")
            elif session_file.exists():
                session_file.unlink()
