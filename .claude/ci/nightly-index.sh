#!/usr/bin/env bash
# Headless nightly re-index — keeps CODEBASE_INDEX/SYMBOLS fresh without human sessions.
set -euo pipefail
claude -p "Invoke the indexer subagent to refresh .agents/state/index/. Output its summary only." \
  --allowedTools "Read,Write,Grep,Glob,Bash" \
  --output-format json
