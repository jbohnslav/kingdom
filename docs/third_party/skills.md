# Analysis: Anthropic Agent Skills

## Overview

The **skills** repository is Anthropic's official implementation of the Agent Skills system—a framework for extending Claude's capabilities with specialized, reusable knowledge packages. Skills are folders containing instructions (SKILL.md), scripts, references, and assets that Claude loads dynamically to improve performance on specific tasks.

**Core purpose**: Transform Claude from a general-purpose model into a specialized agent equipped with procedural knowledge, domain expertise, and tool integrations.

**What skills solve**: The "context window problem." Instead of stuffing instructions into every prompt, skills use progressive disclosure—metadata always in context (~100 words), skill body loaded on trigger (<5k words), bundled resources loaded as needed.

## Core Architecture

### Skill Structure

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/       - Executable code (Python/Bash/JS)
    ├── references/    - Documentation loaded on demand
    └── assets/        - Templates, fonts, images for output
```

### Progressive Disclosure (Key Pattern)

Three-level loading system:

1. **Metadata** (~100 words) - Always in context (name + description determines triggering)
2. **SKILL.md body** (<5k words) - Loaded when skill triggers
3. **Bundled resources** - Loaded as needed by Claude (scripts can execute without loading)

### Degrees of Freedom

Skills match specificity to task fragility:

- **High freedom** (text instructions): Multiple valid approaches, context-dependent
- **Medium freedom** (pseudocode/scripts with params): Preferred patterns with configuration
- **Low freedom** (specific scripts): Fragile operations requiring precise sequences

### Notable Skills

| Skill | Pattern |
|-------|---------|
| `pdf` | Scripts + references for deterministic file operations |
| `doc-coauthoring` | Multi-stage workflow (context → refinement → reader testing) |
| `skill-creator` | Meta-skill with init/package scripts |
| `mcp-builder` | 4-phase workflow guide with variant-specific references |
| `algorithmic-art` | Philosophy-first creative workflow |

## Patterns Worth Adopting

### 1. Progressive Disclosure for Design/Breakdown Prompts

**What they do well**: Keep prompts lean by only loading information when needed.

**Kingdom opportunity**: The design.md and breakdown.md prompts could benefit from this pattern. Currently, Kingdom embeds full design text and breakdown text in every council prompt. Instead:

```python
# Instead of embedding full text, reference it
"Current design: See .kd/runs/{feature}/design.md (read if needed for context)"
```

This becomes more important as designs and breakdowns grow large.

### 2. Degrees of Freedom for Ticket Templates

**What they do well**: Match instruction specificity to task fragility.

**Kingdom opportunity**: Ticket format in breakdown.md is currently underspecified. Skills show that fragile formats benefit from explicit scripts:

```python
# scripts/create_ticket.py
# Deterministic ticket creation from breakdown.md → tk commands
```

This would reduce parsing errors and ensure consistent ticket structure.

### 3. SKILL.md Structure for Hand System Prompts

**What they do well**: Clear separation between triggering conditions (frontmatter description) and operational instructions (body).

**Kingdom opportunity**: The Hand's role switching (`/design`, `/breakdown`, synthesis) could use skill-like structure:

```markdown
---
mode: design
triggers: /design, editing design.md
---

# Design Mode Instructions
[operational instructions for design iteration]
```

### 4. Reference File Organization

**What they do well**: Domain-specific files that load only when relevant (finance.md, sales.md for BigQuery; aws.md, gcp.md for cloud deploy).

**Kingdom opportunity**: For larger projects, breakdown could reference domain-specific guidance:

```
.kd/runs/feature/
├── breakdown.md
└── references/
    ├── backend.md    # Backend implementation patterns
    ├── frontend.md   # Frontend patterns
    └── testing.md    # Testing strategy
