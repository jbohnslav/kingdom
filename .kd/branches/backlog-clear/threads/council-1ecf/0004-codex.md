---
from: codex
to: king
timestamp: 2026-02-14T19:19:11Z
---

I’ll review the `kingdom` skill instructions first, then inspect the current backlog with `kd` commands and cluster tickets into one pragmatic “usability and fixes” branch proposal. I’ll only read and analyze; no file edits or state-changing git actions.
I’ve loaded the `kingdom` workflow guidance. Next I’m pulling the backlog ticket list and individual ticket details so I can group a cohesive, low-design usability/fix batch.
I have the backlog list; now I’m reading ticket details to avoid grouping duplicates or high-design work. I’ll focus on concrete CLI UX/fix tickets that can ship together safely.
I hit a shell parsing hiccup while bulk-summarizing tickets; I’m rerunning with a safer loop and then I’ll propose a concrete branch-sized ticket bundle with rationale and exclusions.
I’ve identified a strong `kd tk`/`kd done` usability cluster, but there are likely duplicate tickets in that set. I’m now reading those ticket bodies to de-duplicate and estimate branch scope correctly.
I found clear duplicates (`kd tk log`, `kd done summary`, and `tk title echo` split tickets). I’m checking a few more likely overlaps (`config show`, `breakdown`, and small bugfixes) before I recommend one branch batch.
I’m now validating whether lightweight council-output tickets belong in the same branch, or if the branch should stay strictly in `tk/done/config` UX to reduce risk.
Reviewed backlog (`kd tk list --backlog`) and this is the best single-branch batch for “usability improvements + fixes” with low design overhead.

**Recommended Branch**
`backlog-batch-cli-ux-polish`

**Tickets to pull into one branch**
1. `115f` `kd tk commands should echo ticket ID and title in output`
2. `a24e` `kd tk start should print ticket title...` (covered by `115f`)
3. `4884` `kd tk close should print ticket title...` (covered by `115f`)
4. `4994` `Add kd tk log command...`
5. `19b6` `Add kd tk log command...` (duplicate of `4994`)
6. `8cf5` `kd done should summarize closed tickets and remind to push`
7. `8a92` `kd done should show a summary` (overlaps `8cf5`)
8. `0817` `kd done error should suggest passing branch name...`
9. `8ff9` `Add 'kd tk ls' alias`
10. `4789` `kd tk show should accept multiple IDs or --all`
11. `2ede` `kd tk create --dep`
12. `c1c7` `kd tk ready should prioritize/separate branch tickets from backlog`
13. `3ad1` `kd breakdown should explain what to do...`
14. `54e3` `kd breakdown should help create tickets...` (same UX area as `3ad1`)
15. `9cc9` `kd config show should indicate source`
16. `1c7b` `kd config show outputs noisy empty defaults`
17. `d0a2` `kd peasant review should flag when there is no code diff`
18. `083b` `peasant_start shadows agent parameter...`
19. `2316` `README advertises removed command`
20. `b430` `Remove learnings.md from branch scaffold...`

**Why this batch works**
- Mostly output/CLI ergonomics, small command behavior fixes, and low-risk correctness issues.
- Several are obvious duplicates/overlaps, so one implementation can close multiple tickets.
- Shared surfaces (`kd tk`, `kd done`, `kd breakdown`, `kd config show`) make this a cohesive “workflow polish” branch.

**Leave out of this branch**
- High-design / larger scope: `6412`, `70f6`, `a4f5`, `d09d`, `1c4b`, `3e60`, `549b`, `efed`, `d098`, `520a`, `50c7`, `e056`, `b5aa`.
- `1147` is important (P1), but likely deeper runtime behavior; I’d run it as a focused follow-up branch unless you want to absorb debugging risk here.

If you want, I can give a concrete pull order (`kd tk pull ...`) and a dependency/closure plan for duplicates before implementation.
