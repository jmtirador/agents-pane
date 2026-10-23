# 7. The right side peeks at sessions it can't attach

Status: accepted, 2026-10-22

## Context

On 2026-10-22, 17 of Pepe's 20 sessions weren't running: Claude Code stops a finished session's process after about an hour with nothing attached.
v4 attached only running sessions (an attach starts a stopped one), so for most cards the right side showed the logo and a one-line note.
Claude Code's agent view peeks at any row, and Agent of Empires and Agent Deck show something for every session too (the v4.1 UX adversary, docs/problems.md G1).

## Decision

- For a card it can't attach, the list writes a peek (name, state and age, folder, last prompt, recap, question and choices, what it's doing, where it is, the keys that work) to `~/.claude/agents-pane/peek-<session>.json` and swaps the welcome viewer onto the right side.
- The welcome viewer stats that file 20 times a second and redraws only on a change; it reads the session's last reply itself from the transcript's last 256 KB and renders it as Markdown, cut to fit.
- The last prompt comes from the list (Claude's `last-prompt` record is always in the transcript's last 64 KB; the typed prompt itself sits a median 240 KB from the end on his data).
- A peek has no input: Enter and `r` go to the list, which acts on the same card; any key gives the keys back.
- Showing a running session writes `{"blank": true}`, so the hidden peek can't come back showing the wrong session; `{}` is the welcome screen, shown only when there's nothing to peek at.

## Alternatives considered

- Signal the viewer (SIGUSR1) after writing a tmux option: the design critic showed a signal that lands before the viewer installs its handler, or after Textual exits, ends the process and leaves the list alone in the window.
- Attach anyway: boots a process per card he passes (144 MB each) and un-stops sessions he stopped.
- Read the last prompt from the transcript's tail: blank in 137 of 222 of his transcripts.

## Consequences

- The welcome viewer wakes 20 times a second for a stat (measured cheaper than the 0.5 s tmux poll it replaces).
- Two cockpits (the real one and a preview) keep separate peek files, like their state files.
