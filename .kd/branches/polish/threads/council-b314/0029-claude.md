---
from: claude
to: king
timestamp: 2026-02-17T11:20:15Z
---

Here's how I'd describe it:

**One sentence:**
A CLI workflow engine that uses multi-model AI council discussions to design, break down, and execute software projects through a structured ticket system.

**Long version:**
Kingdom (`kd`) is a development workflow tool that brings structure and multi-perspective AI reasoning to software projects. You start a feature branch, describe what you want to build, and `kd` orchestrates the process: it runs council sessions where multiple AI models (Claude, GPT, Gemini, etc.) debate your design decisions, breaks work into trackable tickets, and can dispatch "peasant" worker agents to implement tickets in parallel via git worktrees. The whole workflow — branches, tickets, council threads, archives — lives as plain files in a `.kd/` directory tracked in git, so your project's design history travels with the code. It's opinionated about process (design before code, get multiple perspectives, track everything) but lightweight in implementation — a Python CLI that wraps your existing git workflow rather than replacing it.

The medieval metaphor isn't just flavor — it maps to real roles: you're the King making decisions, the council advises, peasants execute. The tool codifies the pattern of "think, discuss, plan, then build" that experienced developers do naturally, but with AI filling the advisory and execution roles.
