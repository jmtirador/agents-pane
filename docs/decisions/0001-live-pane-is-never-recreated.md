# 1. The live pane is never re-created

Status: accepted, 2026-10-07 (recorded 2026-10-08)

## Context

v2 first switched sessions with `tmux respawn-pane -k`.
In testing, one respawn failed ("fork failed: Device not configured") and the next respawn of the same pane made tmux 3.7c segfault in `input_free`, which closed every tmux session on Pepe's machine.

## Decision

The right pane runs one long-running process, `cockpit/live.py`, for its whole life.
It runs `claude attach <id>` or the welcome screen as a child and swaps children when the list sets the pane option `@ap_want` and sends it SIGUSR1.
Nothing in the cockpit calls `respawn-pane`.

## Alternatives considered

- Keep `respawn-pane` and retry carefully: the crash comes from the retry itself.
- One hidden tmux window per session, swapped in with `swap-pane`: instant switches, but one `claude attach` process per session ever viewed.

## Consequences

- live.py must never exit, so every error inside it is caught and the welcome screen comes back.
- The launcher rebuilds the whole cockpit if a pane is ever missing, because a pane can't be healed in place.
