---
from: cursor
to: king
timestamp: 2026-02-14T12:05:49Z
---

As Council Advisor, I have analyzed the requirements for the Kingdom Configuration System.

Based on your request and a review of `docs/multi-agent-design-v3.md` (which proposed Markdown-based agent configs) and third-party comparisons, I recommend adopting a **centralized JSON configuration** strategy. This aligns with industry standards (VS Code, ESLint) and simplifies the "mix-and-match" flexibility you want for the Council and Peasants.

Here is the design proposal to be added to the system.

### **Design: Kingdom Configuration System (RFC)**

**Goal**: Allow users to define custom agent rosters, assign specific LLMs/prompts to roles, and optimize costs (e.g., "cheap peasants, smart council") via a simple JSON file.

#### **1. The Configuration File: `.kd/config.json`**

We will introduce `.kd/config.json` as the single source of truth for agent definitions and role assignments.

**Proposed Schema:**

```json
{
  "council": {
    "members": ["claude-architect", "gpt-researcher", "gemini-critic"],
    "synthesis_model": "claude-architect"
  },
  "peasant": {
    "default_model": "kimmy-worker",
    "review_model": "claude-architect"
  },
  "agents": {
    "claude-architect": {
      "backend": "claude",
      "model": "claude-3-opus",
      "system_prompt": "You are a senior software architect. Focus on system design, patterns, and long-term maintainability."
    },
    "gpt-researcher": {
      "backend": "cursor",
      "model": "gpt-4o",
      "system_prompt": "You are a research specialist. Search the internet widely for existing docs, repos, and libraries before answering.",
      "capabilities": ["internet"]
    },
    "gemini-critic": {
      "backend": "cursor",
      "model": "gemini-1.5-pro",
      "system_prompt": "You are a critical code reviewer. Look for edge cases, security flaws, and performance bottlenecks."
    },
    "kimmy-worker": {
      "backend": "cursor",
      "model": "kimmy-2.5",
      "cost": "low",
      "system_prompt": "You are a junior developer. Follow instructions precisely. Write clean, working code."
    }
  }
}
```

#### **2. Key Features & Behavior**

*   **Customizable Council**: The `council.members` list defines who sits in the `kd chat` room. Users can have a "Council of One" or a "Council of Five" with different personas.
*   **Role-Based Models**:
    *   **Peasants**: Can use cheaper models (defined in `peasant.default_model`) for bulk execution (`kd peasant start`).
    *   **Council**: Can use expensive/reasoning models for high-level strategy.
*   **Backend Abstraction**: The `backend` field maps to the underlying CLI tool:
    *   `"claude"` -> `claude` CLI
    *   `"cursor"` -> `cursor agent` CLI (supports any model Cursor supports: GPT, Gemini, Kimmy, DeepSeek)
    *   `"codex"` -> `codex` CLI
*   **Per-Agent Prompts**: Each agent gets a dedicated system prompt injected at the start of their session. This enables specialized roles (e.g., "The Researcher" who always searches first).

#### **3. Integration with Existing Design**

*   **Supersedes `docs/multi-agent-design-v3.md` Agent Config**: We will replace the proposed `.kd/agents/*.md` format with this `.kd/config.json`. JSON is easier to validate and edit programmatically.
*   **Session Management**: When `kd start` or `kd chat` runs, it will read `config.json`, instantiate the required `CouncilMember` subclasses based on the `backend` field, and initialize them with the specified `model` and `system_prompt`.

#### **4. Third-Party Inspiration (incorporated)**

*   **From Gastown**: The concept of "Unified Dispatch" is preserved. You define the *resources* (agents) in config, and the *work* (tickets) is dispatched to them.
*   **From OpenClaw**: We adopt the "Profile Pinning" idea. Once a run starts, the agent configuration should be "pinned" in the run's `state.json` so that changing the global config doesn't break active runs.
*   **From Ralph**: The distinction between "Planner" (Council) and "Looper" (Peasant) is enforced via the `peasant` vs `council` config sections.

### **Recommendations for Implementation**

1.  **Create `src/kingdom/config.py`**: A module to load, validate, and provide access to `.kd/config.json`.
2.  **Update `Council.create()`**: Modify `src/kingdom/council/base.py` to accept a list of agent configs instead of hardcoding `ClaudeMember`, `CodexMember`, etc.
3.  **Dynamic Backend Loading**: Implement a factory pattern (`AgentFactory.create(backend_type, config)`) to instantiate the correct CLI wrapper.

This design gives you the exact flexibility requested: cheap peasants, specialized council members, and JSON-based configuration.
