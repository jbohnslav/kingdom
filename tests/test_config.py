"""Tests for configuration system."""

import json
from pathlib import Path

import pytest

from kingdom.config import (
    default_config,
    load_config,
    validate_config,
)


class TestDefaultConfig:
    def test_has_three_agents(self) -> None:
        cfg = default_config()
        assert set(cfg.agents) == {"claude", "codex"}

    def test_agent_backends(self) -> None:
        cfg = default_config()
        assert cfg.agents["claude"].backend == "claude_code"
        assert cfg.agents["codex"].backend == "codex"

    def test_council_defaults(self) -> None:
        cfg = default_config()
        assert set(cfg.council.members) == {"claude", "codex"}
        assert cfg.council.timeout == 600
        assert cfg.council.ask.auto_messages == -1
        assert cfg.council.ask.mode == "broadcast"
        assert cfg.council.preamble == ""
        assert cfg.council.chat.mode == "natural"
        assert cfg.council.chat.auto_rounds == 1

    def test_peasant_defaults(self) -> None:
        cfg = default_config()
        assert cfg.peasant.agent == "claude"
        assert cfg.peasant.max_iterations == 50

    def test_lord_defaults(self) -> None:
        cfg = default_config()
        assert cfg.lord.agent == "claude"
        assert cfg.lord.max_cycles == 200

    def test_prompts_empty(self) -> None:
        cfg = default_config()
        assert cfg.prompts.council == ""
        assert cfg.prompts.design == ""
        assert cfg.prompts.review == ""
        assert cfg.prompts.peasant == ""


