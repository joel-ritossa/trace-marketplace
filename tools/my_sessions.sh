#!/usr/bin/env bash
# Convert your local coding-agent sessions (Codex, Claude Code, Cursor) from
# the past 24 hours into uploadable OTLP JSON under devdata/agent-sessions/.
# Works from any cwd; all converter flags pass through, e.g.:
#   tools/my_sessions.sh --source cursor --hours 48 --count 20
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 tools/agent_sessions_to_otlp.py "$@"
