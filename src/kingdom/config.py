"""Configuration system for Kingdom.

Loads agent definitions, council composition, peasant settings, and per-phase
prompts from ``.kd/config.json``. All fields are optional — sensible defaults
are provided for zero-config operation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from kingdom.state import state_root

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AgentDef:
    """User-facing agent configuration from config.json."""

    backend: str  # claude_code, codex, cursor
    model: str = ""
    prompt: str = ""
    prompts: dict[str, str] = field(default_factory=dict)
    extra_flags: list[str] = field(default_factory=list)


@dataclass
class PromptsConfig:
    """Per-phase default prompts applied to all agents."""

    council: str = ""
    design: str = ""
    review: str = ""
    peasant: str = ""


@dataclass
class CouncilConfig:
    """Council composition and settings."""

    members: list[str] = field(default_factory=list)
    timeout: int = 600


@dataclass
class PeasantConfig:
    """Peasant worker settings."""

    agent: str = "claude"
    timeout: int = 900
    max_iterations: int = 50


@dataclass
class KingdomConfig:
    """Top-level configuration, loaded from .kd/config.json."""

    agents: dict[str, AgentDef] = field(default_factory=dict)
    prompts: PromptsConfig = field(default_factory=PromptsConfig)
    council: CouncilConfig = field(default_factory=CouncilConfig)
    peasant: PeasantConfig = field(default_factory=PeasantConfig)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_AGENTS: dict[str, AgentDef] = {
    "claude": AgentDef(backend="claude_code"),
    "codex": AgentDef(backend="codex"),
    "cursor": AgentDef(backend="cursor"),
}


def default_config() -> KingdomConfig:
    """Return the built-in default configuration."""
    agents = {name: AgentDef(backend=a.backend) for name, a in DEFAULT_AGENTS.items()}
    return KingdomConfig(
        agents=agents,
        prompts=PromptsConfig(),
        council=CouncilConfig(members=list(agents)),
        peasant=PeasantConfig(agent="claude"),
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

VALID_AGENT_KEYS = {"backend", "model", "prompt", "prompts", "extra_flags"}
VALID_PROMPTS_KEYS = {"council", "design", "review", "peasant"}
VALID_COUNCIL_KEYS = {"members", "timeout"}
VALID_PEASANT_KEYS = {"agent", "timeout", "max_iterations"}
VALID_TOP_KEYS = {"agents", "prompts", "council", "peasant"}
VALID_AGENT_PROMPT_PHASES = {"council", "design", "review", "peasant"}


def check_unknown_keys(data: dict, valid: set[str], context: str) -> None:
    """Raise ValueError if data contains keys not in valid set."""
    unknown = set(data) - valid
    if unknown:
        raise ValueError(f"Unknown keys in {context}: {', '.join(sorted(unknown))}")


def validate_agent(name: str, data: dict) -> AgentDef:
    """Validate and construct an AgentDef from a raw dict."""
    check_unknown_keys(data, VALID_AGENT_KEYS, f"agents.{name}")

    backend = data.get("backend")
    if not backend:
        raise ValueError(f"Agent '{name}' is missing required field 'backend'")
    if not isinstance(backend, str):
        raise ValueError(f"agents.{name}.backend must be a string, got {type(backend).__name__}")

    model = data.get("model", "")
    if model and not isinstance(model, str):
        raise ValueError(f"agents.{name}.model must be a string, got {type(model).__name__}")

    prompt = data.get("prompt", "")
    if prompt and not isinstance(prompt, str):
        raise ValueError(f"agents.{name}.prompt must be a string, got {type(prompt).__name__}")

    prompts = data.get("prompts", {})
    if not isinstance(prompts, dict):
        raise ValueError(f"agents.{name}.prompts must be an object, got {type(prompts).__name__}")
    bad_phases = set(prompts) - VALID_AGENT_PROMPT_PHASES
    if bad_phases:
        raise ValueError(f"Unknown prompt phases in agents.{name}.prompts: {', '.join(sorted(bad_phases))}")
    for phase, val in prompts.items():
        if not isinstance(val, str):
            raise ValueError(f"agents.{name}.prompts.{phase} must be a string, got {type(val).__name__}")

    extra_flags = data.get("extra_flags", [])
    if not isinstance(extra_flags, list):
        raise ValueError(f"agents.{name}.extra_flags must be a list, got {type(extra_flags).__name__}")
    for i, flag in enumerate(extra_flags):
        if not isinstance(flag, str):
            raise ValueError(f"agents.{name}.extra_flags[{i}] must be a string, got {type(flag).__name__}")

    return AgentDef(
        backend=backend,
        model=model or "",
        prompt=prompt or "",
        prompts=prompts,
        extra_flags=extra_flags,
    )


def validate_prompts(data: dict) -> PromptsConfig:
    """Validate and construct a PromptsConfig from a raw dict."""
    check_unknown_keys(data, VALID_PROMPTS_KEYS, "prompts")
    for key in VALID_PROMPTS_KEYS:
        val = data.get(key)
        if val is not None and not isinstance(val, str):
            raise ValueError(f"prompts.{key} must be a string, got {type(val).__name__}")
    return PromptsConfig(
        council=data.get("council", ""),
        design=data.get("design", ""),
        review=data.get("review", ""),
        peasant=data.get("peasant", ""),
    )


def validate_council(data: dict) -> CouncilConfig:
    """Validate and construct a CouncilConfig from a raw dict."""
    check_unknown_keys(data, VALID_COUNCIL_KEYS, "council")

    members = data.get("members", [])
    if not isinstance(members, list):
        raise ValueError(f"council.members must be a list, got {type(members).__name__}")
    for i, m in enumerate(members):
        if not isinstance(m, str):
            raise ValueError(f"council.members[{i}] must be a string, got {type(m).__name__}")

    timeout = data.get("timeout", 600)
    if not isinstance(timeout, int):
        raise ValueError(f"council.timeout must be an integer, got {type(timeout).__name__}")

    return CouncilConfig(members=members, timeout=timeout)


def validate_peasant(data: dict) -> PeasantConfig:
    """Validate and construct a PeasantConfig from a raw dict."""
    check_unknown_keys(data, VALID_PEASANT_KEYS, "peasant")

    agent = data.get("agent", "claude")
    if not isinstance(agent, str):
        raise ValueError(f"peasant.agent must be a string, got {type(agent).__name__}")

    timeout = data.get("timeout", 900)
    if not isinstance(timeout, int):
        raise ValueError(f"peasant.timeout must be an integer, got {type(timeout).__name__}")

    max_iterations = data.get("max_iterations", 50)
    if not isinstance(max_iterations, int):
        raise ValueError(f"peasant.max_iterations must be an integer, got {type(max_iterations).__name__}")

    return PeasantConfig(agent=agent, timeout=timeout, max_iterations=max_iterations)


def validate_config(data: dict) -> KingdomConfig:
    """Validate a raw dict and construct a KingdomConfig.

    Merges user-provided agents with built-in defaults. Validates types,
    required fields, and cross-references (council members and peasant agent
    must reference defined agents).

    Raises:
        ValueError: On unknown keys, missing required fields, type errors,
            or invalid cross-references.
    """
    check_unknown_keys(data, VALID_TOP_KEYS, "config")

    # Agents: merge defaults with user overrides
    agents_data = data.get("agents", {})
    if not isinstance(agents_data, dict):
        raise ValueError(f"agents must be an object, got {type(agents_data).__name__}")

    agents: dict[str, AgentDef] = {}
    # Start with defaults
    for name, default in DEFAULT_AGENTS.items():
        if name in agents_data:
            agents[name] = validate_agent(name, agents_data[name])
        else:
            agents[name] = AgentDef(backend=default.backend)
    # Add user-defined agents not in defaults
    for name, agent_data in agents_data.items():
        if name not in agents:
            agents[name] = validate_agent(name, agent_data)

    # Prompts
    prompts_data = data.get("prompts", {})
    if not isinstance(prompts_data, dict):
        raise ValueError(f"prompts must be an object, got {type(prompts_data).__name__}")
    prompts = validate_prompts(prompts_data)

    # Council
    council_data = data.get("council", {})
    if not isinstance(council_data, dict):
        raise ValueError(f"council must be an object, got {type(council_data).__name__}")
    council = validate_council(council_data)

    # Default council members to all agents if not specified
    if not council.members:
        council = CouncilConfig(members=list(agents), timeout=council.timeout)

    # Peasant
    peasant_data = data.get("peasant", {})
    if not isinstance(peasant_data, dict):
        raise ValueError(f"peasant must be an object, got {type(peasant_data).__name__}")
    peasant = validate_peasant(peasant_data)

    # Cross-reference validation
    defined = set(agents)
    for member in council.members:
        if member not in defined:
            raise ValueError(
                f"council.members references undefined agent '{member}'. Defined agents: {', '.join(sorted(defined))}"
            )
    if peasant.agent not in defined:
        raise ValueError(
            f"peasant.agent references undefined agent '{peasant.agent}'. Defined agents: {', '.join(sorted(defined))}"
        )

    return KingdomConfig(agents=agents, prompts=prompts, council=council, peasant=peasant)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_config(base: Path) -> KingdomConfig:
    """Load configuration from .kd/config.json, falling back to defaults.

    Returns default_config() if the file doesn't exist or is empty.

    Raises:
        ValueError: If the file exists but contains invalid JSON or fails
            validation.
    """
    config_path = state_root(base) / "config.json"
    if not config_path.exists():
        return default_config()

    text = config_path.read_text(encoding="utf-8").strip()
    if not text or text == "{}":
        return default_config()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Config must be a JSON object, got {type(data).__name__}")

    return validate_config(data)
