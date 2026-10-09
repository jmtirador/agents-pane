"""Draw the session list as colored text: the header box, a box per band with its cards, the idle line.

Waiting and working sessions get two-line cards; done and idle ones get one line each (design B, 2026-10-09).

Pure: rows in, (Text, the session each line belongs to) out, so a click maps back to a card.
Direction A: lines between cards have no background, so the terminal's own gray shows; cards sit one step
lighter; bold is only for the cursor card's name and the card waiting for him; `dim` is the look while
he's typing to Claude. The boxes are thin rounded lines with their name in the top line, like the welcome
screen's box (Pepe, 2026-10-08: "real nice, nice and thin, should be in more places but obv not spammed").
"""

from rich.text import Text

from . import model
from .theme import Palette, mix


def bar(bg, left, right, width):
    """One full-width line: left parts cut with … to make room for right parts; bg None leaves the terminal's own."""
    on = f" on {bg}" if bg else ""
    line = Text(style=on.strip(), no_wrap=True, end="")
    for text, style in left:
        line.append(text, style)
    tail = Text(style=on.strip(), end="")
    for text, style in right:
        tail.append(text, style)
    line.truncate(max(0, width - tail.cell_len), overflow="ellipsis", pad=True)
    line.append_text(tail)
    return line


def attention(p: Palette, bg, frame):
    """The waiting card's text: orange, pulsing between bright and half-faded each spinner frame."""
    return p.needs if frame % 2 == 0 else mix(p.needs, bg, 0.45)


def glyph(row, p: Palette, frame, bg=None):
    """The state's mark and its color."""
    state = row["state"]
    color = {
        "needs": attention(p, bg or p.card, frame),
        "asks": p.needs,
        "failed": p.fail,
        "working": p.work if frame % 2 == 0 else mix(p.work, p.card, 0.55),  # a slow pulse: alive, not alarming
        "quiet": p.quiet,
        "done": p.done,
    }.get(state, p.text3)
    return model.GLYPH[state], color


def line(row, p: Palette, width, now, frame, *, selected, live, watched, dim=False):
    """A done or idle session on one line: stripe, mark, name, then its recap if there's room, and its age.

    No fill unless the cursor is on it, so the finished ones sit back and the space goes to what's still moving.
    """
    cursor = selected and not dim
    bg = p.sel if cursor else None
    proj = model.project_color(row["cwd"])
    if dim:
        proj = mix(proj, p.base, 0.5)
    mark, mark_color = glyph(row, p, frame, bg or p.base)
    right = [(" ", "")]
    if watched:
        right.append(("◉ ", p.work))
    if not row["jobId"] and row["alive"]:
        right.append(("↗ ", p.text3))
    if live:
        right.append(("showing ▸ ", p.key))
    right.append((model.row_age(row, now) + " ", p.text3))
    room = width - 4 - len(row["name"]) - sum(len(text) for text, _ in right) - 2
    said = model.second_line(row)
    said = "  " + (said if len(said) <= room else said[: room - 1] + "…") if said and room >= 8 else ""  # a few words, or none
    left = [("▌", f"{proj} on {bg}" if bg else proj), (" ", ""), (mark + " ", mark_color),
            (row["name"], f"bold {p.text}" if cursor else p.text2 if dim else p.text), (said, p.text3)]
    return [bar(bg, left, right, width)]


def card(row, p: Palette, width, now, frame, *, selected, live, watched, dim=False):
    waiting = row["state"] == "needs"  # waiting for him right now: its text pulses orange, even while the list is dimmed
    cursor = selected and not dim
    bg = p.sel if cursor else p.card
    ink = attention(p, bg, frame) if waiting else p.text2 if dim else p.text
    soft = ink if waiting else p.text3 if dim or row["band"] == 4 else p.text2
    proj = model.project_color(row["cwd"])
    if dim:
        proj = mix(proj, p.base, 0.5)
    stripe = ("▌", f"{proj} on {bg}")
    mark, mark_color = glyph(row, p, frame, bg)
    flags = []
    if watched:
        flags.append(("◉ ", p.work))
    if not row["jobId"] and row["alive"]:
        flags.append(("↗ ", soft))  # a chat in some other window: it can't be shown here
    age = model.row_age(row, now)
    room = width - 4 - len(row["name"]) - sum(len(text) for text, _ in flags) - len(age) - 2
    where = "  " + row["where"] if row["where"] and len(row["where"]) + 2 <= room else ""  # whole or not at all, never ".cl…"
    first = bar(bg, [stripe, (" ", ""), (mark + " ", mark_color), (row["name"], f"bold {ink}" if cursor or waiting else ink),
                     (where, mix(proj, bg, 0.25))],
                [(" ", ""), *flags, (age + " ", soft)], width)  # a gap, so a long name is cut ("…") before it touches the age
    right = []
    if live:
        right.append(("showing ▸", p.key))
    elif model.ctx_pct(row) >= 80:
        right.append((f"context {model.ctx_pct(row)}% full", p.quiet))
    if right:  # a gap, so a cut-off summary doesn't run into it ("hea…context")
        right.insert(0, ("  ", ""))
    second = bar(bg, [stripe, ("   ", ""), (model.second_line(row) or " ", p.fail if row["state"] == "failed" else soft)],
                 [*right, (" ", "")], width)
    return [first, second]


