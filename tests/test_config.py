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
        assert set(cfg.agents) == {"claude", "codex", "cursor"}

    def test_agent_backends(self) -> None:
        cfg = default_config()
        assert cfg.agents["claude"].backend == "claude_code"
        assert cfg.agents["codex"].backend == "codex"
        assert cfg.agents["cursor"].backend == "cursor"

    def test_council_defaults(self) -> None:
        cfg = default_config()
        assert set(cfg.council.members) == {"claude", "codex", "cursor"}
        assert cfg.council.timeout == 600
        assert cfg.council.auto_messages == -1
        assert cfg.council.mode == "broadcast"
        assert cfg.council.preamble == ""

    def test_peasant_defaults(self) -> None:
        cfg = default_config()
        assert cfg.peasant.agent == "claude"
        assert cfg.peasant.timeout == 900
        assert cfg.peasant.max_iterations == 50

    def test_prompts_empty(self) -> None:
        cfg = default_config()
        assert cfg.prompts.council == ""
        assert cfg.prompts.design == ""
        assert cfg.prompts.review == ""
        assert cfg.prompts.peasant == ""


class TestValidateConfig:
    def test_empty_dict_returns_defaults(self) -> None:
        cfg = validate_config({})
        assert set(cfg.agents) == {"claude", "codex", "cursor"}
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
        assert "cursor" in cfg.agents

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

    def test_council_auto_messages(self) -> None:
        data = {"council": {"auto_messages": 5}}
        cfg = validate_config(data)
        assert cfg.council.auto_messages == 5

    def test_council_mode_sequential(self) -> None:
        data = {"council": {"mode": "sequential"}}
        cfg = validate_config(data)
        assert cfg.council.mode == "sequential"

    def test_council_mode_broadcast(self) -> None:
        data = {"council": {"mode": "broadcast"}}
        cfg = validate_config(data)
        assert cfg.council.mode == "broadcast"

    def test_council_preamble(self) -> None:
        data = {"council": {"preamble": "You are a helpful advisor."}}
        cfg = validate_config(data)
        assert cfg.council.preamble == "You are a helpful advisor."

    def test_council_new_fields_preserved_when_members_defaulted(self) -> None:
        data = {"council": {"auto_messages": 7, "mode": "sequential", "preamble": "Custom."}}
        cfg = validate_config(data)
        assert set(cfg.council.members) == {"claude", "codex", "cursor"}
        assert cfg.council.auto_messages == 7
        assert cfg.council.mode == "sequential"
        assert cfg.council.preamble == "Custom."

    def test_council_members_default_to_all_agents(self) -> None:
        cfg = validate_config({})
        assert set(cfg.council.members) == {"claude", "codex", "cursor"}

    def test_peasant_config(self) -> None:
        data = {"peasant": {"agent": "codex", "timeout": 1200, "max_iterations": 100}}
        cfg = validate_config(data)
        assert cfg.peasant.agent == "codex"
        assert cfg.peasant.timeout == 1200
        assert cfg.peasant.max_iterations == 100

    def test_full_config(self) -> None:
        data = {
            "agents": {
                "claude": {"backend": "claude_code", "model": "opus-4-6"},
                "codex": {"backend": "codex", "model": "o3"},
            },
            "prompts": {"council": "Analyze only."},
            "council": {"members": ["claude", "codex"], "timeout": 300},
            "peasant": {"agent": "claude", "timeout": 600},
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

    def test_bad_council_auto_messages_type(self) -> None:
        with pytest.raises(ValueError, match="must be an integer"):
            validate_config({"council": {"auto_messages": "many"}})

    def test_council_auto_messages_valid_values(self) -> None:
        validate_config({"council": {"auto_messages": -1}})  # -1 = auto (len(members))
        validate_config({"council": {"auto_messages": 0}})  # 0 = disabled
        validate_config({"council": {"auto_messages": 5}})  # positive = explicit budget
        with pytest.raises(ValueError, match="must be -1"):
            validate_config({"council": {"auto_messages": -2}})

    def test_bad_council_mode_type(self) -> None:
        with pytest.raises(ValueError, match="must be a string"):
            validate_config({"council": {"mode": 123}})

    def test_bad_council_mode_value(self) -> None:
        with pytest.raises(ValueError, match="must be one of"):
            validate_config({"council": {"mode": "turbo"}})

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

    def test_peasant_timeout_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            validate_config({"peasant": {"timeout": -1}})

    def test_peasant_max_iterations_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            validate_config({"peasant": {"max_iterations": 0}})


class TestLoadConfig:
    def test_no_file_returns_defaults(self, tmp_path: Path) -> None:
        (tmp_path / ".kd").mkdir()
        cfg = load_config(tmp_path)
        assert set(cfg.agents) == {"claude", "codex", "cursor"}

    def test_empty_file_returns_defaults(self, tmp_path: Path) -> None:
        kd = tmp_path / ".kd"
        kd.mkdir()
        (kd / "config.json").write_text("{}")
        cfg = load_config(tmp_path)
        assert set(cfg.agents) == {"claude", "codex", "cursor"}

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
