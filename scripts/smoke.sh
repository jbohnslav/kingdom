#!/usr/bin/env bash
set -euo pipefail

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found; skipping tmux-dependent smoke checks."
  exit 0
fi

if ! command -v tk >/dev/null 2>&1; then
  echo "tk not found; skipping ticket-dependent smoke checks."
  exit 0
fi

uv sync >/dev/null

feature="smoke-$(date +%s)"
uv run kd start "$feature"
uv run kd plan
uv run kd status
