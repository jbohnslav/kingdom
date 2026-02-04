# Ralph: Analysis for Kingdom

Ralph is an autonomous AI agent loop framework that orchestrates repeated AI coding tool invocations (Amp or Claude Code) to complete a PRD item by item. It's not a library—it's a **bash-based orchestration system** (113 lines) with supporting documentation and skills.

Source: `third-party/ralph/`

---

## Core Architecture

### The Loop
```bash
for i in $(seq 1 $MAX_ITERATIONS); do
  OUTPUT=$(claude --dangerously-skip-permissions --print < CLAUDE.md 2>&1)
  if echo "$OUTPUT" | grep -q "<promise>COMPLETE</promise>"; then
    exit 0
  fi
done
```

Each iteration spawns a **fresh AI instance** with clean context. State continuity comes from files (prd.json, progress.txt, git commits), not session memory.

### State Files
| File | Purpose |
|------|---------|
| `prd.json` | Task queue with `passes: boolean` per story |
| `progress.txt` | Append-only learnings log |
| `.last-branch` | Tracks branch for archive trigger |

---

## Patterns Worth Adopting

### 1. Fresh Context per Iteration
**Ralph:** Each AI call starts fresh. No session resume.
**Kingdom:** Uses `--resume` for conversation continuity.

**Tradeoff:** Fresh context forces better state externalization but loses conversational flow. Kingdom's Hand model may benefit from continuity for multi-turn design discussions, but Peasant workers could use fresh context like Ralph.

### 2. Knowledge Consolidation (`progress.txt`)
Ralph's `progress.txt` has a `## Codebase Patterns` section at the top:
```markdown
## Codebase Patterns
- Use `sql<number>` template for aggregations
- Always use `IF NOT EXISTS` for migrations
- Export types from actions.ts for UI components
```

**Kingdom doesn't have this.** Could add a `.kd/runs/<feature>/learnings.md` that accumulates patterns discovered during development.

### 3. Acceptance Criteria as Machine-Verifiable Contracts
Ralph is prescriptive about what makes good criteria:

**Bad (vague):**
- "Works correctly"
- "User can do X easily"

**Good (verifiable):**
- "Add `status` column to tasks table with default 'pending'"
- "Filter dropdown has options: All, Active, Completed"
- "Typecheck passes"
- "Verify in browser using dev-browser skill"

**Kingdom's breakdown format** has acceptance criteria but the MVP doc doesn't specify quality standards. Could add guidance like Ralph's.

### 4. Completion Sentinel
Ralph uses an explicit XML tag:
```
<promise>COMPLETE</promise>
```

Simple grep detection that's immune to output noise. Better than parsing JSON or checking file state.

**Kingdom could adopt:** Use explicit markers for phase transitions (design approved, breakdown approved, ticket complete).

### 5. Archive-on-Branch-Change
Ralph detects when `prd.json.branchName` changes and automatically archives the previous run:
```bash
if [ "$CURRENT_BRANCH" != "$LAST_BRANCH" ]; then
  cp "$PRD_FILE" "$ARCHIVE_DIR/$DATE-$FOLDER_NAME/"
  cp "$PROGRESS_FILE" "$ARCHIVE_DIR/$DATE-$FOLDER_NAME/"
  echo "# Ralph Progress Log" > "$PROGRESS_FILE"  # Reset
fi
```

**Kingdom has `runs/<feature>`** but no archiving. Could add `.kd/archive/` for completed features.

### 6. Skills as Markdown
Ralph skills are markdown files with YAML frontmatter:
```yaml
---
name: prd
description: "Generate a PRD..."
user-invocable: true
---
# PRD Generator
...instructions...
```

**Kingdom has `/design` and `/breakdown` commands** hardcoded in hand.py. Could extract to skill files for extensibility.

### 7. Clarifying Questions with Lettered Options
Ralph's PRD skill asks questions in a specific format:
```
1. What is the scope?
   A. Minimal viable version
   B. Full-featured implementation
   C. Just the backend/API
```

User responds: "1A, 2C, 3B" — fast iteration.

**Kingdom could adopt** this pattern for design clarification questions.

### 8. Distributed CLAUDE.md Files
Ralph instructs agents to update directory-specific CLAUDE.md files:
```
Before committing, check if any edited files have learnings worth
preserving in nearby CLAUDE.md files.
```

This scales knowledge better than a monolithic file.

### 9. Dependency-First Story Ordering
From Ralph's skill:
- Schema/database changes first
- Server actions/backend logic second
- UI components that depend on backend third
- Dashboard/summary views last

