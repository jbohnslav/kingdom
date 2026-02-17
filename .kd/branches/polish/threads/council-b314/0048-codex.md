---
from: codex
to: king
timestamp: 2026-02-17T12:38:43Z
---

I’ll apply this directly in `README.md`: switch install to `uv tool install kingdom-cli` and collapse the workflow section to the single flow we aligned on using `kd chat`, `kd breakdown`, ticket review, execution, and `kd done`. I’m reading the current README now and then patching it.
I found the current README still has the old duplicated `Quick Start`/`Core Workflow`/`Commands` sections and `pip install`. Next I’m validating the exact CLI subcommands once, then I’ll patch the README in one pass with your preferred single flow and `uv tool install kingdom-cli`.
I validated the commands and will now patch `README.md` to a single “Getting Started” workflow with `kd chat` as the design step, remove the redundant workflow/commands sections, and switch install to `uv tool install kingdom-cli`.
README is patched with the exact flow and install command. I’m doing a quick read-through now to confirm it’s clean and non-redundant before I hand it back.
I noticed one grammar issue in the second intro paragraph (“debates … break”). I’m making a tiny wording cleanup there so the top description reads cleanly while preserving your exact meaning.
Applied in `README.md`.

Changes made:
- Switched install command to `uv tool install kingdom-cli`.
- Replaced redundant `Quick Start` + `Core Workflow` + `Commands` sections with one concise `Getting Started` flow:
  - `kd start`
  - configure `.kd/config.json` (`kd config show`)
  - `kd chat --new`
  - `kd breakdown`
  - `kd ticket list` / `kd ticket show <id>`
  - serial (`kd work <id>`) or parallel (`kd peasant start <id>`)
  - `kd done`
- Kept the `.kd/` structure section and dev/license sections.
- Fixed grammar in the top metaphor paragraph.

If you want, I can make one more pass for tone/wording polish only and then commit.
