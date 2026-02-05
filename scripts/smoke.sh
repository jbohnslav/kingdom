#!/usr/bin/env bash
set -euo pipefail

uv sync >/dev/null

feature="smoke-$(date +%s)"
uv run kd start "$feature"
uv run kd design
uv run kd breakdown
uv run kd status
uv run kd ticket list
