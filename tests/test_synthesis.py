"""Tests for synthesis prompt generation."""

from kingdom.council import AgentResponse
from kingdom.synthesis import build_synthesis_prompt


class TestSynthesis:
    def test_build_synthesis_prompt_basic(self) -> None:
        """Test basic prompt construction with valid responses."""
        responses = {
            "claude": AgentResponse(name="claude", text="Claude response", elapsed=1.0),
            "codex": AgentResponse(name="codex", text="Codex response", elapsed=1.0),
            "agent": AgentResponse(name="agent", text="Agent response", elapsed=1.0),
        }
        prompt = build_synthesis_prompt("Hello", responses)

        assert 'The user asked: "Hello"' in prompt
        assert "=== Claude ===" in prompt
        assert "Claude response" in prompt
        assert "=== Codex ===" in prompt
        assert "Codex response" in prompt
        assert "=== Agent ===" in prompt
        assert "Agent response" in prompt
        assert "Synthesize these perspectives" in prompt

    def test_build_synthesis_prompt_with_errors(self) -> None:
        """Test prompt construction when some agents fail."""
        responses = {
            "claude": AgentResponse(name="claude", text="", error="Timeout", elapsed=1.0),
            "codex": AgentResponse(name="codex", text="Codex response", elapsed=1.0),
        }
        prompt = build_synthesis_prompt("Hello", responses)

        assert "=== Claude ===" in prompt
        assert "[Failed: Timeout]" in prompt
        assert "=== Codex ===" in prompt
        assert "Codex response" in prompt

    def test_build_synthesis_prompt_missing_agents(self) -> None:
        """Test prompt construction when some members have no response."""
        members = ["claude", "codex", "agent"]
        responses = {
            "claude": AgentResponse(name="claude", text="Claude response", elapsed=1.0),
        }
        prompt = build_synthesis_prompt("Hello", responses, member_names=members)

        assert "=== Claude ===" in prompt
        assert "Claude response" in prompt
        assert "=== Codex ===" in prompt
        assert "[No response]" in prompt
        assert "=== Agent ===" in prompt
        assert "[No response]" in prompt

    def test_build_synthesis_prompt_empty_responses(self) -> None:
        """Test prompt construction with empty responses and explicit members."""
        members = ["claude", "codex", "agent"]
        prompt = build_synthesis_prompt("Hello", {}, member_names=members)

        assert 'The user asked: "Hello"' in prompt
        assert "=== Claude ===" in prompt
        assert "=== Codex ===" in prompt
        assert "=== Agent ===" in prompt
        assert prompt.count("[No response]") == 3

    def test_build_synthesis_prompt_council_order(self) -> None:
        """Test that council members appear in the order specified by member_names."""
        members = ["claude", "codex", "agent"]
        responses = {
            "agent": AgentResponse(name="agent", text="Agent response", elapsed=1.0),
            "claude": AgentResponse(name="claude", text="Claude response", elapsed=1.0),
            "codex": AgentResponse(name="codex", text="Codex response", elapsed=1.0),
        }
        prompt = build_synthesis_prompt("Hello", responses, member_names=members)

        claude_pos = prompt.index("=== Claude ===")
        codex_pos = prompt.index("=== Codex ===")
        agent_pos = prompt.index("=== Agent ===")

        assert claude_pos < codex_pos < agent_pos

    def test_build_synthesis_prompt_special_characters(self) -> None:
        """Test prompt handles special characters in user input."""
        # Quotes
        prompt = build_synthesis_prompt('Say "hello" to me', {})
        assert 'The user asked: "Say "hello" to me"' in prompt

        # Newlines
        prompt = build_synthesis_prompt("Line 1\nLine 2", {})
        assert "Line 1\nLine 2" in prompt

        # Unicode
        prompt = build_synthesis_prompt("Hello 世界 🌍", {})
        assert "Hello 世界 🌍" in prompt

    def test_build_synthesis_prompt_empty_text_no_error(self) -> None:
        """Test prompt handles empty text without error field."""
        responses = {
            "claude": AgentResponse(name="claude", text="", error=None, elapsed=1.0),
        }
        prompt = build_synthesis_prompt("Hello", responses)

        assert "=== Claude ===" in prompt
        # Empty text with no error should show [No response]
        assert "[No response]" in prompt
        assert "[Failed:" not in prompt

    def test_build_synthesis_prompt_multiline_responses(self) -> None:
        """Test prompt preserves multiline response formatting."""
        multiline_text = "Line 1\nLine 2\n\nLine 4 after blank"
        responses = {
            "claude": AgentResponse(name="claude", text=multiline_text, elapsed=1.0),
        }
        prompt = build_synthesis_prompt("Hello", responses)

        assert multiline_text in prompt

    def test_build_synthesis_prompt_instructions_present(self) -> None:
        """Test that all synthesis instructions are included."""
        prompt = build_synthesis_prompt("Hello", {})

        assert "Synthesize these perspectives into a unified response" in prompt
        assert "Consider:" in prompt
        assert "Points of agreement across advisors" in prompt
        assert "Unique insights from each" in prompt
        assert "Any contradictions to resolve" in prompt
        assert "The most actionable recommendation" in prompt
        assert "Respond directly to the user" in prompt
        assert "don't mention 'the advisors' explicitly" in prompt

    def test_build_synthesis_prompt_mixed_state(self) -> None:
        """Test prompt with mix of success, error, and missing responses."""
        members = ["claude", "codex", "agent"]
        responses = {
            "claude": AgentResponse(name="claude", text="Claude success", elapsed=1.0),
            "codex": AgentResponse(name="codex", text="", error="API timeout", elapsed=5.0),
            # agent is missing entirely
        }
        prompt = build_synthesis_prompt("Hello", responses, member_names=members)

        assert "Claude success" in prompt
        assert "[Failed: API timeout]" in prompt
        assert "[No response]" in prompt
        # Verify order is still correct
        claude_pos = prompt.index("=== Claude ===")
        codex_pos = prompt.index("=== Codex ===")
        agent_pos = prompt.index("=== Agent ===")
        assert claude_pos < codex_pos < agent_pos

    def test_build_synthesis_prompt_custom_member_names(self) -> None:
        """Test that custom member_names controls which members appear."""
        responses = {
            "alice": AgentResponse(name="alice", text="Alice says hi", elapsed=1.0),
            "bob": AgentResponse(name="bob", text="Bob agrees", elapsed=1.0),
        }
        prompt = build_synthesis_prompt("Hello", responses, member_names=["bob", "alice"])

        assert "=== Bob ===" in prompt
        assert "=== Alice ===" in prompt
        # Bob should appear before Alice per member_names order
        assert prompt.index("=== Bob ===") < prompt.index("=== Alice ===")

    def test_build_synthesis_prompt_no_member_names_uses_response_keys(self) -> None:
        """Test that without member_names, response dict keys are used."""
        responses = {
            "alpha": AgentResponse(name="alpha", text="Alpha response", elapsed=1.0),
            "beta": AgentResponse(name="beta", text="Beta response", elapsed=1.0),
        }
        prompt = build_synthesis_prompt("Hello", responses)

        assert "=== Alpha ===" in prompt
        assert "=== Beta ===" in prompt
