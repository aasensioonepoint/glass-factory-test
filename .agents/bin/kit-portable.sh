# shellcheck shell=bash
# Portable shims for GNU coreutils commands a vanilla macOS / BSD box lacks.
# SOURCE this (never exec) near the top of any kit script that calls `timeout`,
# so the identical call works on Linux, Windows (Git-Bash) AND a macOS without
# Homebrew coreutils installed.
#
# `timeout`:
#   - Linux / a macOS with coreutils on PATH -> the real `timeout` is used, this
#     block is inert.
#   - a macOS with only `gtimeout` (Homebrew keg-only) -> thin alias.
#   - a truly vanilla macOS -> a bash-native fallback: run the command in the
#     background and SIGTERM it after DURATION.
# It accepts the forms this repo actually uses — `timeout N cmd`, `timeout Ns cmd`,
# `timeout --kill-after=N Ns cmd` — dropping GNU-only leading options it cannot
# emulate, and returns the command's OWN status. GNU's 124-on-expiry is NOT
# emulated: no kit call site branches on it (the sites that need the real thing,
# sca-scan.sh / emit-event.sh, probe for GNU coreutils themselves before calling).
if ! command -v timeout >/dev/null 2>&1; then
  if command -v gtimeout >/dev/null 2>&1; then
    timeout() { gtimeout "$@"; }
  else
    timeout() {
      while [ "${1#-}" != "$1" ]; do shift; done   # drop GNU-only leading options
      local _dur="${1%s}"; shift                    # 60s -> 60, 5 -> 5
      "$@" &
      local _pid=$!
      ( sleep "$_dur" 2>/dev/null; kill -TERM "$_pid" 2>/dev/null ) &
      local _watch=$!
      wait "$_pid" 2>/dev/null; local _rc=$?
      kill "$_watch" 2>/dev/null; wait "$_watch" 2>/dev/null
      return "$_rc"
    }
  fi
fi
