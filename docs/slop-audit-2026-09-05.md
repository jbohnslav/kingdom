# Kingdom cruft audit — September 5, 2026

**Implementation ledger:** Completed on `codex/cleanup-dead-code` through
initial cleanup `4088` and full follow-up epic `1465`. Locations and proposals
below describe the audited revision before implementation.

| Findings | Ticket | Result |
| --- | --- | --- |
| 1–6 | 4088 | Abandoned features, writers, renderers and test-only helpers removed. |
| 7–9 | 79a4 | Direct module imports, named TicketMatch fields and one effort config key. |
| 10–11 | aeec | Inert force option, overloaded title/type flag and design approval removed; useful aliases retained. |
| 3 reader, 12, 15 historical state | 80d2 | One current runtime format; old migrations, dual stores, closure/ID inference and body-status sniffing removed. |
| 13–15 | dcab | One live streaming function, normalized hook handlers, explicit status and consistent latest-response retry. |
| 16–19 | 8456 | Behavioral assertions repaired, snapshots/skips pruned and Textual integration enabled in CI/release. |
| 20 and final guidance | 67f9 | Stale scaffolding removed, historical designs archived, current docs and smoke/workflow setup aligned. |

The King waived preserving compatibility for the 508 historical closed tickets.
Their files remain intact; they no longer require runtime inference or a
migration subsystem. Concurrent mutation safeguards, ordinary terminal identity,
current provider adapters and useful aliases remain supported.

The two Claude workflows remain because they serve distinct triggers: automatic
review when a PR opens, and explicit `@claude` requests. Release validation
remains separate from CI because it gates publication. The known Cursor
result-event truncation regression remains a strict expected failure; historical
fixture skips and missing-module skip paths are gone. A separately discovered
design-template rendering issue is tracked as backlog `cdc4`.

The following sections preserve the original audit evidence and baseline counts.

There is concrete deletion work here. The strongest candidates are abandoned
features kept alive by their tests, internal compatibility interfaces, and tests
that assert prose or mocks instead of application behavior. A conservative count
of the confirmed dead modules and definitions below is **453 source lines**, before
removing their imports, surrounding comments, and associated tests. This is a
deletion floor, not an estimate for the broader compatibility cleanup.

The original audit left product code and tests unchanged. Its findings cover the source tree, test tree, CLI wiring,
configuration, state migration, worker loops, TUI, scripts, packaging, skills,
public documentation, and checked-in GitHub workflows. Static reference checks
were followed through aliases and actual callers; they are not proof of external
usage or a line-by-line correctness review of every function.

## 1. Delete the abandoned synthesis feature

**Evidence:** `src/kingdom/synthesis.py:8` defines `build_synthesis_prompt`; its only
callers are in `tests/test_synthesis.py`. The source module is 42 lines; its test
file is 171 lines with 12 tests. Some tests check only that literal instructions,
newlines, or Unicode survive string assembly.

**Action:** Delete both files. There is no current CLI or worker path to preserve.

## 2. Delete the abandoned breakdown writer and design-update pipeline

**Evidence:** All of `src/kingdom/breakdown.py` is unreachable from current product
code. Its two tests in `tests/test_breakdown.py` exercise template creation and a
trailing newline. In `src/kingdom/design.py`, `write_design` (line 72), both prompt
builders (90 and 115), the tagged-response parser (167 and 178), and `DesignUpdate`
(34) belong to an automated design-editing workflow with no current caller.
Five of the six tests in `tests/test_design.py` protect that abandoned code.

**Action:** Delete the breakdown module and tests. Reduce the design module to
template creation/read/initialization and retain its live CLI coverage. Existing
Markdown design and breakdown documents do not need deletion.

## 3. Remove the old council bundle writer; retire its separate reader

**Evidence:** `src/kingdom/council/bundle.py:18` creates `run-*` directories, but
`create_run_bundle` and `generate_run_id` are only re-exported from
`council/__init__.py`; no product or test caller creates bundles through them.
The entire 69-line module is dead. Separately, `cli/council.py:698` retains a
legacy bundle reader, with dispatch at line 746 and a legacy fixture test in
`tests/test_cli_council.py:372`.