class TestValidateConfig:
    def test_empty_dict_returns_defaults(self) -> None:
        cfg = validate_config({})
        assert set(cfg.agents) == {"claude", "codex"}
        assert cfg.peasant.agent == "claude"

    def test_custom_agents(self) -> None:
        data = {
            "agents": {
                "claude": {"backend": "claude_code", "model": "opus-4-6"},
                "local": {"backend": "cursor", "prompt": "Be concise."},
            }
        }
        cfg = validate_config(data)
        assert cfg.agents["claude"].model == "opus-4-6"
        assert cfg.agents["local"].backend == "cursor"
        assert cfg.agents["local"].prompt == "Be concise."
        # Defaults still present
        assert "codex" in cfg.agents

    def test_agent_extra_flags(self) -> None:
        data = {"agents": {"claude": {"backend": "claude_code", "extra_flags": ["--verbose", "--no-cache"]}}}
        cfg = validate_config(data)
        assert cfg.agents["claude"].extra_flags == ["--verbose", "--no-cache"]

    def test_agent_per_phase_prompts(self) -> None:
        data = {
            "agents": {
                "claude": {
                    "backend": "claude_code",
                    "prompts": {"council": "Be analytical.", "peasant": "Follow instructions exactly."},
                }
            }
        }
        cfg = validate_config(data)
        assert cfg.agents["claude"].prompts["council"] == "Be analytical."
        assert cfg.agents["claude"].prompts["peasant"] == "Follow instructions exactly."

    def test_global_prompts(self) -> None:
        data = {"prompts": {"council": "No implementation.", "review": "Check for regressions."}}
        cfg = validate_config(data)
        assert cfg.prompts.council == "No implementation."
        assert cfg.prompts.review == "Check for regressions."
        assert cfg.prompts.design == ""

    def test_council_members(self) -> None:
        data = {"council": {"members": ["claude", "codex"], "timeout": 300}}
        cfg = validate_config(data)
        assert cfg.council.members == ["claude", "codex"]
        assert cfg.council.timeout == 300

    def test_council_ask_auto_messages(self) -> None:
        data = {"council": {"ask": {"auto_messages": 5}}}
        cfg = validate_config(data)
        assert cfg.council.ask.auto_messages == 5

    def test_council_ask_mode_sequential(self) -> None:
        data = {"council": {"ask": {"mode": "sequential"}}}
        cfg = validate_config(data)
        assert cfg.council.ask.mode == "sequential"

    def test_council_ask_mode_broadcast(self) -> None:
        data = {"council": {"ask": {"mode": "broadcast"}}}
        cfg = validate_config(data)
        assert cfg.council.ask.mode == "broadcast"

    def test_council_preamble(self) -> None:
        data = {"council": {"preamble": "You are a helpful advisor."}}
        cfg = validate_config(data)
        assert cfg.council.preamble == "You are a helpful advisor."

    def test_council_new_fields_preserved_when_members_defaulted(self) -> None:
        data = {"council": {"ask": {"auto_messages": 7, "mode": "sequential"}, "preamble": "Custom."}}
        cfg = validate_config(data)
        assert set(cfg.council.members) == {"claude", "codex"}
        assert cfg.council.ask.auto_messages == 7
        assert cfg.council.ask.mode == "sequential"
        assert cfg.council.preamble == "Custom."

    def test_council_writable_true(self) -> None:
        data = {"council": {"writable": True}}
        cfg = validate_config(data)
        assert cfg.council.writable is True

    def test_council_writable_false(self) -> None:
        data = {"council": {"writable": False}}
        cfg = validate_config(data)
        assert cfg.council.writable is False

    def test_council_writable_default(self) -> None:
        cfg = validate_config({})
        assert cfg.council.writable is False

    def test_council_writable_preserved_when_members_defaulted(self) -> None:
        data = {"council": {"writable": True}}
        cfg = validate_config(data)
        assert cfg.council.writable is True
        assert set(cfg.council.members) == {"claude", "codex"}

    def test_council_members_default_to_all_agents(self) -> None:
        cfg = validate_config({})
        assert set(cfg.council.members) == {"claude", "codex"}

    def test_peasant_config(self) -> None:
        data = {"peasant": {"agent": "codex", "max_iterations": 100}}
        cfg = validate_config(data)
        assert cfg.peasant.agent == "codex"
        assert cfg.peasant.max_iterations == 100

    def test_lord_config(self) -> None:
        data = {"lord": {"agent": "codex", "max_cycles": 500}}
        cfg = validate_config(data)
        assert cfg.lord.agent == "codex"
        assert cfg.lord.max_cycles == 500

    def test_lord_agent_falls_back_to_peasant_agent(self) -> None:
        data = {"peasant": {"agent": "codex"}}
        cfg = validate_config(data)
        assert cfg.lord.agent == "codex"

    def test_lord_agent_falls_back_to_default_peasant_agent(self) -> None:
        cfg = validate_config({})
        assert cfg.lord.agent == "claude"

    def test_lord_agent_overrides_peasant_agent(self) -> None:
        data = {"peasant": {"agent": "codex"}, "lord": {"agent": "claude"}}
        cfg = validate_config(data)
        assert cfg.lord.agent == "claude"
        assert cfg.peasant.agent == "codex"

    def test_full_config(self) -> None:
        data = {
            "agents": {
                "claude": {"backend": "claude_code", "model": "opus-4-6"},
                "codex": {"backend": "codex", "model": "o3"},
            },
            "prompts": {"council": "Analyze only."},
            "council": {"members": ["claude", "codex"], "timeout": 300},
            "peasant": {"agent": "claude"},
        }
        cfg = validate_config(data)
        assert cfg.agents["claude"].model == "opus-4-6"
        assert cfg.council.members == ["claude", "codex"]
        assert cfg.prompts.council == "Analyze only."


