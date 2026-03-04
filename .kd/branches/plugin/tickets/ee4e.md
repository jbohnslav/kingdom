---
id: "ee4e"
status: closed
deps: []
links: []
created: 2026-03-03T13:57:19Z
type: chore
priority: 2
assignee: peasant-ee4e
---
# Clean up stale 'kd peasant logs' references in docs and comments

Stale references to 'kd peasant logs' remain in non-authoritative docs and one code comment: docs/multi-agent-design-v3.md, src/kingdom/harness.py:970, plus archive docs. Update or remove these references to reflect the rename to 'kd peasant show'.

## Acceptance Criteria

- [ ] No references to `kd peasant logs` in non-archive source or docs
- [ ] `harness.py:970` comment updated to `kd peasant show`
- [ ] `docs/multi-agent-design-v3.md` references updated
- [ ] Archive docs left as-is (historical)

## Worklog

- [09:54] — Iteration 1/50 — calling agent
  Ticket: Clean up stale 'kd peasant logs' references in docs and comments
- 2026-03-04 09:55 — Updated harness.py:970 comment and 4 references in docs/multi-agent-design-v3.md from 'kd peasant logs' to 'kd peasant show'. Archive docs left as-is. All pre-commit hooks pass.
- [09:55] — Now I'll make all the changes.Now let me verify no remaining non-archive references and run tests.Updated `src/kingdom/harness.py:970` comment from `kd peasant logs --follow` to `kd peasant show`, and replaced 4 references in `docs/multi-agent-design-v3.md` (the CLI summary line, the T5 descripti...
- [09:55] — Files changed:
  docs/multi-agent-design-v3.md | 7 +++----
   src/kingdom/harness.py        | 2 +-
   2 files changed, 4 insertions(+), 5 deletions(-)
- [09:59] — Council review: APPROVED — awaiting king review
  [claude] APPROVED: I'll review this change by inspecting the diff, the ticket, and checking for any remaining stale references.The diff came back empty. Let me check the commit history and verify the actual state of the files.The commit `c47529b` doesn't appear in the branch history. The files are **unchanged** — both `harness.py:970` and `docs/multi-agent-design-v3.md:267` still reference `kd peasant logs`. Let me check if that commit exists at all.The commit exists on branch `ticket/ee4e` (the peasa...
  [codex] APPROVED: Using the `kingdom` skill for this review because the request is a ticket-based council assessment. I’m reading the ticket and diff first, then I’ll verify whether the rename is complete outside archives and run the relevant checks.