**Kingdom's breakdown** has `Depends on:` but doesn't specify ordering strategy. Could add guidance.

---

## Patterns to NOT Adopt

### JSON PRDs
Ralph uses `prd.json` with structured schema. Kingdom uses markdown (`design.md`, `breakdown.md`) which is more human-readable and editable. **Keep markdown.**

### No Council
Ralph has no multi-model consultation. Kingdom's Council pattern (claude, codex, agent in parallel) is more sophisticated. **Keep Council.**

### Minimal UX
Ralph is a single bash script with no interactive mode. Kingdom's Hand provides interactive chat. **Keep Hand's interactivity.**

---

## Concrete Recommendations

1. **Add learnings accumulation** — `.kd/runs/<feature>/learnings.md` with `## Codebase Patterns` section at top
2. **Define acceptance criteria quality** — Add guidance to MVP doc about verifiable vs vague criteria
3. **Use completion sentinels** — Explicit markers for phase transitions
4. **Add archiving** — `.kd/archive/<date>-<feature>/` when runs complete
5. **Lettered options for clarification** — Pattern for Hand to use when asking design questions
6. **Skill extraction** — Consider making `/design` and `/breakdown` into skill files

---

## Why Doesn't Kingdom Just Use Ralph Loops?

### The Question
Ralph is simple and effective: 113 lines of bash that loops through stories until done. Should Kingdom's Peasants just be Ralph loops?

### Where Ralph's Model Fits
Ralph's loop makes sense when:
1. **You have a queue of work** — Multiple stories in prd.json, iterate through them
2. **Each unit is self-contained** — One story = one commit, no cross-story dependencies mid-implementation
3. **Fresh context is acceptable** — Each iteration starts clean, state is in files
4. **Quality gates are automated** — Typecheck, tests, lint can verify "done"

### Where Kingdom Differs

**1. Kingdom has structured phases, not just execution**
- Ralph: PRD → auto-implement (one phase)
- Kingdom: Design → Breakdown → Tickets → Develop (multiple phases)

The Hand's job during Design and Breakdown is **collaborative iteration with the user**, not autonomous execution. Ralph's loop pattern doesn't fit interactive design.

**2. Kingdom has Council**
Ralph is single-model. Kingdom's Council queries claude, codex, and agent in parallel, then synthesizes. This multi-model consultation doesn't map to Ralph's "run one model, check sentinel, repeat" pattern.

**3. Different granularity**
- Ralph story: "Add priority column to tasks table" — atomic, completable in one iteration
- Kingdom ticket: Could be similar, or could be larger

If Kingdom tickets match Ralph story size, a Peasant might not need a loop — one invocation could complete the ticket.

### When a Ralph-Style Loop WOULD Help

**Peasant retry loop:**
A Peasant could use Ralph's pattern for a single ticket:
```bash
for i in $(seq 1 $MAX_RETRIES); do
  OUTPUT=$(claude --print < peasant_prompt.md)
  if verify_acceptance_criteria "$TICKET"; then
    exit 0
  fi
done
```

This handles the case where the first attempt doesn't pass quality checks.

**Development phase loop:**
`kd dev` could be a Ralph-style loop over all tickets:
```bash
while tickets_remaining; do
  NEXT=$(next_unblocked_ticket)
  kd peasant "$NEXT"
done
```

This is essentially what `kd dev` would become post-MVP.

### Recommendation

**Don't replace Kingdom's architecture with Ralph.** Instead:

1. **Hand stays interactive** — Session continuity, Council, synthesis
2. **Peasant adopts Ralph's discipline** — Fresh context, verifiable acceptance criteria, completion sentinels
3. **`kd dev` becomes a Ralph-style loop** — Iterate through tickets, one Peasant per ticket

The insight isn't "use Ralph" — it's **adopt Ralph's constraints** (fresh context, externalized state, machine-verifiable done criteria) where they fit (Peasant execution), while keeping Kingdom's additions (Council, Hand interactivity, structured phases) where they add value.

---

## Key Insight

Ralph succeeds because of **clarity and constraints**, not sophistication:
- Each story defines exactly what "done" means
- Each iteration starts fresh (no accumulated confusion)
- Knowledge is externalized to files (git, progress.txt, CLAUDE.md)
- The loop is simple: pick story → implement → check quality → commit → next

Kingdom has more moving parts (Council, synthesis, tmux) but could adopt Ralph's **discipline around acceptance criteria and knowledge externalization**.
