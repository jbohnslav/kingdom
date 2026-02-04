# LLM Council: Analysis for Kingdom

LLM Council is a multi-model deliberation system that queries several LLMs in parallel, has them anonymously evaluate each other's responses, and synthesizes a final answer via a "chairman" model. It's designed for transparency—users can inspect every stage of the reasoning process.

Source: `third-party/llm-council/`

---

## Overview

**Problem it solves**: Single-model responses can be biased, incomplete, or wrong. LLM Council addresses this by:
1. Gathering multiple perspectives (Stage 1: parallel queries)
2. Having models critique each other without knowing identities (Stage 2: anonymized peer review)
3. Synthesizing the best answer using all evidence (Stage 3: chairman synthesis)

**Tech stack**: Python FastAPI backend + React frontend, OpenRouter for model access, JSON file persistence.

**Core insight**: Anonymization in peer review prevents model favoritism (e.g., Claude might prefer Claude-style responses).

---

## Core Architecture

### 3-Stage Pipeline

```
User Query
    ↓
Stage 1: Parallel queries to all council models (GPT, Gemini, Claude, Grok)
    ↓ (collect all responses)
Stage 2: Each model ranks all responses (anonymized as "Response A", "Response B", etc.)
    ↓ (aggregate rankings)
Stage 3: Chairman model synthesizes final answer using all evidence
    ↓
Return: Full 3-stage response + metadata
```

### Key Abstractions

| Layer | Responsibility |
|-------|----------------|
| `council.py` | 3-stage workflow orchestration |
| `openrouter.py` | Async model API calls with 120s timeout |
| `storage.py` | JSON-based conversation persistence |
| `config.py` | Model list, API keys, ports |

### State Model

Each assistant message contains:
```python
{
  "role": "assistant",
  "stage1": [{"model": "...", "response": "..."}],  # Raw responses
  "stage2": [{"model": "...", "ranking": "...", "parsed_ranking": [...]}],  # Peer evals
  "stage3": {"model": "...", "response": "..."}  # Chairman synthesis
}
```

**Critical design choice**: Context is NOT accumulated across messages. Each query is stateless—models don't see prior conversation turns.

---

## Patterns Worth Adopting

### 1. Anonymized Peer Review

**What they do**: Stage 2 presents responses as "Response A", "Response B" with a shuffled mapping. Models evaluate without knowing which model produced which response.

**Why it matters**: Prevents brand-loyalty bias. Without anonymization, Claude might favor Claude-style responses, GPT might favor GPT-style responses.

**For Kingdom**: When implementing Council synthesis, consider anonymizing responses before asking any model to evaluate or merge them.

### 2. Transparent Deliberation

**What they do**: All intermediate results are visible—users can inspect each model's raw response, see how models ranked each other, and understand the aggregate scores.

**Why it matters**: Builds trust. When the final answer is wrong, users can debug which stage failed.

**For Kingdom**: Log all Council member responses in `.kd/runs/<feature>/logs/` (already planned). Consider structured JSONL that captures the full deliberation record.

### 3. Graceful Degradation

**What they do**: If 1 of 4 models fails, continue with 3. If ranking parsing fails, use regex fallback. Never fail the whole request due to one model.

**Implementation**:
```python
# Partial results accepted
if response is not None:
    stage1_results.append(...)

# Parse fallback
def parse_ranking_from_text(text):
    if "FINAL RANKING:" in text:
        # Try strict format first
        ...
    # Fallback: extract any "Response X" patterns
    return re.findall(r'Response [A-Z]', text)
```

**For Kingdom**: Already doing this in `CouncilMember.query()` with timeout handling. Extend to synthesis—if one agent times out, synthesize with available responses.

### 4. Progressive UI Rendering

**What they do**: Server-Sent Events emit stage completion signals. Frontend shows spinners during each stage, then renders results as they arrive.

**For Kingdom**: The log-tailing tmux UI (`kd attach council`) already enables this. Could enhance Hand REPL to show partial results incrementally.

---

## Patterns to Skip

### 1. Stateless Queries

**What they do**: Each message is independent. Models don't see conversation history.

**Why skip**: Kingdom's value proposition is multi-turn collaboration. Session continuity (via `--resume`) lets models accumulate context across 5-10+ exchanges without re-sending history. LLM Council's stateless model would break this.

### 2. Web-Based UI

**What they do**: React SPA with sidebar, tabbed views, conversation management in browser.

**Why skip**: Kingdom is CLI-first. The tmux-based UI (`kd attach`) serves the same "observe agents working" need without a separate frontend deployment.

