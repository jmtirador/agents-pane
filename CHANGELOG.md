# Changelog

Every version of agents-pane, newest first, in plain words.
The shape follows Keep a Changelog (https://keepachangelog.com/en/1.1.0/) and the version numbers follow Semantic Versioning.

## [Unreleased]

## [4.0.0] - 2026-10-14

Fast, and it works the way you'd expect.

### Changed
- Switching sessions is instant once you've looked at a session: each one you view keeps its own `claude attach` running in a hidden tmux session, and picking it again swaps it onto the right side in a few milliseconds instead of starting it over (about 0.05 s instead of 0.56 s, with no blank flash). Up to four sessions you looked at in the last 15 minutes stay ready this way; Claude Code stops a session's process after about an hour with nothing attached, so these no longer boot again when you come back.
- The right side always shows the card you're on. A session it can't show, like a chat in another terminal tab, gets a short note there saying where it is.
- One click on a background session's card opens it, with your keys in it (Enter still switches to a chat in another tmux window or resumes an ended one). The blank row between two cards opens the card below it, and messages pop up at the top of the list and go away after 3 seconds instead of covering the bottom cards.
- Stopping a session is now capital `S` twice and deleting is capital `X` twice, so a reply typed into the list by mistake can't stop or delete anything.
- A waiting card says how long it has waited ("waiting 4m"), shows the whole question on up to three lines, and lists its choices. A working card says what it's doing in words ("editing app.py") or "no output for 12m".
- Cards drop the folder name, the "showing" mark and the context warning; the highlighted card is the one on the right.
- The `u` screen just shows how often you've used the dashboard.

### Added
- `q` or Ctrl+C in the list closes the dashboard, and the bar says so; every session keeps running. Opened from inside another tmux session, it takes you back there.
- Leaving a session from inside Claude Code (Ctrl+C twice, `←`, `/exit` or Ctrl+Z) brings the same session back on the right and gives your keys back to the list, instead of leaving Claude's own session list there.

### Fixed
- Esc closes a dialog in about half the time (0.09 s instead of 0.16 s).

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
