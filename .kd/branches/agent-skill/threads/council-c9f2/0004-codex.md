---
from: codex
to: king
timestamp: 2026-02-14T03:41:50Z
---

I’ll perform a PR-style audit against `cf85` acceptance criteria: read the design, the listed closed tickets, shipped skill files/tests, and packaging changes, then report concrete findings with file references and pass/fail by criterion.
I confirmed the ticket set and root `SKILL.md` removal; next I’m auditing the delivered `skills/kingdom/*` and `tests/test_skill.py` line-by-line against the design requirements and cf85 checklist.
I found a likely command-signature mismatch (`kd work` probably needs a ticket argument). I’m validating all skill-documented command signatures against actual CLI definitions before final verdict.
I’ve identified a couple of command-signature mismatches in the shipped SKILL docs; I’m doing one last quick sweep for residual references and then I’ll provide pass/fail against each `cf85` acceptance criterion.
**Findings**
1. **High: `cf85` acceptance criterion “at least one kd command registered and working as a skill” is not met as written.**
   The implementation intentionally keeps commands as bash and does not register an invocable skill command surface; smoke test was also replaced with structural tests only.
   Refs: `.kd/branches/agent-skill/tickets/cf85.md:18`, `.kd/branches/agent-skill/tickets/b253.md:17`, `.kd/branches/agent-skill/design.md:39`, `.kd/branches/agent-skill/design.md:47`

2. **Medium: Command signatures are incorrect in shipped skill docs.**
   `kd work` requires a ticket id, but docs show `kd work` with no arg. `kd tk pull` requires one or more ticket ids, but docs show no args.
   Refs: `skills/kingdom/SKILL.md:100`, `skills/kingdom/SKILL.md:125`, `skills/kingdom/references/tickets.md:61`, `skills/kingdom/references/peasants.md:52`, `src/kingdom/cli.py:1725`, `src/kingdom/cli.py:2542`

3. **Medium: Tests do not enforce command-signature correctness despite design requirement.**
   `tests/test_skill.py` validates structure/frontmatter/references only, not CLI signature accuracy against `--help`, so the above mismatches pass.
   Refs: `tests/test_skill.py:34`, `tests/test_skill.py:62`, `.kd/branches/agent-skill/design.md:31`

4. **Low: Python compatibility claim may be optimistic without validation matrix.**
   `requires-python` changed to `>=3.10`, but tool config still targets `py312`; no evidence in this PR of 3.10/3.11 test runs.
   Refs: `pyproject.toml:6`, `pyproject.toml:30`

**Acceptance Criteria (`cf85`)**
1. Open spec reviewed/documented: **Met** (design documents format/discovery/platform framing).
   Ref: `.kd/branches/agent-skill/design.md:24`
2. Platform support understanding: **Met** (documented as portable core + platform wiring).
   Ref: `.kd/branches/agent-skill/design.md:119`
3. At least one kd command registered and working as a skill: **Not met (strict reading)**.
   Ref: `.kd/branches/agent-skill/tickets/cf85.md:18`
4. Commands as skills vs bash documented: **Met** (decision is “all bash”).
   Ref: `.kd/branches/agent-skill/design.md:47`
5. Limitations/gotchas documented: **Met** (platform wiring/open questions/gotchas).
   Refs: `.kd/branches/agent-skill/design.md:121`, `.kd/branches/agent-skill/design.md:139`

**Other requested checks**
1. Root `SKILL.md` deletion: **Confirmed gone** (`ROOT_SKILL_EXISTS:1`).
2. Implementation structure: **Matches design** (`skills/kingdom/SKILL.md` + `references/`, no scripts).
   Refs: `skills/kingdom/SKILL.md`, `skills/kingdom/references/council.md`, `skills/kingdom/references/tickets.md`, `skills/kingdom/references/peasants.md`

Overall: close, but I would not call it fully done for `cf85` until either (a) criterion 3 is explicitly re-scoped/updated, and (b) the command signature docs are corrected.
