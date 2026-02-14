---
from: claude
to: king
timestamp: 2026-02-14T03:01:45Z
---

Good, now I have the full picture. Here's my review.

---

## Design Doc Review: `agent-skill`

### Overall Assessment

The design is **solid and well-reasoned**. The structural decisions align with the spec, the progressive disclosure strategy is correct, and the "skill teaches workflow, CLI stays as bash" principle is exactly right. There are a few issues ranging from spec violations to content accuracy problems.

### What's Correct Per Spec

1. **Directory structure** — `kingdom/SKILL.md` with `scripts/` and `references/` matches the spec exactly.
2. **`name` field** — `kingdom` is valid: lowercase, no hyphens needed, matches parent directory.
3. **Progressive disclosure** — metadata → body (<500 lines) → references is the right pattern.
4. **No Claude Code extensions** — correct decision for portability. The spec explicitly says `allowed-tools` is experimental.
5. **No extraneous files** — no README, no CHANGELOG, no INSTALLATION_GUIDE in the skill directory. This matches the skill-creator's guidance exactly.

### Issues

#### 1. `metadata.requires-bins` is not a spec field — it's meaningless

The design proposes:
```yaml
metadata:
  requires-bins: kd
```

The `metadata` field is a freeform key-value map, so this is *technically valid*, but no agent platform reads `requires-bins`. It's dead weight. The correct way to express this dependency is the `compatibility` field, which the design already uses: `compatibility: Requires kd CLI (pip install kingdom), git`. The `metadata.requires-bins` is redundant — drop it.

#### 2. `compatibility` value should mention Python

`Requires kd CLI (pip install kingdom), git` — but `kd` is a Python package installed via `uv` or `pip`. An agent trying to install it needs to know Python is required. Should be something like: `Requires Python 3.12+, kd CLI (pip install kingdom), git`.

#### 3. The design doc's command list has inaccuracies

The design says:
```
kd council ask/show/list/watch/reset
```

That's actually correct per `kd council --help`. But the current root-level SKILL.md references commands that don't exist or are wrong:

- `kd council last` — doesn't exist (it's `kd council list`)
- `kd council show <run-id>` — exists but parameter is `thread-id`, not `run-id`
- `kd council show last` — not clear this works
- `kd design` — creates/views template per the SKILL.md, but per `--help` it's just the parent command (subcommands are `show` and `approve`)
- `kd ticket` — the SKILL.md says `kd ticket` but the actual alias is `kd tk` (both may work, but the design doc itself uses `kd tk`)
- `kd peasant <ticket-id>` — the SKILL.md says this creates a worktree, but the actual subcommand structure needs `kd peasant start`

The design doc should note that the new SKILL.md must use the **actual** command signatures, not the ones from the old SKILL.md.

#### 4. The design doc's command list is also incomplete

Missing from the command inventory:
- `kd init` — initialize `.kd/` directory
- `kd doctor` — check agent CLIs are installed (useful preflight, arguably more valuable than `scripts/check-kd.sh`)
- `kd work` — run autonomous agent loop on a ticket
- `kd tk assign/unassign` — agent assignment
- `kd tk pull` — pull backlog tickets into current branch
- `kd tk undep` — remove dependencies
- `kd breakdown` — listed but not clearly distinguished from `kd breakdown --apply`

Not all of these need to be in the skill body, but the design doc's "What Commands Stay as Bash" section should be the complete inventory so nothing is accidentally omitted.

#### 5. `scripts/check-kd.sh` is probably unnecessary

The design proposes a preflight script. But `kd doctor` already exists and does exactly this — it checks whether agent CLIs are installed. An agent that has the skill loaded can just run `kd doctor` as the first step. Adding a bash script to check whether `kd` itself is installed is marginal value: if `kd` isn't installed, the very first `kd` command will fail with `command not found`, and any agent will understand that error. The skill can just say "Run `kd doctor` to verify prerequisites" in the body.

