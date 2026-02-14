---
from: claude
to: king
timestamp: 2026-02-13T22:10:26Z
---

Now I have a thorough picture. Here's my analysis:

---

## Design Review: cli-output-cleanup

### Overall Assessment

The design is clean, well-scoped, and correctly identifies the core problem: Rich panels create friction for both agents and humans doing copy-paste. The approach of replacing panels with plain text while keeping tables is the right call.

### Key Question: Keep Rich Console or Go Fully Plain?

**Recommendation: Keep Rich, but only for two things — Tables and Progress spinners.** Remove everything else.

Here's why:

**Tables (`peasant status`)** — This is genuinely better with Rich. The columnar layout with aligned headers would be painful to replicate with `typer.echo()` and `str.ljust()`. You'd be reimplementing table rendering poorly. Rich Tables don't have the copy-paste problem that Panels do — they use simple `│` and `─` characters that read fine.

**Progress spinners (`council ask --sync`, `query_with_progress`)** — These are transient UI elements (they disappear when done). They never end up in copy-paste or agent output. Replacing them with `typer.echo("Querying...")` loses the "still working" feedback during long council queries, which can take 30+ seconds. The spinner is genuinely useful UX here.

**Everything else should go.** Specifically:
- `Panel` + `Markdown` → `typer.echo()` with raw markdown text
- `console.print(f"[dim]...[/dim]")` → `typer.echo()` (the dim styling is nice-to-have but not worth the dependency surface)
- `console.print(Panel(..., border_style="green"))` for test results → plain `typer.echo("--- pytest: PASSED ---\n{output}")` with a simple header

This keeps Rich as a dependency (it's a transitive dep of Typer anyway, so you can't remove it from your dep tree), but limits its surface area to two well-justified use cases.

### Concerns and Suggestions

**1. Council output separator format matters.** The design says `--- header ---` or `## header` but doesn't commit to one. I'd go with `## header` — it's valid markdown that agents parse well, and in `council show` where you're displaying multi-member responses, agents will correctly identify `## advisor_name` as a section boundary. The `---` style looks like a horizontal rule and could confuse markdown parsers.

**2. The `render_response_panel` function** (line 667-686 in cli.py) is the core formatting chokepoint for council output. It currently does Panel + Markdown + dim elapsed time. Replacing it with something like:

```
## member_name (12.3s)
<response text as-is>
```

...is clean, parseable, and trivial for agents. Good target for a single, clean refactor.

**3. `peasant review` has 5 panels** (lines 1620-1673) for pytest, ruff, diff, worklog. These are the densest panel cluster. Replacing with simple section headers works, but consider: the color-coded pass/fail borders (green/red) are actually useful visual signal for humans reviewing peasant work. You could keep the pass/fail in the header text (`--- pytest: PASSED ---` vs `--- pytest: FAILED ---`) which is sufficient — agents don't need ANSI colors to understand pass/fail.

**4. Trailing whitespace stripping in council** — This is a good fix but make sure you strip at write-time (when `add_message` persists the response), not at display-time. That way the `.kd/` files themselves are clean for pre-commit hooks, and any future consumer of those files gets clean data.

**5. `tk move` defaulting to current branch** — Straightforward, but verify behavior when called from a worktree (peasant context). `resolve_current_run(base)` should handle this, but worth a quick check since worktrees have a different `.git` structure.

**6. No test plan mentioned in the design doc.** These are all output changes, so automated testing is tricky, but at minimum you should manually verify:
- `kd council show <thread>` renders cleanly without panels
- `kd peasant review <ticket>` shows pass/fail clearly
- `kd design` prints relative paths
- `kd tk show <id>` shows the file path
- Copied output from terminal pastes cleanly (the whole point)

### One Thing Missing

The design doesn't mention `doctor()` (line 1914), which uses `console.print()` with Rich markup for colored checkmarks (`[green]✓[/green]`). This is a minor one but should be included for completeness — simple `typer.echo("✓ python")` works fine since the checkmark is a unicode character, not a Rich feature.

### Summary

The design is solid and well-targeted. Keep Rich for Tables + Spinners only, drop everything else to `typer.echo()`. Use `## header` as your section separator format. Strip whitespace at write-time. Add `doctor()` to scope. Ship it.
