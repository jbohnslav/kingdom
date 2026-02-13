---
from: codex
to: king
timestamp: 2026-02-13T22:12:03Z
---

I’ll review `.kd/branches/cli-output-cleanup/design.md` directly, then give a focused recommendation on `Rich Console` vs `typer.echo` and flag any design risks I see.
I have the design doc context; next I’ll quickly inspect current CLI usage of `Panel`, `Console`, and table rendering to ground the recommendation in the actual code paths.
I found all panel and markdown call sites in `src/kingdom/cli.py`; now I’m sampling the specific command implementations (`design`, `tk show`, `tk move`, council formatting) to check for hidden edge cases in the proposed changes.
I’m now checking user-facing strings and command behavior details (`runs` wording, defaults, path formatting) to identify any migration gaps that the design should explicitly cover.
I found existing tests that already assert some of these strings; I’ll inspect `test_cli_ticket` and `test_cli_council` to spot likely breakpoints and recommend where the design should be explicit to avoid regressions.
I confirmed there’s little test coverage for `tk show`/`tk move` output changes, so regressions are possible unless the plan adds tests; I’ll also check where `Rich` is still needed outside panels before giving the final recommendation.
I’ve identified a few concrete edge cases (especially around `tk move` default behavior and inconsistent whitespace stripping paths). I’m verifying the council write paths now so the recommendations are precise.
I’ve finished the pass and have enough detail to answer decisively. I’ll summarize recommendations and concrete concerns with file-level references so you can adjust the design before implementation.
**Recommendation**
Keep `Rich Console`, but narrow usage to `Table`/`Progress` only. Remove `Panel` + `Markdown` rendering. Going fully `typer.echo` now adds churn with limited benefit.

**Findings (ordered by severity)**
1. High: trailing-whitespace cleanup is currently scoped too narrowly in the design. If you only patch the worker path, sync council writes still bypass it (`src/kingdom/council/worker.py:48`, `src/kingdom/council/council.py:115`, `src/kingdom/cli.py:388`).
2. Medium: `tk move` default-to-current-branch needs explicit same-destination behavior. With current flow, defaulting can hit `FileExistsError` when the ticket is already there (`src/kingdom/cli.py:2281`).
3. Medium: scope mismatch inside the design doc: requirements say “replace panels” (`.kd/branches/cli-output-cleanup/design.md:21`), but decisions also imply removing Markdown renderer and “relative paths everywhere” (`.kd/branches/cli-output-cleanup/design.md:37`, `.kd/branches/cli-output-cleanup/design.md:39`). This should be reconciled to avoid unplanned scope growth.
4. Medium: “remove runs terminology” needs a compatibility policy, since user-facing strings are spread across commands/errors (`src/kingdom/cli.py:459`, `src/kingdom/state.py:378`) and tests currently assert old phrasing (`tests/test_cli_council.py:534`, `tests/test_done.py:66`, `tests/test_cli_ticket.py:274`).
5. Low: if you really mean “relative paths everywhere,” there are additional absolute-path outputs beyond `kd design` (`src/kingdom/cli.py:2007`, `src/kingdom/cli.py:2354`).

For the key question: I’d keep Rich for tables/progress and drop it for content rendering. If agent-parseability is a priority, consider showing progress spinners only on TTY (`src/kingdom/cli.py:379`, `src/kingdom/cli.py:695`).
