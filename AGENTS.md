
## Style

Optimize for simple, readable, functional code.

Ask yourself
    - "Is this a real problem or imaginary?" -> reject over-design
    - "Is there a simpler way?" -> pick the smallest working solution

Rules
    - Follow the Zen of Python (readability, explicitness, simplicity).
    - Prefer pure functions, clear data flow, and immutability. Prefer helper functions over bloated classes with tons of methods.
    - Use classes when necessary and avoid overly deep inheritance trees.
    - No premature abstraction (worse than premature optimization); duplicate a little before you abstract.
    - Standard library > lightweight deps > heavy frameworks.
    - Fail loudly and explicitly; never swallow errors.
    - If it's hard to explain, it's a bad design.
    - Deliver a minimal, well-named module with docstrings, type hints, and a tiny usage example/test.
    - No functions beginning with underscores! Private functions are fake in python. Bad: `_send_to_agent()`: good: `send_to_agent()`.

## Python execution

Always run Python in the repo venv:
- `source .venv/bin/activate && python my_script.py`
- or `uv run my_script.py`
