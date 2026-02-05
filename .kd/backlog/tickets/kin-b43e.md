---
id: kin-b43e
status: open
deps: []
links: []
created: 2026-02-05T00:26:22Z
type: bug
priority: 2
---
# Council timeout too short, needs better debug output

Two council members (agent, claude) timed out during a design review query. The default 120s timeout may be too short for complex prompts.

Changes needed:
1. Increase default timeout to 5 minutes (300s)
2. Add better debug output to council commands - show progress/status while waiting
3. Consider streaming responses or progress indicators so users know it's working
