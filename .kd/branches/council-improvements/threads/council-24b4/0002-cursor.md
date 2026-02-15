---
from: cursor
to: king
timestamp: 2026-02-15T14:18:19Z
---

I recommend **Option 1: Prefix partial responses with an error marker**.

### Rationale

1.  **Immediate Fix**: It works with the existing `council retry` logic, which already checks `msg.body.startswith("*Error:")`. No changes to the retry command are needed.
2.  **User Visibility**: The user immediately sees *why* the response might be cut off or incomplete directly in the markdown, without needing to inspect file metadata.
3.  **Low Complexity**: It avoids refactoring `Message`, `add_message`, and `parse_message` to support arbitrary metadata, which is a larger architectural change better suited for a separate "thread metadata" ticket.

### Implementation Details

Modify `AgentResponse.thread_body()` to handle the case where both `text` and `error` exist:

```python
def thread_body(self) -> str:
    """Format response for writing to a thread message file."""
    if self.text and self.error:
        return f"*Error: {self.error}*\n\n{self.text}"
    if self.text:
        return self.text
    if self.error:
        return f"*Error: {self.error}*"
    return "*Empty response — no text or error returned.*"
```

This ensures `council retry` correctly identifies these as failures (because they start with `*Error:`), allowing the user to retry them, while preserving the potentially valuable partial work.