def box_top(title, style, p: Palette, width):
    """╭─ title ───╮: a box's first line, its name in its own color."""
    rule = max(0, width - len(title) - 5)
    return Text.assemble(("╭─ ", p.line), (title, style), (" " + "─" * rule + "╮", p.line), no_wrap=True, end="")


def box_side(line, p: Palette):
    return Text.assemble(("│", p.line), line, ("│", p.line), no_wrap=True, end="")


def box_bottom(p: Palette, width):
    return Text("╰" + "─" * max(0, width - 2) + "╯", style=p.line, no_wrap=True, end="")


def list_header(counts, p: Palette, width, dim=False):
    """The list's own header (no tmux title line, decision 0003): a small box named "agents", saying what's going on in words."""
    parts = [(" ", "")]
    if counts["needs"]:  # the bar on the Claude side says "waiting for you"
        parts += [(f"{counts['needs']} waiting", f"bold {p.needs}"), ("   ", "")]
    if counts["working"]:
        parts += [(f"{counts['working']} working", p.work), ("   ", "")]
    if counts["done"]:
        parts += [(f"{counts['done']} done", p.done)]
    if len(parts) == 1:
        parts += [("nothing running", p.text3)]
    return Text("\n", end="").join([box_top("agents", p.text3 if dim else f"bold {p.text}", p, width),
                                     box_side(bar(None, parts, [], width - 2), p), box_bottom(p, width)])


def find_line(p: Palette, width):
    return bar(None, [(" /", p.key), (" find an old session", p.text3)], [], width)


def render(rows, order, p: Palette, width, now, frame, *, selected, live, watched, show_quiet, warning="", dim=False):
    shown, quiet = model.visible(rows, order, show_quiet, selected)
    lines, sids = [], []

    def add(line, sid=None):
        lines.append(line)
        sids.append(sid)

    if warning:
        add(bar(None, [(" ⚠ " + warning, p.fail)], [], width))
    if not shown and not quiet:
        add(bar(None, [], [], width))
        add(bar(None, [(" No sessions yet.", p.text)], [], width))
        add(bar(None, [(" n", p.key), (" starts one, ", p.text3), ("/", p.key), (" finds an old one.", p.text3)], [], width))
    colors = {1: p.needs, 2: p.work, 3: p.done, 4: p.text3}
    inner = width - 2
    last_band = None
    for row in shown:
        row = {**row, "band": model.band(row)}
        brief = row["band"] >= 3  # done and idle: one line each, no gaps (design B, his pick 2026-10-09)
        if row["band"] != last_band:  # each band is a box named after it
            if last_band is not None:
                add(box_bottom(p, width))
            add(box_top(model.BAND_LABEL[row["band"]], colors[row["band"]] if not dim else p.text3, p, width))
            last_band = row["band"]
        elif not brief:
            add(box_side(bar(None, [], [], inner), p))  # a blank row between two-line cards
        draw = line if brief else card
        for drawn in draw(row, p, inner, now, frame, selected=row["sid"] == selected, live=bool(live) and row["jobId"] == live,
                          watched=row["sid"] in watched, dim=dim):
            add(box_side(drawn, p), row["sid"])
    if last_band is not None:
        add(box_bottom(p, width))
    if quiet:
        hidden = f" {len(quiet)} idle {'session' if len(quiet) == 1 else 'sessions'} hidden"
        add(bar(None, [(hidden, p.text3)], [("e", p.key), (" to show ", p.text3)], width))
    elif show_quiet:
        add(bar(None, [], [("e", p.key), (" to hide idle ", p.text3)], width))
    return Text("\n", end="").join(lines), sids
