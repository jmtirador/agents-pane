# Changelog

Every version of agents-pane, newest first, in plain words.
The shape follows Keep a Changelog (https://keepachangelog.com/en/1.1.0/) and the version numbers follow Semantic Versioning.

## [Unreleased]

## [3.1.2] - 2026-10-09

### Fixed
- If the list ever crashed, its pane closed instead of offering to start it again, because tmux runs the restart loop with zsh and zsh read the `=agents:` target as a command lookup (since 3.0.0). The targets are quoted now, and a test crashes the list under zsh.

## [3.1.1] - 2026-10-09

### Fixed
- The 3.1.0 scroll fix went too far: the card you're on could slide off screen when it moved to Done or when idle sessions appeared, `g` and `G` did nothing after you scrolled away, and leaving a session jumped the list to the top. Now a card you can see stays in view when cards move, one you scrolled away from stays away, and moving the cursor always brings it into view.
- Clicking the last box's border no longer shows the idle sessions when there's no idle line.

## [3.1.0] - 2026-10-09

### Changed
- A session waiting for you no longer turns its whole card pink: its name and question pulse orange instead, in every theme, and the count in the header and in your other tmux sessions is orange text too.
- Done and idle sessions take one line each, with a few words of their recap beside the name, so the list fits about twice as many sessions; waiting and working sessions keep their two-line cards.
- The theme menu's dots show each theme's own color, working, done and keys.

### Fixed
- Scrolling the list jumped back to the top a second later, worst after showing the idle sessions; a scroll now stays where you leave it.

## [3.0.0] - 2026-10-08

### Changed
- The cockpit now uses your terminal's own gray everywhere instead of painting a near-black box, and one thin gray line divides the list from Claude Code; the title lines over each side are gone.
- The bottom bar is quiet text instead of bold chips, and it shows only the keys for the side you're on: the list's keys in the list, and just `ctrl+] back to your sessions` while you type to Claude, plus "N waiting for you" when a session waits.
- The list dims while Claude has your keys, and the card shown on the right says "showing".
- Each theme's loud color now means only "a session is waiting for you"; keys, project stripes and the frame never use it.
- Labels are in plain words: "Waiting for you", "Working", "Done", "Idle", "context 84% full", "4 idle sessions hidden, e to show", and `?` shows every key grouped as Moving around, Doing things and Managing.
- `t` opens a theme menu with each theme's colors; moving through it shows each theme live, Enter keeps one, and Esc puts back the one you had. `?` says which one is on.
- Dialogs, toasts and find results are calmer: less bold, toasts that don't wrap, no black strips behind a dialog.
- The list's header and each group (Waiting for you, Working, Done) sit in thin rounded boxes named in their top line, like the welcome box, and a thin line separates the keys at the bottom from the two sides.

### Fixed
- A long session name could run into its age.

## [2.0.1] - 2026-10-08

### Fixed
- A card whose state changed while the cursor was on it could make a band label (like DONE) show up twice.
- Pressing Tab twice, or Enter then Tab, could bounce you back to the list; Tab now always goes to the Claude side.
- Ctrl+] while a dialog was open squeezed the dialog into the narrow list; it now waits until the dialog closes.
- In Find, pressing Enter right after typing could open the result for what you typed a moment earlier; it now opens a result for what's in the box.

### Added
- A safety net for the v3 work: tests that run the real launcher on a private tmux server with a fake `claude`, app tests with tmux faked, one `make check` command, git hooks that run it before every commit and check commit messages, and this changelog.
- `python -m cockpit --version`.

## [2.0.0] - 2026-10-07

The cockpit: a full-screen tmux app instead of a pane inside one chat.

### Added
- Every Claude Code session on the left as a colored card, grouped by who needs you, what's working and what's done.
- The picked session running live on the right as the real Claude Code, switched by a process that never re-creates the pane.
- New session, reply, rename, find old sessions, watch with a Mac notification, stop, remove, three looks, and a usage check for the two-week rule.
- `yolo` opens it; `yolo "prompt"` starts a session and shows it live.

## [1.0.0] - 2026-10-06

A pane docked inside one Claude Code chat, built as a Claude Code mod. Retired by 2.0.0.
