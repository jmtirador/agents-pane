# 4. How the cockpit is tested

Status: accepted, 2026-10-08

## Context

v2 was checked by hand in tmux and on screenshots, and the screenshots could be stale (Ghostty stops redrawing a covered window).
UI regressions and tmux bugs were found late, by reviewers or by Pepe.

## Decision

- Unit tests for the pure parts: ordering, drawing, sessions, state.
- Picture tests with pytest-textual-snapshot for every screen at his size, with tmux, the state file and the session reader faked.
- tmux tests on a private server (`tmux -L`) with a fake `claude`, `osascript` and session files, which run the real launcher and check layout, the key bar, bindings and switching. They never touch his tmux server.
- `make check` runs lint, unit and picture tests before every commit; `make check-all` adds the tmux tests before every release tag.
- A picture test is updated only after its new picture was looked at.
- Picture tests start once Pepe approves the new look (after M2), so they lock in the look he wants instead of v2's (devil's advocate, 2026-10-08).

## Consequences

- Dev-only dependencies (pytest, pytest-textual-snapshot, ruff) live in `requirements-dev.txt`.