```

## Patterns to Skip

### 1. Triggering via Description Matching

**What they do**: Skills trigger when Claude's internal matching determines the description fits the user's request.

**Why skip for Kingdom**: Kingdom has explicit phase management (`/design`, `/breakdown`, `peasant`). Implicit triggering would interfere with the deliberate workflow phases. Kingdom's value is in structured progression, not ad-hoc skill activation.

### 2. Single-Agent Model

**What they do**: Skills assume a single Claude instance executing instructions.

**Why skip for Kingdom**: Kingdom's Council pattern (claude + codex + agent in parallel, then Hand synthesis) is architecturally incompatible with the single-agent skill model. Skills can't orchestrate multiple models.

### 3. Context Window as Primary Constraint

**What they do**: Skills obsess over token economy because they share context with everything else.

**Why skip for Kingdom**: Kingdom uses external state (design.md, breakdown.md, state.json, tickets). The context window is ephemeral; the artifacts persist. Kingdom can afford more verbose prompts because state lives outside the conversation.

### 4. .skill Packaging

**What they do**: Package skills into distributable .skill files (zip archives).

**Why skip for Kingdom**: Kingdom's workflows are project-specific (feature branches, ticket dependencies, peasant worktrees). There's no portable "Kingdom skill" that makes sense across projects. The orchestration is the product, not the instructions.

## Can/Should Kingdom Components Be Claude Skills?

**The concrete question**: Can or should we re-implement key components of Kingdom (council, ticket management, etc.) as Claude skills?

### What Could Be Skills

| Component | Skill Viability | Notes |
|-----------|----------------|-------|
| Design iteration | Medium | The doc-coauthoring skill shows this pattern works. But Kingdom's Council synthesis adds value over single-agent iteration. |
| Breakdown structure | High | The breakdown.md format and ticket parsing could be a skill that guides Claude through ticket breakdown. |
| Ticket creation | High | A skill could guide `tk` command generation from breakdown.md. |
| Design → Breakdown transition | Medium | Could guide the "when is design done?" question. |

### What Cannot Be Skills

| Component | Why Not |
|-----------|---------|
| Council (multi-model orchestration) | Skills run in a single Claude instance. Council requires running claude + codex + agent in parallel—an external orchestration concern. |
| Hand synthesis | The Hand synthesizes across multiple model responses. This is orchestration, not procedural knowledge. |
| State management | .kd/ directory, session persistence, feature branches—external system concerns. |
| Peasant coordination | Spawning worktrees, managing parallel workers—infrastructure, not instructions. |
| Phase transitions | Moving between design → breakdown → dev requires orchestrator logic. |

### The Insight

Skills are **procedural knowledge for a single agent**. Kingdom is **orchestration across multiple agents and phases**.

The doc-coauthoring skill is instructive: it achieves sophisticated workflow (context gathering → refinement → reader testing) within a single Claude conversation. But it can only use sub-agents for reader testing—it can't run claude, codex, and agent in parallel for synthesis.

**Recommendation**: Kingdom could use skill-like patterns internally (progressive disclosure, degrees of freedom, reference organization) without becoming a skill itself. The orchestration layer (Council, Hand, Peasant coordination) must remain external Python code.

### Hybrid Approach

One possible architecture:

```
Kingdom (Python orchestrator)
├── Council (runs multiple models in parallel)
│   ├── claude  ← could use skills for domain knowledge
│   ├── codex   ← could use skills for domain knowledge
│   └── agent   ← could use skills for domain knowledge
├── Hand (synthesizes council responses)
│   └── Could have skill-like mode instructions
└── Peasant (executes tickets)
    └── Could use skills for implementation patterns
```

The orchestration stays in Python. The instructions each agent receives could be skill-like (progressive disclosure, reference files, scripts for deterministic operations).

## Why Not Just Use Skills?

Skills solve: "How do I give Claude specialized knowledge efficiently?"

Kingdom solves: "How do I coordinate multiple AI models through a structured workflow to ship features?"

These are complementary, not competing. A skill can't:

- Run three models in parallel and synthesize their responses
- Manage feature branches and worktrees
- Track tickets with dependencies across phases
- Persist state across sessions
- Coordinate multiple "Peasant" workers

Skills are a fantastic pattern for the instructions Kingdom sends to its agents. Skills are not a replacement for Kingdom's orchestration layer.

## Concrete Recommendations

### Adopt Now

1. **Progressive disclosure for prompts**: Move detailed instructions to reference files. Keep council prompts lean; let agents read references as needed.

2. **Scripts for deterministic operations**: Create `scripts/parse_breakdown.py` and `scripts/create_tickets.py` for fragile parsing/generation operations.

3. **Skill-like mode documentation**: Structure Hand mode instructions with clear triggers and operational instructions in separate files.

### Consider Later

4. **Breakdown-as-skill**: The breakdown workflow (design → tickets) could be packaged as a skill that Claude Code users could install. This would let people use Kingdom's breakdown discipline without the full orchestration.

5. **Domain reference files**: For complex projects, support `.kd/references/` directories that agents can read on demand.

### Don't Do

6. **Replace Council with skills**: The multi-model synthesis is Kingdom's core value proposition. Skills can't do this.

7. **Package Kingdom as a skill**: Kingdom is an orchestrator, not procedural knowledge.

## Key Takeaways

1. **Skills = procedural knowledge, Kingdom = orchestration**. Complementary, not competing.

2. **Progressive disclosure is valuable** and Kingdom should adopt it for prompts.

3. **Degrees of freedom** is a useful mental model for deciding when to use scripts vs. instructions.

4. **Doc-coauthoring shows what's possible** in a single-agent workflow—but Kingdom's multi-agent Council pattern goes beyond what skills can express.

5. **The hybrid approach is best**: Use skill-like patterns for instructions, keep orchestration in Python.
