# 3. A quiet frame around Claude Code

Status: accepted, 2026-10-08; amended the same day (see the end)

## Context

Claude Code draws its own rules, its own session name and its own context meter.
v2 added a tmux title line above each pane and a heavy pink divider, so the session name and context showed twice and the divider touched Claude's text (problem P2).
With two panes, tmux gives the whole shared divider one color, so border color can't show which side has focus.

## Decision

- `pane-border-lines single` in a quiet gray and `pane-border-status off`: no tmux titles (amended below: a plain bottom line, still no titles).
- The list draws its own first row: `agents` plus the counts.
- Focus is shown by the bottom bar (it lists the keys for the focused side) and by the list dimming while Claude has focus.

## Alternatives considered

- `pane-border-lines spaces` as a one-column gutter: cleaner, but Pepe picked direction A, which keeps one thin line.
- Titles at the bottom: they wedge a row between Claude's own status lines and the key bar.

## Consequences

- The live session's name is shown only by Claude Code itself and by the "showing" mark on its card.

## Amendment, 2026-10-08 (after Pepe saw the M2 preview)

Pepe liked the welcome box's thin rounded line ("real nice, nice and thin, should be in more places but obv not spammed") and asked for the list's header and each band to sit in a box like it, and for a line separating the key bar from the panes.

- `pane-border-status bottom` with an empty `pane-border-format`: one plain line across both sides over the key bar, still with no title on it.
  It costs the row this record's alternatives warned about, and he asked for exactly that separation, so his ask wins.
- The list draws its own boxes (thin rounded lines in the frame gray, the name in the top line like the welcome box): `agents` with the counts, then one box per band.
- Toasts get the same thin line; dialogs and inputs stay line-only.
- Not boxed, on purpose: single cards, the idle line, the find line and the Claude side, so the boxes keep meaning "a group" and don't get spammed.
