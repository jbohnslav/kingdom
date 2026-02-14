---
from: codex
to: king
timestamp: 2026-02-13T23:12:01Z
---

I’ll inspect the current `kd done` and `.kd` tracking/ignore model first, because the right design depends on which files are actually git-tracked versus operational-only.
I found an important inconsistency: docs still describe `state.json` as ignored, but `.kd/.gitignore` currently ignores all `*.json` recursively, which has implications for any status-based approach. I’ll confirm what’s actually tracked in this repo now.
I now have enough to recommend a concrete workflow. I’m doing one last check for whether `.kd/branches/*` is currently tracked in this repo state, because that affects the clutter tradeoff directly.
Recommended design: split “finish work” from “curate tracked history.”

1. `kd done` should become operational-only and never touch tracked markdown paths.
2. Add a separate `kd archive` (or `kd archive sweep`) that performs tracked moves in a normal PR branch when you choose to do repo curation.

Why this is the right model

- Current pain is caused by tracked path moves (`src/kingdom/cli.py:246`), not by status writes.
- `state.json` is already ignored (`.kd/.gitignore:2`) and currently not tracked at all.
- `.kd/branches/*` content is tracked in this repo (`.kd/branches/cli-output-cleanup/design.md` etc.), so moving/deleting it locally will always create tracked diffs.
- Therefore option 2 is a trap: moving tracked files into a gitignored destination still creates tracked deletions in source.

Tradeoffs by option

1. Status-only in `state.json` + maybe `kd gc`:
- Strong on safety and branch-protection compatibility.
- Weak on long-term tree clutter if you never run archival PRs.
- Also: `kd gc` cannot “prune” tracked branch folders without creating tracked changes.

2. Status-only + move to gitignored archive:
- Not viable for tracked branch folders (creates tracked deletions).

3. Run `kd done` on feature branch before merge:
- Viable, and avoids post-merge protected-branch friction.
- But brittle operationally: easy to forget, and it couples lifecycle cleanup to feature PR timing.
- Can add noisy/non-functional diffs to feature PRs.

4. Hybrid (recommended):
- `kd done`: local completion only (clear `.kd/current`, remove worktrees, optional local done metadata).
- `kd archive`: explicit tracked move, run either:
  - on the feature branch before merge, or
  - on a separate cleanup branch after merge, via PR.
- This keeps daily flow safe while still allowing periodic cleanup.

Concrete recommendation

- Adopt option 4.
- Make `kd done` idempotent and zero tracked diffs by design.
- Keep archive moves as an explicit maintenance action, not part of mandatory “done.”
- If clutter is mostly UX, solve in commands (`kd status`, list commands) by showing active/current by default, not by forcing immediate file moves.

Relevant refs: `src/kingdom/cli.py:193`, `src/kingdom/cli.py:246`, `.kd/.gitignore:2`, `.kd/.gitignore:9`, `README.md:77`, `README.md:80`.
