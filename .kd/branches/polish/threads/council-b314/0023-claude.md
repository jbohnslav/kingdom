---
from: claude
to: king
timestamp: 2026-02-17T11:09:32Z
---



Good call — let me think about what PyPI and GitHub expect for a proper public package.

Here's what you need beyond the code itself:

**PyPI metadata (in `pyproject.toml`):**
- `description` — currently says "Add your description here"
- `license` — Apache 2.0
- `authors` — your name/email
- `readme` — points to README.md (so PyPI renders it as the project page)
- `requires-python` — already set but worth verifying
- `classifiers` — Development Status, License, Python versions, Topic
- `urls` — Homepage, Repository, Issues (shows as sidebar links on PyPI)
- `keywords` — discoverability on PyPI search

**Files in repo:**
- `LICENSE` — actual Apache 2.0 license file (required for the license classifier to be meaningful, and GitHub shows it in the repo header)
- `README.md` — this becomes your PyPI landing page and GitHub front page. Needs: what it is, install command (`pip install kingdom-cli`), quick usage example, link to docs if any

**GitHub repo settings (manual):**
- Repository description and topics (tags) — shows in search results
- "Releases" section will auto-populate from the workflow

**Things people forget:**
- `py.typed` marker if you want to advertise type hint support (you have type hints throughout)
- `CHANGELOG.md` — optional since GitHub auto-generates release notes, but some users expect it
- Verify the `console_scripts` entry point works from a clean `pip install` (not just your dev venv) — worth a quick `uvx` or `pipx` test

Let me create the ticket.Created backlog ticket **02b5**. I'd suggest tackling it before the first real publish — `0.1.1` landing on PyPI with "Add your description here" and no license isn't a great first impression. Might be worth holding the version bump until this ticket is closed.
