---
from: claude
to: king
timestamp: 2026-02-17T13:07:08Z
---

Ship the whole thing. Here's my reasoning:

**Textual isn't that heavy.** It pulls in `rich` (which you already depend on for CLI output) and a few small extras. It's not like shipping numpy or torch — we're talking a few MB of pure Python.

**Splitting creates real UX friction.** If `kd chat` is in the primary README flow (which it is), then `uv tool install kingdom-cli` needs to just work. Making users figure out `kingdom-cli[chat]` or a separate install step for the main feature is a bad first impression. People will hit the error, assume it's broken, and leave.

**You don't have evidence anyone wants the split yet.** This is a v0.1 launch. You have zero users asking "I love kd but I wish I could skip the TUI dependency." If that demand appears later, you can split it then — moving a dep from required to optional is a non-breaking change.

**The complexity cost is real.** Optional deps mean: conditional imports, user-facing error messages when the extra isn't installed (you already have one), documentation for two install paths, testing both paths. That's maintenance burden for a hypothetical need.

Just add `textual` to the main `[project.dependencies]` and delete the conditional import guard. Revisit if someone actually complains about install size. @codex — agree or disagree?
