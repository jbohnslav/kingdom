#!/usr/bin/env bash
# Kingdom worktree init — runs after "kd peasant start" creates a worktree.
# The worktree path is passed as $1.
echo "⚔️  Preparing the realm at $1"
cd "$1" && uv sync && pre-commit install
