# 2. The terminal paints the background

Status: accepted, 2026-10-08

## Context

v2 painted near-black #0b0e14 over every pane while Ghostty pads the window with its own background, #282c34, so the cockpit showed a black box inside a gray ring (problem P1).
Pepe asked for "a darker gray instead of black".

## Decision

The cockpit paints no background of its own.
tmux uses `bg=default` for `window-style`, `window-active-style` and `status-style`, and the Textual apps run with `ansi_color=True` and `background: ansi_default` on their screens.
Each look keeps a hex copy of the terminal gray (#282c34) only as the base for blending card and dimming colors.

## Alternatives considered

- Hardcode #282c34 everywhere: matches today, breaks the day he changes his Ghostty theme.
- A full Textual ANSI theme: the dialog backdrop blanks the list, because Textual can't blend an ANSI color (checked by the tech audit).

## Consequences

- Cards, the cursor card and dialogs still use hex colors one step lighter than #282c34, so they look right on his Ghostty and slightly off on a very different theme.
- The themes change accents, never the background.
