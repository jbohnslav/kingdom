# Council Patterns and Usage

The council is a group of AI models (typically claude, cursor, codex) that provide independent perspectives on design questions. Each member responds in parallel without seeing the others' answers.

## When to Consult the Council

**Good uses:**
- Architectural decisions with multiple valid approaches
- Technology or library selection with trade-offs
- Design patterns where the right choice depends on context
- Reviewing code changes or design docs for blind spots
- When the King is uncertain and wants diverse perspectives

**Skip the council for:**
- Straightforward implementation tasks
- Bug fixes with obvious root causes
- Tasks where the King has already made a decision
- Simple refactoring or formatting changes

## Querying

```bash
# Query all members (default: creates a new thread)
kd council ask "How should we handle authentication?"

# Continue the current thread (for follow-up questions)
kd council ask --continue "What about the edge case with expired tokens?"
kd council ask -c "Short form works too"

# Query a specific member
kd council ask --to claude "Review this approach"

# Run in background (async)
kd council ask --async "Long research question"
kd council ask --async --no-watch "Fire and forget"
```

## Threads

Council conversations are stored in `.kd/branches/<branch>/threads/<thread-id>/`. Each message is a numbered markdown file (`0001-king.md`, `0002-claude.md`, etc.).

Every `kd council ask` creates a new thread by default. Use `--continue` / `-c` to append to the current thread for multi-round discussions on the same topic.

```bash
kd council list                    # see all threads
kd council show <thread-id>       # display a thread
kd council watch <thread-id>      # watch for incoming responses
```

## Reading Responses

Summarize council responses for the King when they inform the active decision. Present the main agreements, disagreements, and any recommendation, then point to the thread for full context. Preserve the tensions — don't flatten dissent into false consensus.

## Async and Streaming

Long queries can take several minutes per member. When using `--async`:
- Responses stream to `.stream-<member>.md` files in the thread directory
- These are cleaned up after the full response is written
- If a query times out, partial output is preserved in the thread
- Use `kd council watch <thread-id>` to monitor progress

## Sessions

Council members maintain session state across queries on the same branch. To clear sessions and start fresh:

```bash
kd council reset
```