**Action:** Delete the writer and exports immediately. Remove the `run-*` reader
and old `last` route after checking any other repositories whose history matters.
This checkout has zero legacy bundles under `.kd/branches/*/logs/council/run-*`.
Current thread history is a separate, live feature.

## 4. Delete the TUI renderer that the TUI does not render

**Evidence:** `src/kingdom/tui/widgets.py:114` defines a 58-line
`ColoredMentionMarkdown` renderer. `MessagePanel.compose` instead yields
Textual's native Markdown widget at line 206. Only the ten tests starting at
`tests/test_tui_widgets.py:290` instantiate the old renderer.

**Action:** Delete the class, its dedicated imports and tests. Also delete
`MessagePanel.compose_text` at line 208 and `CommandHintBar.first_match` at line
529: both are called only by tests. Keep current Markdown rendering and command
completion behavior tests.

## 5. Delete the superseded synchronous panel-removal method

**Evidence:** All five production call sites use `await_remove_member_panels`.
`ChatApp.remove_member_panels` at `src/kingdom/tui/app.py:1239` survives only for
tests. `tests/test_tui.py:2854` spies on this unused method, so its negative
assertion cannot detect calls to the actual asynchronous removal method.
The direct unit test at line 2936 also exercises the obsolete implementation.

**Action:** Delete the synchronous method and its direct test. Keep the useful
queue assertions in the surrounding tests, but replace the obsolete spy with
checks against the real DOM or active removal path.

## 6. Delete unused helpers, including helpers exported for tests

No production call sites were found for these definitions:

| Location | Definition | Treatment |
|---|---|---|
| `src/kingdom/cli/ticket.py:140` | `format_ticket_line` | Delete; seven tests exercise a formatter the CLI never uses. |
| `src/kingdom/cli/config.py:130` | `check_cli` | Delete with its tests and ineffective doctor mocks; doctor uses `check_agent_runtime`. |
| `src/kingdom/cli/helpers.py:89` | `not_implemented` | Delete the unused scaffold. |
| `src/kingdom/cli/helpers.py:114` | `ensure_feature_branch` | Delete the obsolete branch-creation path. |
| `src/kingdom/cli/helpers.py:137` | `skill_install_targets` | Delete; production uses `skill_targets` directly. |
| `src/kingdom/cli/council.py:225` | `topic_for_location` | Delete the unused alternative topic helper. |
| `src/kingdom/cli/council.py:1416` | `display_rich_panels` | Delete; current rendering does not call it. |
| `src/kingdom/ticket.py:374` | `write_ticket_content` | Delete the unused locking wrapper; retain the active atomic writer and locking paths. |
| `src/kingdom/ticket.py:823` | `get_ticket_location` | Delete; tests are its only callers. |
| `src/kingdom/state.py:607` | `execution_context_is_stale` | Delete or use it deliberately; current stale-context logic does not call it. |
| `src/kingdom/state.py:826` | `append_jsonl` | Delete. |
| `src/kingdom/state.py:930` | `clear_current_run` | Delete. |

The dead `check_cli` is particularly misleading: many doctor tests patch
`kingdom.cli.check_cli`, but doctor never calls it. Patching the defining
module's helper to raise still allowed all 18 agent-doctor tests to pass.

## 7. Undo internal API compatibility in the CLI package

**Evidence:** `src/kingdom/cli/__init__.py:23-78` contains re-exports explicitly
marked as used by tests. `tests/test_cli.py:81` asserts their continued existence.
Some submodules import the top-level CLI back again to access their own helpers:
`cli/peasant.py:486`, `1038`, and `1830`, and `cli/council.py:1460`.
`cli/display.py:12` defines a `NO_COLOR` constant it does not use; `styled_echo`
imports the CLI package and reads that package's duplicate constant instead.

**Action:** Keep the actual entry points, use direct imports where functionality
lives, and patch those actual locations in tests. Remove the re-export contract
test. Put color ownership in the display module. These are internal Python APIs,
not a useful compatibility promise for a personal CLI.

