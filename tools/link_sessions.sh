#!/usr/bin/env bash
# Maintain git-ignored symlinks to the session logs your coding agents
# already write, so trace-sync can upload them raw (8_session-ingestion.md —
# the server converts; there is no client-side conversion step):
#
#   tools/link_sessions.sh
#   TRACE_API_KEY=tmk_… trace-sync sync devdata/sessions-src --since-hours 24
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p devdata/sessions-src
for entry in "codex:$HOME/.codex/sessions" \
             "claude:$HOME/.claude/projects" \
             "cursor:$HOME/.cursor/projects"; do
  name="${entry%%:*}" target="${entry#*:}"
  link="devdata/sessions-src/$name"
  # Refresh symlinks only; respect a link the user replaced with a real dir.
  if [ -d "$target" ] && { [ ! -e "$link" ] || [ -L "$link" ]; }; then
    ln -sfn "$target" "$link"
  fi
  [ -e "$link" ] && echo "$link -> $(readlink "$link" 2>/dev/null || echo '(local dir)')"
done
