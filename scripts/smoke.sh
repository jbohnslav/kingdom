#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
smoke_root=$(mktemp -d "${TMPDIR:-/tmp}/kingdom-smoke.XXXXXX")
smoke_uv_cache=${UV_CACHE_DIR:-$(uv cache dir)}
trap 'rm -rf "$smoke_root"' EXIT

uv sync --project "$repo_root" >/dev/null

cd "$smoke_root"
git init -q
git config user.email "smoke@kingdom.invalid"
git config user.name "Kingdom Smoke"
printf '# Smoke repository\n' > README.md
git add README.md
git commit -qm "Initialize smoke repository"

kd=(
  env -u HOME
  KD_SKILL_HOME="$smoke_root/agent-home"
  KD_CONTEXT="kingdom-smoke"
  UV_CACHE_DIR="$smoke_uv_cache"
  uv run --project "$repo_root" kd
)

"${kd[@]}" --help >/dev/null
"${kd[@]}" start smoke

epic_output=$("${kd[@]}" tk create --type epic "Smoke ticket workflow")
epic_id=${epic_output#Created }
epic_id=${epic_id%%:*}
epic_id=${epic_id%% *}
"${kd[@]}" tk find "$epic_id" >/dev/null

direct_output=$("${kd[@]}" tk create --parent "$epic_id" "Direct smoke ticket")
direct_id=${direct_output#Created }
direct_id=${direct_id%%:*}
direct_id=${direct_id%% *}
"${kd[@]}" tk start "$direct_id"
"${kd[@]}" tk log "$direct_id" "Smoke verification completed"
"${kd[@]}" tk close "$direct_id"

backlog_output=$("${kd[@]}" tk create --backlog "Pulled smoke ticket")
backlog_id=${backlog_output#Created }
backlog_id=${backlog_id%%:*}
backlog_id=${backlog_id%% *}
"${kd[@]}" tk pull "$backlog_id"
"${kd[@]}" tk start "$backlog_id"
"${kd[@]}" tk log "$backlog_id" "Backlog pull and start verified"
"${kd[@]}" tk close "$backlog_id"

hierarchy_output=$("${kd[@]}" tk list --parent "$epic_id" --closed)
if [[ "$hierarchy_output" != *"$direct_id"* ]]; then
  printf 'Epic hierarchy did not include child %s\n' "$direct_id" >&2
  exit 1
fi
printf '%s\n' "$hierarchy_output"
"${kd[@]}" status
if "${kd[@]}" status --check >/dev/null 2>&1; then
  printf 'Readiness check unexpectedly passed with open epic %s\n' "$epic_id" >&2
  exit 1
fi
"${kd[@]}" tk close "$epic_id"
"${kd[@]}" status --check

printf 'Smoke workflow passed in %s\n' "$smoke_root"
