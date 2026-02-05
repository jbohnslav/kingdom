# Third-Party Repo Analysis Prompt

Analyze `third-party/<repo>/` to inform Kingdom's design.

## What to Look For

1. **Architecture** — How is it structured? What are the core abstractions?

2. **Design patterns** — What patterns do they use? (state machines, loops, event-driven, etc.)

3. **State management** — How do they persist and manage state across sessions?

4. **CLI/UX patterns** — How do they handle user interaction, commands, configuration?

5. **AI orchestration** — How do they invoke AI models? Fresh context vs session continuity? Single vs multi-model?

6. **Quality gates** — How do they verify work is "done"? What makes acceptance criteria good?

7. **Knowledge persistence** — How do they accumulate learnings across runs?

8. **Error handling** — How do they handle failures, retries, partial completion?

## Output Format

Create `docs/third_party/<repo>.md` with:

- **Overview** — What is this tool? What problem does it solve?
- **Core Architecture** — Key abstractions, state files, flow
- **Patterns Worth Adopting** — What they do well that Kingdom should consider
- **Patterns to Skip** — What doesn't fit Kingdom's model and why
- **Why Not Just Use This?** — If applicable, why Kingdom exists separately
- **Concrete Recommendations** — Specific changes or additions for Kingdom

## Guiding Questions

- What do they do better than Kingdom currently does?
- What constraints or disciplines do they enforce that Kingdom lacks?
- Where does Kingdom's approach (Council, Hand, structured phases) add value over theirs?
- What would break if we adopted their pattern wholesale?
