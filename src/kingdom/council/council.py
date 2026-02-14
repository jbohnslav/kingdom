"""Council orchestration for multi-agent queries."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from kingdom.agent import DEFAULT_AGENTS, AgentConfig, agents_root, list_agents
from kingdom.session import get_agent_state, update_agent_state

from .base import AgentResponse, CouncilMember


@dataclass
class Council:
    """Orchestrates queries to multiple council members."""

    members: list[CouncilMember] = field(default_factory=list)
    timeout: int = 600

    @classmethod
    def create(cls, logs_dir: Path | None = None, base: Path | None = None) -> Council:
        """Create a council with configured or default members.

        If ``base`` is provided and ``.kd/agents/`` contains agent files,
        those are used. Otherwise falls back to built-in defaults.

        Raises:
            ValueError: If agent files exist but none could be parsed.
        """
        configs: list[AgentConfig] = []
        if base is not None:
            configs = list_agents(base)
            if not configs:
                root = agents_root(base)
                if root.exists() and any(root.glob("*.md")):
                    raise ValueError(
                        f"Agent files in {root} exist but none could be parsed. "
                        "Check .kd/agents/*.md for syntax errors."
                    )

        if not configs:
            configs = list(DEFAULT_AGENTS.values())

        members: list[CouncilMember] = [CouncilMember(config=c) for c in configs]

        if logs_dir:
            for member in members:
                member.log_path = logs_dir / f"council-{member.name}.log"

        return cls(members=members)

    def query(self, prompt: str) -> dict[str, AgentResponse]:
        """Query all members in parallel and return responses."""
        responses: dict[str, AgentResponse] = {}

        with ThreadPoolExecutor(max_workers=len(self.members)) as executor:
            futures = {executor.submit(member.query, prompt, self.timeout): member for member in self.members}

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

    def query_to_thread(
        self,
        prompt: str,
        base: Path,
        branch: str,
        thread_id: str,
        callback: Callable[[str, AgentResponse], None] | None = None,
    ) -> dict[str, AgentResponse]:
        """Query all members, writing each response to a thread as it arrives.

        Args:
            prompt: The query prompt.
            base: Project root.
            branch: Branch name.
            thread_id: Thread ID to write responses to.
            callback: Optional function called with (name, response) as each arrives.

        Returns:
            Dict mapping member name to AgentResponse.
        """
        from kingdom.thread import add_message, thread_dir

        responses: dict[str, AgentResponse] = {}
        tdir = thread_dir(base, branch, thread_id)
        tdir.mkdir(parents=True, exist_ok=True)

        with ThreadPoolExecutor(max_workers=len(self.members)) as executor:
            futures = {}
            for member in self.members:
                # Stream to .stream-{member}.md
                stream_path = tdir / f".stream-{member.name}.md"
                futures[executor.submit(member.query, prompt, self.timeout, stream_path)] = (member, stream_path)

            for future in as_completed(futures):
                member, stream_path = futures[future]
                try:
                    response = future.result()
                except Exception as e:
                    response = AgentResponse(name=member.name, text="", error=str(e), elapsed=0.0, raw="")

                responses[member.name] = response

                # Write to thread
                body = response.text if response.text else f"*Error: {response.error}*"
                add_message(base, branch, thread_id, from_=member.name, to="king", body=body)

                # Cleanup stream file
                if stream_path.exists():
                    stream_path.unlink()

                if callback:
                    callback(member.name, response)

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

    def load_sessions(self, base: Path, branch: str) -> None:
        """Load session IDs from agent state files."""
        for member in self.members:
            state = get_agent_state(base, branch, member.name)
            if state.resume_id:
                member.session_id = state.resume_id

    def save_sessions(self, base: Path, branch: str) -> None:
        """Save session IDs to agent state files."""
        for member in self.members:
            update_agent_state(base, branch, member.name, resume_id=member.session_id)
