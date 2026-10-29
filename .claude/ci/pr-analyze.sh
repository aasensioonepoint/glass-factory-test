#!/usr/bin/env bash
# Headless PR analysis — run the analyzer agent non-interactively on a diff.
# Usage: ./pr-analyze.sh "origin/main...HEAD"
set -euo pipefail
RANGE="${1:-origin/main...HEAD}"
FILES=$(git diff --name-only "$RANGE" | head -50)
claude -p "Use the analyzer subagent. Review these changed files for bugs, risky patterns, and index staleness. Files:
$FILES
Return the analyzer's compressed summary only." \
  --allowedTools "Read,Grep,Glob,Bash(git *)" \
  --output-format json
