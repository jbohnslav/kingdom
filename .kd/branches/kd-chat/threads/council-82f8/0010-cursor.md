---
from: cursor
to: king
timestamp: 2026-02-16T21:19:43Z
---

I found a bug in `src/kingdom/tui/poll.py` where `tail_stream_file` was incorrectly handling file seeking for UTF-8 streams.

The code was opening the file in text mode (`"r"`) but seeking to a byte offset obtained from `stat().st_size`. In Python, `seek()` on a text file is only safe with offsets returned by `tell()`, not arbitrary byte offsets. This would cause crashes or decoding errors if the stream contained multi-byte characters (like emojis) and the offset didn't align with Python's internal text buffer state.

I've fixed it to open the file in binary mode (`"rb"`), seek to the byte offset, and decode the result safely.

```python:src/kingdom/tui/poll.py
<<<<
    try:
        with path.open("r", encoding="utf-8") as f:
            f.seek(offset)
            new_data = f.read()
    except (FileNotFoundError, OSError):
        return "", ""
====
    try:
        with path.open("rb") as f:
            f.seek(offset)
            new_data = f.read().decode("utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return "", ""
>>>>
```
