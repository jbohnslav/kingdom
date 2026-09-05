# Supported host integration matrix

Verified: 2026-08-21

Kingdom: 1.0.0

Baseline commit: `a9120675c2cadcd62c9117f8e2cc329f48cdd7d9`

This matrix distinguishes observed host state from deterministic contract tests:

- **Live** — checked against the locally installed host without simulating its
  command or configuration.
- **Contract** — verified with checked-in host payloads and isolated CLI tests.
- **Limited** — supported only within the limitations stated in the table.
- **Unsupported** — Kingdom does not currently provide this integration path.

A live version check does not promote every lifecycle capability for that host
to live evidence. Host flows remain labelled Contract unless they were exercised
through a real host session.

| Host | Install and update | Session isolation and Stop | Compaction | Native subagents | Uninstall |
| --- | --- | --- | --- | --- | --- |
| Claude Code 2.1.220 | **Live:** authenticated host present and full repository hook set enabled. **Contract:** `kd plugin enable` installs or extends the supported hook set; `kd update` refreshes the skill. | **Live:** a real Claude session bound and logged its own ticket alongside a distinct real Codex task on the same branch; Stop completed without crossing contexts. **Contract:** invalid or stale state fails open. | **Contract:** pre- and post-compaction checkpoint requests target the exact bound ticket. | **Live:** a real Explore child inherited the parent ticket, completed, and recorded its handoff without taking ownership. **Contract:** explicit child assignment and missing-parent paths are covered. | **Live:** `kd plugin disable` and re-enable passed in an isolated repository. **Contract:** unrelated Claude settings and hooks are preserved. |
| Codex CLI 0.147.0-alpha.6.6 | **Live:** installed, activated, and idempotently refreshed through the personal marketplace. **Contract:** unrelated marketplace and user configuration are preserved. | **Live:** real Codex tasks matched their thread contexts alongside the distinct Claude session; Stop completed without crossing contexts. **Contract:** missing-host failure and malformed-hook failures are isolated and fail open. | **Contract:** pre- and post-compaction events repeat an exact-ticket checkpoint when needed. | **Live:** a real native child inherited the parent ticket and recorded its handoff after one transient noninteractive thread-lookup retry. **Contract:** explicit assignment and failure paths are covered. | **Live:** `kd plugin uninstall codex` removed six managed files, deactivated the host plugin, and a clean reinstall restored it. **Contract:** modified/unknown files and unrelated marketplace state are preserved; host-removal failure leaves local state unchanged. |
| Cursor Agent 2026.02.27-e7d2ef6; Cursor desktop 3.17.8 (`2fdd31c9f33f7fbe501f2d57772dc5bf64b63620`, arm64) | **Limited / Live:** installed versions were observed. `kd update` refreshes the skill only when a Cursor home already exists; Kingdom does not install `.cursor/hooks.json`. | **Limited / Contract:** stable conversation IDs isolate bindings and Stop can issue one exact-ticket `followup_message`; arbitrary shell commands are not guaranteed to inherit the conversation context. | **Limited / Contract:** `preCompact` can request a checkpoint. Cursor has no `postCompact`, so Kingdom cannot repeat the request after compaction. | **Limited / Contract:** `subagentStart` records stable parent/child provenance, but an allowed start cannot inject ticket context. `subagentStop` omits the child ID, so exact concurrent-child completion is unsupported. | **Unsupported:** Kingdom has no Cursor hook installation to reverse. Remove a copied Kingdom skill manually if it is no longer wanted. |

## Cursor capability boundary

Cursor support follows the limited-adapter result in
[Cursor hook capability](cursor-hooks.md), not Claude or Codex parity. The
[Cursor Hooks reference](https://cursor.com/docs/hooks) documents the stable
conversation and subagent identifiers used by the contract. The
[Cursor 3.11 changelog](https://cursor.com/changelog/side-chat) introduced the
broader lifecycle surface. Cloud agents also omit `sessionStart` and
`sessionEnd`, and may begin before repository hooks load.

## Deterministic evidence

`tests/fixtures/host_events.json` records content-free payloads for every event
Kingdom accepts from each host. `tests/test_host_integration_matrix.py` keeps
those fixture sets aligned with the configured Claude and Codex hooks and the
limited Cursor adapter, proves same-branch host sessions retain separate current
tickets, and locks this document's dated/versioned contract.

The shared lifecycle, hook, plugin, skill-update, and execution-context tests add
the detailed behavior behind each Contract cell. Live host checks are a release
task because the host binaries and authenticated sessions are not available in
portable CI.