class TestValidateConfigErrors:
    def test_unknown_top_level_key(self) -> None:
        with pytest.raises(ValueError, match="Unknown keys in config: timout"):
            validate_config({"timout": 300})

    def test_unknown_agent_key(self) -> None:
        with pytest.raises(ValueError, match=r"Unknown keys in agents\.claude"):
            validate_config({"agents": {"claude": {"backend": "claude_code", "colour": "blue"}}})

    def test_unknown_prompts_key(self) -> None:
        with pytest.raises(ValueError, match="Unknown keys in prompts"):
            validate_config({"prompts": {"synthesis": "Do stuff."}})

    def test_unknown_council_key(self) -> None:
        with pytest.raises(ValueError, match="Unknown keys in council"):
            validate_config({"council": {"timout": 300}})

    def test_unknown_peasant_key(self) -> None:
        with pytest.raises(ValueError, match="Unknown keys in peasant"):
            validate_config({"peasant": {"agnet": "claude"}})

    def test_missing_backend(self) -> None:
        with pytest.raises(ValueError, match="missing required field 'backend'"):
            validate_config({"agents": {"myagent": {"model": "gpt-4"}}})

    def test_bad_backend_type(self) -> None:
        with pytest.raises(ValueError, match="must be a string"):
            validate_config({"agents": {"myagent": {"backend": 123}}})

    def test_bad_model_type(self) -> None:
        with pytest.raises(ValueError, match="must be a string"):
            validate_config({"agents": {"claude": {"backend": "claude_code", "model": 123}}})

    def test_bad_extra_flags_type(self) -> None:
        with pytest.raises(ValueError, match="must be a list"):
            validate_config({"agents": {"claude": {"backend": "claude_code", "extra_flags": "--flag"}}})

    def test_bad_extra_flags_element(self) -> None:
        with pytest.raises(ValueError, match="extra_flags\\[0\\] must be a string"):
            validate_config({"agents": {"claude": {"backend": "claude_code", "extra_flags": [123]}}})

    def test_bad_agent_prompts_type(self) -> None:
        with pytest.raises(ValueError, match="must be an object"):
            validate_config({"agents": {"claude": {"backend": "claude_code", "prompts": "string"}}})

    def test_bad_agent_prompt_phase(self) -> None:
        with pytest.raises(ValueError, match="Unknown prompt phases"):
            validate_config({"agents": {"claude": {"backend": "claude_code", "prompts": {"synthesis": "x"}}}})

    def test_council_member_undefined_agent(self) -> None:
        with pytest.raises(ValueError, match=r"undefined agent 'ghost'.*Defined agents"):
            validate_config({"council": {"members": ["claude", "ghost"]}})

    def test_peasant_agent_undefined(self) -> None:
        with pytest.raises(ValueError, match=r"undefined agent 'ghost'.*Defined agents"):
            validate_config({"peasant": {"agent": "ghost"}})

    def test_lord_agent_undefined(self) -> None:
        with pytest.raises(ValueError, match=r"lord\.agent references undefined agent 'ghost'"):
            validate_config({"lord": {"agent": "ghost"}})

    def test_unknown_lord_key(self) -> None:
        with pytest.raises(ValueError, match="Unknown keys in lord"):
            validate_config({"lord": {"timeout": 300}})

    def test_bad_lord_agent_type(self) -> None:
        with pytest.raises(ValueError, match=r"lord\.agent must be a string"):
            validate_config({"lord": {"agent": 123}})

    def test_bad_lord_max_cycles_type(self) -> None:
        with pytest.raises(ValueError, match=r"lord\.max_cycles must be an integer"):
            validate_config({"lord": {"max_cycles": "many"}})

    def test_lord_max_cycles_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            validate_config({"lord": {"max_cycles": 0}})

    def test_bad_lord_type(self) -> None:
        with pytest.raises(ValueError, match="lord must be an object"):
            validate_config({"lord": "string"})

    def test_bad_council_timeout_type(self) -> None:
        with pytest.raises(ValueError, match="must be an integer"):
            validate_config({"council": {"timeout": "fast"}})

    def test_bad_agents_type(self) -> None:
        with pytest.raises(ValueError, match="agents must be an object"):
            validate_config({"agents": ["claude"]})

    def test_bad_council_members_type(self) -> None:
        with pytest.raises(ValueError, match="must be a list"):
            validate_config({"council": {"members": "claude"}})

    def test_unknown_backend(self) -> None:
        with pytest.raises(ValueError, match="not a known backend"):
            validate_config({"agents": {"myagent": {"backend": "foo"}}})

    def test_council_timeout_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            validate_config({"council": {"timeout": 0}})

    def test_bad_ask_auto_messages_type(self) -> None:
        with pytest.raises(ValueError, match="must be an integer"):
            validate_config({"council": {"ask": {"auto_messages": "many"}}})

    def test_ask_auto_messages_valid_values(self) -> None:
        validate_config({"council": {"ask": {"auto_messages": -1}}})
        validate_config({"council": {"ask": {"auto_messages": 0}}})
        validate_config({"council": {"ask": {"auto_messages": 5}}})
        with pytest.raises(ValueError, match="must be -1"):
            validate_config({"council": {"ask": {"auto_messages": -2}}})

    def test_bad_ask_mode_type(self) -> None:
        with pytest.raises(ValueError, match="must be a string"):
            validate_config({"council": {"ask": {"mode": 123}}})

    def test_bad_ask_mode_value(self) -> None:
        with pytest.raises(ValueError, match="must be one of"):
            validate_config({"council": {"ask": {"mode": "turbo"}}})

    def test_deprecated_flat_keys_fail_fast(self) -> None:
        for key in ("auto_messages", "mode", "chat_mode", "chat_auto_rounds"):
            with pytest.raises(ValueError, match="Deprecated council keys"):
                validate_config({"council": {key: "whatever"}})

    def test_bad_council_preamble_type(self) -> None:
        with pytest.raises(ValueError, match="must be a string"):
            validate_config({"council": {"preamble": 123}})

    def test_council_preamble_must_be_nonempty(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            validate_config({"council": {"preamble": ""}})

    def test_bad_thinking_visibility_type(self) -> None:
        with pytest.raises(ValueError, match="must be a string"):
            validate_config({"council": {"thinking_visibility": 123}})

    def test_bad_thinking_visibility_value(self) -> None:
        with pytest.raises(ValueError, match="must be one of"):
            validate_config({"council": {"thinking_visibility": "verbose"}})

    def test_thinking_visibility_valid_values(self) -> None:
        for mode in ("auto", "show", "hide"):
            cfg = validate_config({"council": {"thinking_visibility": mode}})
            assert cfg.council.thinking_visibility == mode

    def test_thinking_visibility_default(self) -> None:
        cfg = validate_config({})
        assert cfg.council.thinking_visibility == "auto"

    def test_bad_council_writable_type(self) -> None:
        with pytest.raises(ValueError, match="must be a boolean"):
            validate_config({"council": {"writable": "yes"}})

    def test_council_writable_rejects_int(self) -> None:
        with pytest.raises(ValueError, match="must be a boolean"):
            validate_config({"council": {"writable": 1}})

    def test_chat_mode_round_robin(self) -> None:
        cfg = validate_config({"council": {"chat": {"mode": "round_robin"}}})
        assert cfg.council.chat.mode == "round_robin"

    def test_chat_mode_broadcast(self) -> None:
        cfg = validate_config({"council": {"chat": {"mode": "broadcast"}}})
        assert cfg.council.chat.mode == "broadcast"

    def test_chat_mode_manual(self) -> None:
        cfg = validate_config({"council": {"chat": {"mode": "manual"}}})
        assert cfg.council.chat.mode == "manual"

    def test_chat_mode_natural(self) -> None:
        cfg = validate_config({"council": {"chat": {"mode": "natural"}}})
        assert cfg.council.chat.mode == "natural"

    def test_bad_chat_mode_type(self) -> None:
        with pytest.raises(ValueError, match=r"council\.chat\.mode must be a string"):
            validate_config({"council": {"chat": {"mode": 123}}})

    def test_bad_chat_mode_value(self) -> None:
        with pytest.raises(ValueError, match=r"council\.chat\.mode must be one of"):
            validate_config({"council": {"chat": {"mode": "invalid"}}})

    def test_chat_auto_rounds(self) -> None:
        cfg = validate_config({"council": {"chat": {"auto_rounds": 3}}})
        assert cfg.council.chat.auto_rounds == 3

    def test_chat_auto_rounds_zero(self) -> None:
        cfg = validate_config({"council": {"chat": {"auto_rounds": 0}}})
        assert cfg.council.chat.auto_rounds == 0

    def test_bad_chat_auto_rounds_type(self) -> None:
        with pytest.raises(ValueError, match=r"council\.chat\.auto_rounds must be an integer"):
            validate_config({"council": {"chat": {"auto_rounds": "many"}}})

    def test_bad_chat_auto_rounds_negative(self) -> None:
        with pytest.raises(ValueError, match=r"council\.chat\.auto_rounds must be non-negative"):
            validate_config({"council": {"chat": {"auto_rounds": -1}}})

    def test_peasant_max_iterations_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            validate_config({"peasant": {"max_iterations": 0}})

    def test_reasoning_effort_valid_on_codex(self) -> None:
        for effort in ("low", "medium", "high"):
            cfg = validate_config({"agents": {"codex": {"backend": "codex", "reasoning_effort": effort}}})
            assert cfg.agents["codex"].reasoning_effort == effort

    def test_reasoning_effort_absent_defaults_empty(self) -> None:
        cfg = validate_config({})
        assert cfg.agents["codex"].reasoning_effort == ""
        assert cfg.agents["claude"].reasoning_effort == ""

    def test_reasoning_effort_bad_value(self) -> None:
        with pytest.raises(ValueError, match="must be one of"):
            validate_config({"agents": {"codex": {"backend": "codex", "reasoning_effort": "turbo"}}})

    def test_reasoning_effort_bad_type(self) -> None:
        with pytest.raises(ValueError, match="must be a string"):
            validate_config({"agents": {"codex": {"backend": "codex", "reasoning_effort": 3}}})

    def test_reasoning_effort_falsey_bad_types_rejected(self) -> None:
        for val in (0, False, []):
            with pytest.raises(ValueError, match="must be a string"):
                validate_config({"agents": {"codex": {"backend": "codex", "reasoning_effort": val}}})

    def test_reasoning_effort_unsupported_backend_claude(self) -> None:
        with pytest.raises(ValueError, match="only supported for backends"):
            validate_config({"agents": {"claude": {"backend": "claude_code", "reasoning_effort": "high"}}})

    def test_reasoning_effort_unsupported_backend_cursor(self) -> None:
        with pytest.raises(ValueError, match="only supported for backends"):
            validate_config({"agents": {"mycursor": {"backend": "cursor", "reasoning_effort": "low"}}})


class TestLoadConfig:
    def test_no_file_returns_defaults(self, tmp_path: Path) -> None:
        (tmp_path / ".kd").mkdir()
        cfg = load_config(tmp_path)
        assert set(cfg.agents) == {"claude", "codex"}

    def test_empty_file_returns_defaults(self, tmp_path: Path) -> None:
        kd = tmp_path / ".kd"
        kd.mkdir()
        (kd / "config.json").write_text("{}")
        cfg = load_config(tmp_path)
        assert set(cfg.agents) == {"claude", "codex"}

    def test_valid_config_file(self, tmp_path: Path) -> None:
        kd = tmp_path / ".kd"
        kd.mkdir()
        data = {
            "agents": {"claude": {"backend": "claude_code", "model": "opus-4-6"}},
            "council": {"members": ["claude"], "timeout": 120},
        }
        (kd / "config.json").write_text(json.dumps(data))
        cfg = load_config(tmp_path)
        assert cfg.agents["claude"].model == "opus-4-6"
        assert cfg.council.members == ["claude"]
        assert cfg.council.timeout == 120

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        kd = tmp_path / ".kd"
        kd.mkdir()
        (kd / "config.json").write_text("{bad json")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_config(tmp_path)

    def test_non_object_json_raises(self, tmp_path: Path) -> None:
        kd = tmp_path / ".kd"
        kd.mkdir()
        (kd / "config.json").write_text('"just a string"')
        with pytest.raises(ValueError, match="must be a JSON object"):
            load_config(tmp_path)

    def test_validation_errors_propagate(self, tmp_path: Path) -> None:
        kd = tmp_path / ".kd"
        kd.mkdir()
        data = {"agents": {"bad": {"model": "x"}}}  # missing backend
        (kd / "config.json").write_text(json.dumps(data))
        with pytest.raises(ValueError, match="missing required field 'backend'"):
            load_config(tmp_path)

    def test_unknown_keys_caught_on_load(self, tmp_path: Path) -> None:
        """load_config validates so unknown keys surface immediately."""
        kd = tmp_path / ".kd"
        kd.mkdir()
        data = {"council": {"bogus_key": True}}
        (kd / "config.json").write_text(json.dumps(data))
        with pytest.raises(ValueError, match="Unknown keys in council: bogus_key"):
            load_config(tmp_path)

    def test_bad_types_caught_on_load(self, tmp_path: Path) -> None:
        """load_config validates types, not just keys."""
        kd = tmp_path / ".kd"
        kd.mkdir()
        data = {"council": {"timeout": "slow"}}
        (kd / "config.json").write_text(json.dumps(data))
        with pytest.raises(ValueError, match=r"council\.timeout must be an integer"):
            load_config(tmp_path)
