# Upgrading existing repositories

`kd update` upgrades the Kingdom CLI and refreshes configured host integrations.
Current Kingdom reads one repository layout and one execution-context format;
it does not migrate older runtime formats automatically.

## Current formats

- Branch tickets and threads live under `.kd/branches/<branch>/`.
- Session state uses `.kd/branches/<branch>/sessions/<agent>.json`.
- Current-ticket bindings live under `.kd/runtime/contexts/` and identify their
  owning host execution context. Ordinary terminal sessions also use this store.
- Peasant worktrees use `.kd/worktrees/<branch>/<ticket>/`.
- Ticket IDs are used as stored, without alternate filename or `kin-` aliases.
- Closed tickets need explicit resolution fields; readiness checks do not infer
  outcomes from old status or body text.
- Council response messages carry explicit status metadata.

Old `.kd/runs/` bundles, plaintext `.session` files, terminal-context records,
unnamespaced worktrees, and generic `hand` assignments are no longer imported or
used as fallback state. Historical ticket files can remain in the repository;
retaining them does not make them current runtime inputs. No bulk rewrite of
closed history is required for unrelated active workspaces.

## Back up and verify

Stop active Kingdom workers before changing versions. Preserve the complete
state, including ignored runtime files, outside the working directory:

```bash
cp -R .kd ../kd-backup-YYYYMMDD-HHMMSS
kd update
kd start
kd doctor
kd tk current
```

Check the selected workspace and execution context before resuming work. If an
old binding is absent, explicitly select the intended ticket with `kd tk start`;
starting a ticket reassigns it to the calling context. Diagnose
invalid current state with `kd doctor`. Refresh the supported host integration
with `kd plugin enable` or the appropriate `kd plugin install` command instead
of relying on old hook-layout migration.

Configuration uses `effort`; remove the old `reasoning_effort` key. `kd start`
is idempotent and has no `--force` option. In ticket creation, `-t`/`--title`
sets the title and `--type` sets the type. Optional design documents are created
with `kd design` and displayed with `kd design show`; they need no approval step.

## Workspace lifecycle

`kd start <branch>` initializes or selects a workspace. `kd status --check`
checks its tickets and closure evidence without changing state. There is no
workspace `done` flag or global finalizer: ticket close/defer operations clear
their bindings, `kd status --prune-stale` removes stale context bindings, and
`kd peasant accept`, `clean`, and `prune` own worker cleanup.

## Roll back

Restore the previous CLI version and the matching complete backup together.
Preserve the upgraded state first:

```bash
mv -n .kd ../kd-after-upgrade
cp -R ../kd-backup-YYYYMMDD-HHMMSS .kd
uv tool install --force kingdom-cli==PREVIOUS_VERSION
kd doctor
```

Neither state copy is deleted by these commands. The current version does not
maintain old runtime records for older releases to read.
