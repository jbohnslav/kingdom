---
from: cursor
to: king
timestamp: 2026-02-14T13:26:05Z
---

I recommend a **Hybrid Approach**: Use a single `.kd/config.json` as the source of truth, but allow it to reference external Markdown files for long system prompts.

This satisfies the "JSON only" requirement for the *configuration mechanism* while avoiding the pain of editing 50-line prompts inside JSON strings. It also lets us deprecate the confusing `.kd/agents/*.md` format (which mixed config frontmatter with prompt body).

### Recommendation: Single JSON Config + Optional Prompt Files

1.  **Primary**: All agent definitions live in `.kd/config.json`.
2.  **Simple Prompts**: Short prompts are written inline (string or list of strings).
3.  **Complex Prompts**: Long prompts are written in `.kd/prompts/<name>.md` and referenced by path.

#### 1. The Config File (`.kd/config.json`)

```json
{
  "council": {
    "members": ["architect", "researcher", "critic"],
    "timeout": 300
  },
  "agents": {
    "architect": {
      "backend": "claude",
      "model": "claude-3-opus",
      "system_prompt": "You are a software architect. Focus on patterns and modularity."
    },
    "researcher": {
      "backend": "cursor",
      "model": "gpt-4o",
      "system_prompt": [
        "You are a research specialist.",
        "1. Search the internet widely.",
        "2. Cite your sources."
      ],
      "extra_flags": ["--max-search-results", "10"]
    },
    "critic": {
      "backend": "gemini",
      "model": "gemini-1.5-pro",
      "system_prompt_file": "prompts/critic_rules.md"
    }
  }
}
```

#### 2. The Prompt File (`.kd/prompts/critic_rules.md`)

```markdown
You are a critical code reviewer.

# Guidelines
1. Look for security flaws first.
2. Identify performance bottlenecks.
3. Enforce strict typing.

# Tone
Be concise and direct. Do not sugarcoat feedback.
```

### Why This Wins

*   **Single Source of Truth**: You always look at `config.json` to see which agents exist and what backend they use.
*   **Editor Friendly**: You get full Markdown syntax highlighting for complex prompts in `.md` files, and JSON validation for the config.
*   **Copy-Pasteable**: You can copy the `agents` block to another project easily. If it uses external files, you copy the `prompts/` folder too.
*   **No "Mixed" Formats**: We delete `.kd/agents/*.md`. No more parsing YAML frontmatter out of Markdown files.

### Implementation Details

Here is how to handle the "manual validation" and file loading in `src/kingdom/config.py`:

```python
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class AgentConfig:
    name: str
    backend: str
    model: str | None = None
    system_prompt: str | None = None
    timeout: int = 300
    extra_flags: list[str] = field(default_factory=list)

def load_agent_config(name: str, data: dict[str, Any], project_root: Path) -> AgentConfig:
    # 1. Validate required fields
    if "backend" not in data:
        raise ValueError(f"Agent '{name}' missing required field: 'backend'")

    # 2. Handle system prompt (Inline vs File)
    system_prompt = None
    if "system_prompt_file" in data:
        prompt_path = project_root / ".kd" / data["system_prompt_file"]
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        system_prompt = prompt_path.read_text(encoding="utf-8")
    elif "system_prompt" in data:
        raw = data["system_prompt"]
        if isinstance(raw, list):
            system_prompt = "\n".join(raw)
        else:
            system_prompt = str(raw)

    # 3. Return dataclass
    return AgentConfig(
        name=name,
        backend=data["backend"],
        model=data.get("model"),
        system_prompt=system_prompt,
        timeout=data.get("timeout", 300),
        extra_flags=data.get("extra_flags", [])
    )
```

### Migration Plan

1.  **Refactor `src/kingdom/agent.py`**:
    *   Remove `parse_frontmatter` logic.
    *   Remove `cli` and `resume_flag` from `AgentConfig` (move these to the backend command builders in code).
    *   Add `model`, `system_prompt`, `extra_flags` to `AgentConfig`.
2.  **Create `src/kingdom/config.py`**: Implement the JSON loader above.
3.  **Update `CommandBuilders`**:
    *   `build_claude_command` now constructs the base CLI command itself (e.g., `["claude", "--print", ...]`) instead of reading it from config.
    *   It appends `extra_flags` from config.
4.  **Cleanup**: Delete any existing `.kd/agents/` directory logic.