### 3. Single API Provider (OpenRouter)

**What they do**: All models accessed via OpenRouter's unified API.

**Why skip**: Kingdom orchestrates CLI agents (Claude Code, Codex, Cursor Agent) that can read/write files and execute code. These are fundamentally different from API-only text models. Kingdom's value is in orchestrating *agentic* tools, not just text generation.

### 4. Chairman as Single Authority

**What they do**: One designated model synthesizes the final answer.

**Why skip**: In Kingdom, the Hand (human operator) is the final authority. Council members provide perspectives; Hand decides. Automatic synthesis removes human judgment from the loop.

---

## Why Not Just Use This?

LLM Council is a **text generation consensus tool**. Kingdom is a **software engineering workflow orchestrator**.

| Aspect | LLM Council | Kingdom |
|--------|-------------|---------|
| **Input** | User question | Feature requirement / ticket |
| **Output** | Synthesized text answer | Code changes, design docs, PRs |
| **State** | Stateless per-message | Multi-turn sessions with file context |
| **Agents** | Text-only API models | Agentic CLI tools (read/write/execute) |
| **Quality gate** | Peer ranking heuristic | Acceptance criteria, tests, human review |
| **Persistence** | Conversation history | Run state, sessions, tickets, git branches |

Kingdom could adopt LLM Council's deliberation pattern for specific phases (e.g., design critique), but the overall workflow model is incompatible.

---

## Concrete Recommendations

### 1. Add Anonymization Option for Synthesis

When synthesizing Council responses, optionally anonymize them:

```python
def synthesize(responses: dict[str, str], anonymize: bool = True) -> str:
    if anonymize:
        # Shuffle and label as "Response 1", "Response 2", etc.
        shuffled = list(responses.values())
        random.shuffle(shuffled)
        prompt = "Synthesize these responses:\n" + "\n".join(
            f"Response {i+1}: {r}" for i, r in enumerate(shuffled)
        )
    else:
        prompt = "Synthesize these responses:\n" + "\n".join(
            f"[{name}]: {r}" for name, r in responses.items()
        )
    return hand.synthesize_model.query(prompt)
```

### 2. Structured Deliberation Logs

Adopt LLM Council's multi-stage log structure for Hand:

```python
# .kd/runs/<feature>/logs/hand.jsonl
{
  "timestamp": "...",
  "prompt": "...",
  "responses": {
    "claude": {"text": "...", "elapsed": 2.1},
    "codex": {"text": "...", "elapsed": 1.8},
    "agent": {"text": "...", "elapsed": 2.4}
  },
  "synthesis": "...",  # Optional: if Hand auto-synthesizes
  "decision": "..."    # What the human decided to do
}
```

This enables post-hoc analysis of which models contributed most to final decisions.

### 3. Peer Critique Phase (Optional)

For high-stakes decisions (architecture, security), consider a lightweight "peer critique" step:

```
Council responds to design question
    ↓
Hand shows responses to user
    ↓
User requests critique: "kd critique"
    ↓
Each model receives all responses (anonymized) and identifies weaknesses
    ↓
Hand displays critiques
```

This is lighter than full 3-stage deliberation but captures the "models checking each other" benefit.

### 4. Aggregate Ranking for Tie-Breaking

When Council responses conflict, adopt LLM Council's aggregate ranking approach:

```python
def rank_responses(responses: dict[str, str]) -> list[str]:
    """Ask each model to rank all responses, aggregate scores."""
    rankings = {}
    for model, _ in responses.items():
        # Each model ranks all responses
        ranking = ask_model_to_rank(model, responses)
        for position, ranked_model in enumerate(ranking):
            rankings.setdefault(ranked_model, []).append(position + 1)

    # Sort by average rank
    return sorted(rankings.keys(), key=lambda m: sum(rankings[m]) / len(rankings[m]))
```

This is expensive (N² model calls) but useful when responses strongly disagree.

---

## Notes / Risks

- **API cost**: LLM Council's 3-stage pattern multiplies API calls. For Kingdom (using CLI agents), this is less of a concern since agent sessions are already expensive.

- **Parsing fragility**: LLM Council's ranking parser is brittle (relies on "FINAL RANKING:" header). Kingdom should use structured output (JSON mode) if implementing similar critique patterns.

- **No learning**: LLM Council doesn't accumulate learnings across runs. Kingdom's ticket system and `.kd/` state provide some of this, but explicit "lessons learned" storage could be valuable.

- **Vibe code heritage**: LLM Council is explicitly "99% vibe coded"—quick and functional but not production-hardened. Adopt patterns, not implementation.
