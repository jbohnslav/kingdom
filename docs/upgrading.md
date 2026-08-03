# Upgrading existing repositories

`kd update` upgrades the Kingdom CLI and refreshes configured host integrations.
Repository compatibility is separate: current `.kd` repositories migrate lazily
when an execution context first runs `kd tk current`.

## Back up first

Kingdom's state is plain files, so a complete backup is a directory copy. Stop
active Kingdom sessions, choose a timestamped destination outside `.kd`, and run:

```bash
cp -R .kd ../kd-backup-YYYYMMDD-HHMMSS
```

Keep that backup until the upgraded workflow and `kd doctor` both pass. The copy
includes tracked ticket history and ignored runtime bindings; it does not alter
the working repository.

## Supported lazy migration

Older repositories can identify current work with a generic `hand` assignment or
a terminal-context record. On the first `kd tk current`, Kingdom:

1. uses an exact legacy terminal binding when one exists;
2. otherwise migrates one unambiguous generic active ticket;
3. refuses to guess when multiple tickets are candidates;
4. changes only the active ticket's `assignee` line and writes a new ignored
   `.kd/runtime/contexts/` record.

Ticket IDs, unknown frontmatter, Markdown bodies, and Worklogs remain intact.
Backlog and archived tickets are not rewritten. Repeating the command is
idempotent, and a retry completes a migration interrupted between the ticket and
runtime-state writes.

Use `kd doctor` after upgrading. It is read-only and reports exact next steps for
ambiguous bindings, invalid or orphaned contexts, bad closure resolutions, and
stale configured Claude or Codex integrations.

## Roll back

The legacy terminal-context record is retained, so the previous Kingdom version
can continue to read it. The newer `.kd/runtime/contexts/` directory is ignored
runtime state and can be moved aside without changing ticket Markdown:

```bash
mv -n .kd/runtime/contexts ../kd-contexts-after-upgrade
uv tool install --force kingdom-cli==PREVIOUS_VERSION
```

To restore the complete backup, first preserve the upgraded state, then copy the
backup into place:

```bash
mv -n .kd ../kd-after-upgrade
cp -R ../kd-backup-YYYYMMDD-HHMMSS .kd
kd doctor
```

These commands are intentionally recoverable: neither the upgraded state nor the
backup is deleted. Inspect both copies before removing either one.
