#!/bin/sh
# Generic tmux interactive driver for EDPA onboarding tests.
#
# Drive ANY interactive terminal program — install.sh, or a nested `claude`
# session for the full /edpa:setup E2E — by sending keystrokes and capturing
# the pane. Same technique an agent uses to test a TUI: a detached session you
# poke at with send-keys and read back with capture-pane.
#
# Drive install.sh through its overwrite prompt (offline abort):
#   ./tmux_drive.sh new  onb  /tmp/sb && mkdir -p /tmp/sb/.edpa/engine
#   ./tmux_drive.sh run  onb  'sh /Users/jurby/projects/edpa/install.sh'
#   ./tmux_drive.sh cap  onb                 # read what's on screen
#   ./tmux_drive.sh send onb  'n'            # answer the prompt
#   ./tmux_drive.sh cap  onb
#   ./tmux_drive.sh kill onb
#
# Full /edpa:setup E2E (heavier): `run` a `claude` session in the pane, then
# `send` the slash command and `cap` the model's actions between turns.
set -e

cmd="${1:?usage: tmux_drive.sh new|run|send|keys|cap|kill <session> [arg]}"
ses="${2:?session name required}"
arg="$3"

case "$cmd" in
  new)  tmux new-session -d -s "$ses" -x 220 -y 50 ${arg:+-c "$arg"} ;;
  run)  tmux send-keys -t "$ses" "$arg" Enter ;;   # run a command line
  send) tmux send-keys -t "$ses" "$arg" Enter ;;   # text + Enter (prompt answer)
  keys) tmux send-keys -t "$ses" "$arg" ;;         # raw keys, no Enter (C-c, Up, …)
  cap)  tmux capture-pane -t "$ses" -p ;;          # print current pane
  kill) tmux kill-session -t "$ses" ;;
  *)    echo "unknown subcommand: $cmd" >&2; exit 2 ;;
esac