## 8. Replace the hand-written two-tuple compatibility object

**Evidence:** `src/kingdom/ticket.py:555` implements `TicketMatch` with slots,
constructor, iterator, length, indexing, and repr to preserve two-item tuple
access while adding a third property, `location`.

**Action:** Use a small frozen dataclass with `ticket`, `path`, and `location`.
Update internal callers to named attributes. Do this as a coordinated change:
tuple unpacking and indexing are still live, so deleting the methods alone is
not safe. This removes an obsolete interface rather than introducing a new
abstraction.

## 9. Retire the `reasoning_effort` alias

**Evidence:** `src/kingdom/config.py:32-41` carries an extra dataclass field and
constructor translation solely for the old name. Validation branches at line
216 and source-attribution fallback in `cli/config.py:108` also preserve it.
Tests maintain both APIs. The current local config has zero agent entries using
the old key.

**Action:** Keep `effort`, update any other saved configs once, and remove the
constructor alias, validation branches, display fallback, and alias tests.
Keep the provider's `model_reasoning_effort` command-line setting: that is an
external API parameter, not Kingdom's deprecated alias.

## 10. Remove inert and overloaded CLI compatibility

**Evidence:** `src/kingdom/cli/__init__.py:175` accepts `kd start --force` but never
reads it. Manual `uv run kd start --help` confirms it occupies a help row solely
to advertise compatibility. `cli/ticket.py:408-445` also makes `-t` mean either
title or ticket type depending on whether a positional title was supplied.

**Action:** Delete `--force`; tracked separately as backlog ticket `aeec` after
observing it in help. Choose one meaning for `-t`, keeping explicit `--type` for
type. Keep useful muscle-memory aliases such as `tk`; those have current value.
The `council ls` alias at `cli/council.py:984` can share the existing function via
another command decorator instead of duplicating its signature in a wrapper.

## 11. Drop the design-approval ceremony if you do not use the annotation

**Evidence:** `src/kingdom/cli/design.py:78` writes `design_approved=true`.
The only production reads are for status JSON and the displayed approval label
in `cli/__init__.py:389`, `399`, and `510`. Nothing gates execution on approval.
The skill and README still tell agents to run it.

**Action:** Remove the command, hidden `accept` alias, field presentation, and
instructions if the annotation is not useful to you. Keep plain `kd design`
initialization and `show` if you use them. This is a workflow choice, unlike the
confirmed dead design-update code. Also collapse `get_branch_paths` →
`get_design_paths` at `cli/design.py:30-47`; building four paths to discard two
is leftover structure from the larger planning workflow.

## 12. Retire runtime migrations as a coordinated cleanup

**Evidence:** `session.py:74-125` migrates `.session` files during reads.
`worktree.py:25` checks old un-namespaced directories.
`cli/ticket.py:966-1074` implements legacy execution-binding migration.
`state.py:616-714` and its cleanup callers maintain the old terminal-context
store; `doctor.py:262` diagnoses it; `cli/hook.py:300-350` falls back through it
and an opt-in subprocess invoking `kd tk current`.

**Action:** Remove session-file and old worktree-path support after a one-time
inventory of relevant repositories. For terminal contexts, remove dual writes
at `cli/ticket.py:1109` and `2021` together with migration/read/cleanup/doctor
support. Do not just delete a reader: current code still writes the old format.
Preserve terminal identity resolution into the current execution-context model;
ordinary shell use still needs it. Verify supported host hooks against the
single current context store before retiring the fallback.

This checkout has no legacy session files, council run bundles, terminal-context
records, or worktree directories. That supports removal here, but is not an
inventory of your other Kingdom repositories.

## 13. Normalize hook inputs only at the CLI boundary

**Evidence:** `src/kingdom/cli/hook.py:448` documents `handler_event` as support
for direct legacy handler calls. Each handler accepts `HostEvent | dict` and
normalizes again, while the real CLI already calls `normalize_host_event` at
line 823 before dispatch.

