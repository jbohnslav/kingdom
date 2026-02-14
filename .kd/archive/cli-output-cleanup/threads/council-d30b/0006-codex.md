---
from: codex
to: king
timestamp: 2026-02-13T22:21:27Z
---

I’ll read the updated design doc first, then sanity-check it against current code paths (`council`, `design/tk show`, `tk move`, terminology) and call out any remaining gaps.
I have a few concrete concerns with the new `Markdown(f"## ...")` pattern in specific call sites, so I’m checking those exact sections to make sure recommendations are implementation-safe.
1. **Medium:** Replacing every panel with `Markdown(f"## ...\n\n{body}")` is good for council text, but risky for raw/log-like outputs. `peasant logs` and `peasant review` currently render literal stdout/stderr/test/diff text (`src/kingdom/cli.py:1307`, `src/kingdom/cli.py:1311`, `src/kingdom/cli.py:1634`, `src/kingdom/cli.py:1652`, `src/kingdom/cli.py:1664`, `src/kingdom/cli.py:1666`). Markdown can reinterpret symbols and alter readability.
Use Markdown headers, but keep raw payloads literal (or fenced as ` ```text `).

2. **Medium:** Whitespace stripping should be centralized at message write boundary, not repeated in worker/council/cli call sites. The single choke point is `add_message(...)` (`src/kingdom/thread.py:218`). That avoids future misses.

3. **Low-Medium:** If agent parseability is a primary goal, Rich Markdown still does wrapping/styling in TTY mode. You removed the biggest issue (box chars), but not all formatting variability. Consider plain output for non-interactive mode as a follow-up.

4. **Low:** Docs are now stale: architecture docs still describe panel output and `.kd/runs/...` paths (`docs/cli-skill-architecture.md:125`, `docs/cli-skill-architecture.md:154`, `docs/cli-skill-architecture.md:164`).

Overall: revised approach is solid and much better scoped. Main thing missing is treating raw machine-like output differently from prose markdown, and centralizing strip logic in `thread.add_message`.
