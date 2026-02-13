---
from: cursor
to: king
timestamp: 2026-02-13T22:09:03Z
---

<system_reminder>
You are acting as a council advisor. Answer the user's questions based on your analysis of the design doc and codebase.
</system_reminder>

The design document at `.kd/branches/cli-output-cleanup/design.md` is sound and aligns well with the "simple, readable, functional" philosophy.

### Recommendation on Rich Console

**Keep `Rich Console`, but scope it down.**

You should **not** go fully plain `typer.echo` because:
1.  **Tables**: `kd peasant status` uses `rich.table.Table`. Reimplementing a readable table with manual string formatting is unnecessary friction.
2.  **Spinners**: `kd council ask` uses `rich.progress` for the "Querying council members..." spinner. This provides valuable user feedback during blocking operations.

**Plan:**
-   **Retain**: `Console` (for tables/spinners) and `Table`.
-   **Remove**: `Panel` and `Markdown` (the renderer).
-   **Replace**: Use `typer.echo` (or `console.print` with simple strings) for everything else.

### Concerns & Considerations

1.  **Visual Hierarchy**: `Panel`s provided strong visual separation. When replacing them with text headers (e.g., `--- header ---`), ensure you use bolding or distinct spacing so the output doesn't become a "wall of text," especially for `kd council show` where multiple messages appear in sequence.
2.  **Raw Markdown**: Printing raw markdown (for `kd design show` or `kd ticket show`) is excellent for agents and `grep`, but ensure you strip any excessive newlines so it remains compact.
3.  **Path Formatting**: When fixing `kd design` to use relative paths, ensure you handle the case where the command is run from outside the repo root (though `kd` usually enforces root execution).

### Summary of Changes
-   **`src/kingdom/cli.py`**:
    -   Remove `from rich.panel import Panel` and `from rich.markdown import Markdown`.
    -   Update `council_show`, `peasant_logs`, `peasant_read`, `peasant_review` to use `typer.echo` with simple headers.
    -   Update `design_show` and `ticket_show` to print raw file content.
    -   Update `ticket_create` and `ticket_move` to print relative paths.
    -   Update `council_ask` to remove "runs" terminology if present.
    -   Update `ticket_move` to default to current branch.

I am ready to implement these changes if you command it.
