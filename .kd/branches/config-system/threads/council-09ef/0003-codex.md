---
from: codex
to: king
timestamp: 2026-02-14T12:15:58Z
---

I’ll stay in analysis-only mode and start by pulling `kd tk show 3860`, then I’ll scan the local comparison docs and relevant skill guidance so I can propose a concrete JSON config design without changing files.
I pulled ticket `3860` and confirmed it already scopes JSON/TOML config for council members, model IDs, permissions, and per-phase prompts. Next I’m mining the local third-party comparison docs for concrete config patterns users expect, then I’ll add internet-backed comparisons.
I’ve extracted the local design context and third-party notes; next I’m collecting external docs on real-world agent/tool config systems (Claude Code, Codex, Aider, OpenHands, etc.) so we can ground the config shape in what users already expect.
I’ve started pulling external sources; now I’m broadening to other agent ecosystems to extract concrete config fields (fallbacks, budgets, routing, profiles, observability, and safety controls) that users commonly expect.
I now have usable external references for Claude Code, OpenHands, Continue, Aider, and SWE-agent. I’m drilling into the exact option surfaces to turn this into a concrete “must-have vs later” config proposal for `kingdom`.
I found the authoritative Codex config docs pointer in the repo and am now pulling the exact OpenAI `config-basic/config-advanced/config-reference` pages, plus a quick pass over local docs that mention `.kd/config.json` expectations.
I can’t reliably extract Cursor docs due redirects in this environment, so I’m replacing that with other primary sources that are easier to parse (Aider/OpenHands/SWE-agent/Claude/Codex) to keep recommendations evidence-backed.
I’ve got strong external evidence now. I’m doing one more pass through your local third-party analyses (`openclaw`, `llm-council`, etc.) to align recommendations with what your own docs already concluded, then I’ll propose a concrete JSON schema and rollout plan.
I’ve aligned with your internal analyses; next I’m reading the current `kingdom` implementation (`state/council/agent/cli`) so the design recommendation matches the actual code paths and migration risk.
I confirmed the current run is `config-system` and there’s no `.kd/agents/` yet in this workspace, so this feature will likely define defaults plus optional overrides from config. I’m reading the active design doc to align recommendations with branch intent.
I confirmed the concrete integration points for config: `.kd/config.json` exists but is unused, while council members come from `.kd/agents/*.md` and peasant prompting is hardcoded. I’m doing a quick pass of `design.py/synthesis.py` to include phase-prompt override recommendations accurately.
`kd tk show 3860` confirms scope and matches your ask. I did not change files.

**Current Reality In Code**
- `.kd/config.json` exists but is unused (`src/kingdom/state.py:228`).
- Council membership currently comes from `.kd/agents/*.md` or hardcoded defaults (`src/kingdom/council/council.py:25`, `src/kingdom/agent.py:130`).
- Council/peasant prompts are hardcoded (`src/kingdom/council/base.py:38`, `src/kingdom/harness.py:36`, `src/kingdom/design.py:80`, `src/kingdom/synthesis.py:7`).
- Peasant default agent is hardcoded to `claude` (`src/kingdom/cli.py:1097`, `src/kingdom/cli.py:1702`).
- Design/synthesis code still assumes fixed names `claude/codex/agent` (`src/kingdom/design.py:137`, `src/kingdom/synthesis.py:7`).

**Recommended `config.json` Shape (v1)**
```json
{
  "version": 1,
  "roles": {
    "council": { "members": ["claude_arch", "codex_research", "cursor_gemini"], "min_successful": 2 },
    "peasant": { "default_agent": "cursor_kimi_worker", "allowed_agents": ["cursor_kimi_worker", "claude_worker"] },
    "hand": { "default_agent": "claude_hand" }
  },
  "agents": {
    "codex_research": {
      "backend": "codex",
      "model": "gpt-5.3-codex",
      "cli": "codex exec --json",
      "resume_flag": "resume",
      "permissions_profile": "read_only",
      "timeouts": { "query_seconds": 600 },
      "prompt_overrides": {
        "council.ask": "Search the web broadly for docs/repos and cite sources."
      }
    },
    "cursor_kimi_worker": {
      "backend": "cursor",
      "model": "kimi-2.5",
      "cli": "agent --print --output-format json",
      "resume_flag": "--resume",
      "permissions_profile": "worker_write"
    }
  },
  "prompts": {
    "phase_defaults": {
      "council.ask": "Return analysis and recommendations only.",
      "design": "Propose concrete design decisions and non-goals.",
      "review": "Prioritize regressions, risks, and missing tests."
    }
  },
  "execution": {
    "council_timeout_seconds": 600,
    "council_parallelism": 6,
    "retry": { "max_attempts": 1 }
  },
  "profiles": {
    "cheap-dev": { "roles.peasant.default_agent": "cursor_kimi_worker" },
    "deep-council": { "roles.council.members": ["claude_opus_high", "claude_opus_low", "codex_research", "cursor_gemini", "cursor_deepseek"] }
  }
}
```

**What Users Will Want Beyond Your Initial List**
- Config layering and overrides (global/user/project/profile), not just one flat file.
- Profiles/presets (cheap mode vs deep mode).
- Per-role permission/sandbox policy.
- Timeouts/retries/failure policy (graceful degradation when one council member fails).
- Fallback model/provider chain per agent.
- Budget guards (per-run cost/token caps; especially for council).
- Context controls (files to auto-include/exclude per phase).
- MCP/tool integration toggles.
- Observability toggles (structured logs/traces, stream behavior).

**Design Recommendation**
- Keep v1 minimal: `roles`, `agents`, `prompts`, `execution` only.
- Add `profiles` in v1 if easy; defer budgets/fallbacks/MCP to v1.1.
- Preserve backward compatibility: if config is missing/partial, current defaults still work.
- Do not keep hardcoded council member names in design/synthesis paths.

**Decisions To Lock Before Implementation**
1. Is `.kd/config.json` the single source of truth, or do `.kd/agents/*.md` remain supported?
2. Prompt merge order: safety preamble → phase default → agent override → runtime user prompt?
3. Should unknown config keys fail hard or warn-and-ignore?
4. Should `profiles` be selectable via CLI flag/env now or later?

**Sources**
- Local ticket + code: `.kd/branches/config-system/tickets/3860.md`, `src/kingdom/state.py:228`, `src/kingdom/council/council.py:25`, `src/kingdom/agent.py:32`, `src/kingdom/council/base.py:38`, `src/kingdom/harness.py:36`, `src/kingdom/design.py:137`, `src/kingdom/synthesis.py:7`
- Local third-party analyses: `docs/third_party/openclaw.md`, `docs/third_party/llm-council.md`, `docs/third_party/skills.md`
- Anthropic Claude Code settings: https://docs.anthropic.com/en/docs/claude-code/settings
- OpenAI Codex config docs: https://developers.openai.com/codex/config-basic , https://developers.openai.com/codex/config-advanced , https://developers.openai.com/codex/config-reference
- Aider config/model settings: https://aider.chat/docs/config/options.html , https://aider.chat/docs/config/model-settings.html
- Continue config reference: https://docs.continue.dev/reference
- OpenHands configuration options: https://docs.all-hands.dev/openhands/usage/configuration-options
- SWE-agent config overview/models: https://swe-agent.com/latest/config/overview/ , https://swe-agent.com/latest/config/models/
