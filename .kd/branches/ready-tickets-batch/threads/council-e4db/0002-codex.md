---
from: codex
to: king
timestamp: 2026-02-14T04:54:01Z
---

*Error: WARNING: proceeding, even though we could not update PATH: Operation not permitted (os error 1)
2026-02-14T04:54:01.095486Z ERROR codex_core::rollout::list: state db missing rollout path for thread 019c5a71-eb8e-7aa0-ac9b-d148029f6090
2026-02-14T04:54:01.104280Z ERROR codex_core::codex: failed to initialize rollout recorder: Operation not permitted (os error 1)
2026-02-14T04:54:01.104335Z ERROR codex_core::codex: Failed to create session: Operation not permitted (os error 1)
Error: Fatal error: Codex cannot access session files at /Users/jrb/.codex/sessions (permission denied). If sessions were created using sudo, fix ownership: sudo chown -R $(whoami) /Users/jrb/.codex (underlying error: Operation not permitted (os error 1))*