**Action:** Have internal handlers accept `HostEvent`. Test provider payload
normalization at the entry point; have handler unit tests construct normalized
events. Retain real Claude/Codex/Cursor normalization, validation, and host
differences.

## 14. Consolidate duplicated worker streaming

**Evidence:** `harness.py:423` and `lord_harness.py:890` implement the same Popen,
two pipe-draining threads, wait/join, and CompletedProcess assembly. They already
diverge: the peasant opens/closes its log per line, while the lord holds a
buffered file open and does not explicitly flush per line. Both suppress log
write errors.

**Action:** Share one small streaming function, with a deliberate log-flush and
error-reporting policy. Keep subprocess lifecycle and concurrent pipe tests.
There is no need for a runner class hierarchy. This is a live consolidation,
so verify incremental output and shutdown, not just returned strings.

## 15. Remove fallback states that only synthetic objects can produce

**Evidence:** `cli/council.py:1102` has a backward-compatibility fallback for
missing `ThreadStatus.member_states`, but `thread_response_status` fills a state
for every expected member. Elsewhere, old message-body error inference is
repeated in `thread.py:666`, `tui/app.py:666`, and `cli/council.py:1345`.

**Action:** Remove the synthetic missing-state fallback and update incomplete
test objects. For persisted messages, first inventory old histories; either
migrate their status once or centralize interpretation. Do not confuse obsolete
test constructors with historical data that actually exists.

## 16. Repair tests that pass with the behavior disabled

**Evidence:** These tests passed after an in-memory mutation disabled both quit
slash commands and `ChatApp.action_interrupt`:

- `tests/test_tui_integration.py:892` — `test_quit_exits`
- `tests/test_tui_integration.py:908` — `test_escape_with_no_active_queries_exits`
- `tests/test_tui_integration.py:955` — `test_second_escape_exits`

The test context manager cleans up the app regardless; leaving its context does
not prove that the key or command caused exit. Mutation result: **3 passed**.

**Action:** Assert exit was requested by the interaction before context cleanup,
or observe the application stopping. These behaviors deserve tests; the current
tests supply false confidence. Likewise, `tests/test_init.py:806` and `823`
claim to test warnings but assert neither warning output nor failure status.

## 17. Delete historical fixture skips and missing-module escape hatches

**Evidence:** `tests/test_ticket.py:726-765` has three tests tied to specific
`.tickets/kin-*.md` files from the old project layout. All three skip now.
`tests/test_parsing.py:7-18` skips its entire module on ImportError because a
parent worktree might not contain the implementation yet. `test_council.py:865`
similarly makes the worker suite conditional on its own module existing.

**Action:** Delete obsolete repository-ticket tests, or turn any unique parser
case into an explicit fixture. Remove missing-module skips; broken imports in
the current source tree should fail. Also remove the redundant late sys.path
insertion in `tests/conftest.py:14`: pytest.ini already sets `pythonpath = src`,
and conftest imports Kingdom before that insertion anyway.

## 18. Cut prose snapshots and release-specific test obligations

**Evidence:** `tests/test_public_docs.py` is 315 lines largely asserting headings,
phrases, literal shell implementation, and release-note ticket IDs. The test at
line 130 insists on a list of historical IDs and their exact `.kd` paths.
`tests/test_tooling_config.py:36` hardcodes release `1.0.2`, forcing future
version bumps to edit a test. `tests/test_skill.py` adds ordering/wording checks
on top of useful structure and package-mirror validation.

**Action:** Delete wording, historical-ticket, and exact implementation snapshots.
Compare version surfaces to project metadata instead of a release literal.
Keep executable doc examples (`tests/test_docs.py`), packaged artifact checks,
skill structure/mirror tests, CLI behavior checks, and a small number of genuine
workflow policy assertions. Tests for intentional automatic-release or review
triggers have more value than tests for the prose describing them.

## 19. Put useful integration tests on an actual execution path

