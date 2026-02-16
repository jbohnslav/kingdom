---
from: claude
to: king
timestamp: 2026-02-16T11:42:06Z
---



Good questions. Let me look at the relevant code to give grounded answers.Let me also look at how the auto-turn scheduler (3b76) will call this, so we get the interface right.Here are my recommendations:

### (1) Where should it live?

**`thread.py`.** It's a pure function over thread data — reads `Message` objects, returns a string. It has the same dependencies as `list_messages()` and `parse_message()` which already live there. Putting it in a new module would be over-organization for a single function. It doesn't depend on Textual, council, or agent infrastructure.

The caller (3b76, the auto-turn scheduler in `app.py`) would import it the same way it already imports `list_messages` and `add_message`.

### (2) Should we strip markdown headers agents add?

**No.** Don't try to normalize agent output. Reasons:

- You can't reliably distinguish structural headers the agent intended (e.g., `## Approach 1` / `## Approach 2`) from decorative ones (e.g., `## Response`). Stripping the wrong ones corrupts the message.
- The consuming agent sees the raw conversation as context, not as instruction. A `## Response` header in claude's prior message doesn't confuse codex — it just looks like how claude formatted its answer.
- If a particular agent's output format is genuinely problematic, the right fix is the agent's phase prompt (e.g., "Respond in plain prose, not with section headers"), not post-processing in the history formatter.

Keep it simple: body verbatim, as stored in the thread file.

### (3) Directed messages: include or filter?

**Include all messages.** Every member should see the full conversation, including directed messages. Reasons:

- The whole point of thread history injection is giving each agent **full cross-agent awareness**. Filtering out `@claude` messages from codex's view defeats this.
- In a real group chat, when someone directs a question at one person, everyone else still sees the question and the answer. That's the UX model we're building toward.
- The `to` field is already visible in the formatted output through the message body itself (the king typed `@claude what do you think?`). The agent can infer the addressing from context.

One minor consideration: should the format include the `to` field explicitly? I'd say no — it adds noise and the body text already contains the `@mention`. The format should just be `king: @claude what do you think about X?` which naturally communicates the direction.

### (4) Is the output format clear enough?

The proposed format is solid but I have one suggestion. Here's what the design says:

```
[Previous conversation]
king: What should we do about X?

claude: I think we should consider three approaches...

codex: I disagree because...

---
You are cursor. Continue the discussion. Respond to the points raised above.
```

**The format works.** LLMs understand `name: message` conversation logs. The `---` separator cleanly delineates history from instruction. One refinement:

**Make the suffix more specific.** "Continue the discussion" is vague. The agent might just say "I agree" and stop. Consider:

```
You are cursor. Respond to the conversation above. Share your analysis, build on or challenge the points raised, and provide specific recommendations where you have a different perspective.
```

But — this is a prompt engineering concern, not a format concern. I'd recommend keeping the *function* output generic (`You are {target_member}. Continue the discussion.`) and letting the **caller** (the auto-turn scheduler, or eventually config-driven phase prompts) customize the suffix if needed. So the function signature could be:

```python
def format_thread_history(tdir: Path, target_member: str, suffix: str | None = None) -> str:
```

With a sensible default suffix, and the caller can override. This keeps 213e simple while giving 3b76 flexibility.

### Summary

| Question | Answer |
|---|---|
| Where? | `thread.py`, alongside `list_messages()` |
| Strip headers? | No — body verbatim |
| Directed messages? | Include all — full visibility |
| Format? | Good as-is, add optional `suffix` parameter for caller flexibility |
