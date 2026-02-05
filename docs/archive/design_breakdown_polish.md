# Design: Breakdown Stage Polish

## Goal
Refine the "Breakdown" stage of the Kingdom workflow to ensure `breakdown.md` artifacts are consistently machine-readable, enabling reliable automated ticket creation via `tk`.

## Context
The Kingdom MVP workflow transitions from "Design" (conceptual) to "Breakdown" (executable). The `breakdown.md` file serves as the bridge.
- **Problem**: The initial LLM prompts in `breakdown.py` were too permissive, leading to inconsistent Markdown formatting (e.g., missing checkboxes, wrong indentation) that the regex-based parser could not handle.
- **Impact**: `kd breakdown --apply` would fail to create tickets, breaking the "Hand -> Peasant" flow.
- **Constraint**: We are using Markdown as the interface (not JSON) to keep it human-readable and editable in the editor.

## Approach
We enforce strict output formatting through "one-shot" prompting examples rather than code changes to the parser. This preserves the flexibility of natural language while ensuring the structural "skeleton" remains parseable.

## Key Changes
1. **Strict Prompting (`src/kingdom/breakdown.py`)**
   - **Council Prompt**: Explicitly instructs advisors (Claude, Codex, Agent) to use the specific ticket format in their suggestions.
   - **Hand Update Prompt**: Added a "Format Requirement (strict)" section with a visual template for the Ticket block.

2. **Parser Logic (`src/kingdom/breakdown.py`)**
   - Relies on `parse_breakdown_tickets` which uses regex (`^- \[[ xX]\] (?P<id>[^:]+): (?P<title>.+)$`).
   - Requires 2-space indentation for metadata fields (`Priority`, `Depends on`, `Description`, `Acceptance`).

## Code Pointers

### Core Logic
- **`src/kingdom/breakdown.py`**
  - `build_breakdown_update_prompt`: The critical prompt enforcing the `breakdown.md` schema.
  - `parse_breakdown_tickets`: The function that converts Markdown text into Python dictionaries for `tk`.
  - `BreakdownUpdate`: Dataclass for the Hand's response structure (`<BREAKDOWN_MD>` and `<SUMMARY>`).

### CLI Integration
- **`src/kingdom/cli.py`**
  - `breakdown()`: The entry point. Handles the `--apply` flag to invoke `tk` subprocesses based on parsed tickets.

### Testing
- **`tests/test_breakdown.py`**
  - `test_parse_breakdown_tickets_extracts_ids_and_fields`: verifying the regex matches the expected format.

## Decisions
- **Markdown vs JSON**: Sticking with Markdown. While JSON is easier to parse, Markdown allows the user to read/edit the plan in the editor (`kd chat` side-by-side with the file).
- **Regex vs AST**: Using Regex for simplicity in the MVP. If formatting issues persist, we may move to a proper Markdown AST parser (e.g., `mistune` or `markdown-it-py`).

## Dependencies
- **`tk` CLI**: The system assumes a `tk` binary exists in the `$PATH` for ticket creation. This is currently external to the repo.
