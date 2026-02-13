---
id: kin-b908
status: closed
deps: []
links: []
created: 2026-02-13T18:07:05Z
type: bug
priority: 2
---
# Message sequencing race in thread writes

next_message_number() + add_message() is non-atomic. Concurrent council members in --sync mode can get same sequence number, losing messages. Fix with O_EXCL or retry loop. (thread.py:202-259, #2 from PR #6 review)