If you do want a preflight, a `which kd` one-liner in the SKILL.md body is sufficient — doesn't need a `scripts/` directory for it. Removing `scripts/` entirely makes the skill structure simpler:

```
kingdom/
├── SKILL.md
└── references/
    ├── council.md
    ├── tickets.md
    └── peasants.md
```

#### 6. Reference file split is probably too granular

Three reference files (`council.md`, `tickets.md`, `peasants.md`) for what is ultimately one linear workflow. The question is whether an agent would ever need `tickets.md` without `council.md` context. In practice, the workflow is tightly coupled — you council to design, breakdown to tickets, then work tickets with peasants.

Two alternatives to consider:
- **Single `references/commands.md`** — comprehensive command reference with all subcommands, flags, and examples. SKILL.md stays workflow-focused, `commands.md` is the lookup table.
- **Keep the three-file split** but make sure each is self-contained and doesn't duplicate what's in SKILL.md.

The three-file approach isn't wrong per the spec, but make sure each file justifies its existence. If `peasants.md` would only be 30 lines, it should merge into SKILL.md or into a combined reference.

#### 7. Open question on root SKILL.md should be resolved in the design

The design asks: "Should the existing root `SKILL.md` be replaced with a symlink to `kingdom/SKILL.md`, or deleted with a note pointing to the new location?"

My recommendation: **delete it**. The root `SKILL.md` is not spec-compliant (no frontmatter, no directory), and having two SKILL.md files is confusing. The `kingdom/` directory is the skill. If someone wants to install it, they copy/symlink the `kingdom/` directory. The root SKILL.md served its purpose as a prototype; the new structure replaces it. A note in CLAUDE.md or the project README (if you have one) can point to `kingdom/` as the skill location.

#### 8. The SKILL.md body outline should front-load actionable commands

The proposed outline is:

> 1. Role definition
> 2. Core workflow
> 3. Key commands
> 4. When to consult council
> 5. Directory structure
> 6. Best practices
> 7. References

The skill-creator guidance says: "Only add context Claude doesn't already have." An agent doesn't need a "role definition" section — the description field already says what Kingdom is. It also doesn't need a "directory structure" section for `.kd/` — it can just `ls` if it needs to know.

Tighter ordering:
1. **Core workflow** — the linear path from start to done (this is the unique knowledge)
2. **Command reference** — concise table of commands (the actionable part)
3. **Council philosophy** — don't synthesize, let King read directly (this is the non-obvious behavioral constraint)
4. **References** — pointers to deep dives

The current SKILL.md's "You are the Hand" role-play framing is fine flavor text but costs tokens. One sentence is enough; a whole section is too much.

#### 9. Description could be more trigger-oriented

The skill-creator guidance emphasizes that the description is the *primary triggering mechanism*. The proposed description says "Use when the user mentions kd, kingdom, council, design docs, ticket breakdown, or multi-agent workflow." That's good but could be stronger. Consider adding action-oriented triggers: "Use when starting a new feature branch, breaking down work into tickets, consulting multiple AI models for design decisions, or managing development workflow with kd commands."

### Summary of Recommendations

| Item | Severity | Action |
|---|---|---|
| Drop `metadata.requires-bins` | Low | Remove, `compatibility` covers it |
| Add Python to `compatibility` | Low | `Requires Python 3.12+, kd CLI, git` |
| Fix command signatures | Medium | Audit against actual `--help` output |
| Complete command inventory | Medium | Add init, doctor, work, assign, undep, pull |
| Drop `scripts/check-kd.sh` | Low | `kd doctor` already exists |
| Resolve root SKILL.md fate | Medium | Delete it, design should state this |
| Tighten SKILL.md body outline | Low | Front-load workflow and commands, trim role framing |
| Sharpen description triggers | Low | Add action-oriented trigger phrases |

The design is 90% there. The structural decisions are correct. The gaps are all in content accuracy and spec-pedantry, not in architecture.