**Evidence:** `tests/conftest.py:22-36` skips Textual integration tests without
`--run-textual-integration`. Both CI and release run plain `uv run pytest`.
The 46 opt-in tests passed locally in **12.51 seconds**; the normal suite took
25.88 seconds. No checked-in GitHub job enables their flag.

**Action:** Enable them in CI, or add an explicit job that runs them. First fix
the vacuous exit assertions. The skip mechanism is not itself dead code, but it
currently keeps the most realistic TUI coverage outside both automated gates.
There is also one non-strict expected failure at `tests/test_agent.py:765` for a
short Cursor result overwriting richer streamed text. Keep that regression as
evidence of a real unresolved behavior; use strict xfail or fix the behavior so
an unexpected pass cannot silently leave a stale exemption.

## 20. Remove stale docs and one-off scaffolding

**Evidence:** `docs/backlog.md` still asks for Ruff, pre-commit, and CI, all of
which exist. `docs/architecture.md:3-27` calls the project design-first, lists
nonexistent `cli.py`, describes breakdown generation, and presents abandoned
synthesis/bundle code as current architecture. This contradicts the current
ticket-first README and real CLI. `scripts/add_submodule.py` is a 75-line wrapper
around `git submodule add` with its own one-line `run` wrapper; there is no tracked
`.gitmodules` file or caller elsewhere in the active scripts/workflows.

**Action:** Delete the stale backlog document. Rewrite the architecture page to
describe current modules after cleanup. Delete the one-off submodule helper if
you no longer use it manually; the Git command is sufficient. Move explicitly
historical design documents into the existing archive if their current placement
causes confusion. Do not erase ticket history just to reduce file count.

The four GitHub workflows have real triggers; none is proven dead from source
alone. Remove copied TypeScript path examples in
`.github/workflows/claude-code-review.yml:6-12` and unused example comments in
`claude.yml`. CI and release use divergent action revisions; align their shared
setup when touching them. Whether the `@claude` workflow is used requires run
history or your preference, so it is a candidate to assess, not a confirmed
deletion. Do not remove release validation merely because CI also validates.

## What to preserve

- The baseline had **508 closed tickets without explicit resolutions** out of
  602 ticket Markdown files. The King subsequently waived this preservation
  gate: old files remain, but closure inference and migrations are removed.
- File locks, atomic writes, relocation handling, and worker start serialization
  address real concurrent processes. Small wrappers that enforce those
  boundaries are useful.
- `extract_error` initially looked unused to a simple AST name count, but
  `council/base.py:13` imports it as `agent_extract_error` and calls it at line
  266. It is live. Textual framework hooks similarly are not dead merely because
  direct Python callers are absent.
- Provider event-format handling and auth failures are external integration
  concerns. Do not label them compatibility cruft based on the word "legacy"
  alone.
- `TicketMatch` location information, ticket collision checks, archive-aware
  lookup, and managed skill edit preservation have concrete current consumers.

## Suggested cleanup order and validation

1. Delete confirmed dead modules, definitions, and their dedicated tests
   (findings 1–6). This offers the lowest-risk reduction.
2. Remove test-only re-exports, internal tuple compatibility, obsolete constructor
   aliases, and duplicated paths; update live callers (7–10, 13, 15).
3. Fix false-confidence tests, prune prose snapshots, and enable integration
   coverage (16–19).
4. Retire old runtime formats with a small repository inventory; decide on the
   approval annotation; consolidate worker streaming (11–14).
5. Update current docs and delete one-off scaffolding (20).

Validation performed for this audit:

- `uv run pytest -q`: **2,359 passed, 49 skipped, 1 xfailed**.
- `uv run pytest -q --run-textual-integration tests/test_tui_integration.py`:
  **46 passed**. The remaining three default skips are missing old ticket files.
- In-memory quit/interrupt mutation: the three purported exit tests still passed.
- In-memory obsolete doctor-helper mutation: **18 agent-doctor tests passed**.
- Manual `uv run kd start --help`: confirmed the accepted-but-inert force option.
- Source-reference inspection and local legacy-state inventory; no provider
  model calls, workflow changes, or product-code mutations were needed.
