"""v3's look and words, checked on what gets drawn (problems P3, P4, P5, P7 in docs/problems.md)."""

import os

import pytest
from helpers import NOW, row

from cockpit import dialogs, model, tmuxctl, view
from cockpit.theme import PALETTES, PROJECT_COLORS

NEON = PALETTES["neon"]
ROWS = [
    row("needs-1", "needs", question="Ship it?"),
    row("asks-1", "asks", question="Which folder?"),
    row("work-1", "working", name="finch-fixes"),
    row("ours-1", "working", name="cockpit work", cwd=os.path.expanduser("~/Projects/agents-pane"), where="agents-pane"),
    row("done-1", "done", finishedAt=NOW, ctx=900_000),
    row("idle-1"), row("idle-2"),
]
# v2's jargon (P5); a test fails if any of it is drawn again
BANNED = ["^]", "ctx", "s s", "x x", "quiet", " e shows", "look", "● 2", "✓ 2", "list ⇄ live"]


def drawn(selected="work-1", dim=False, show_quiet=False, p=NEON):
    order = model.fresh_order(ROWS)
    text, sids = view.render(ROWS, order, p, 41, NOW, 0, selected=selected, live="done-1"[:8], watched=set(),
                             show_quiet=show_quiet, dim=dim)
    return text, sids


def spans_by_line(text, sids):
    """Each styled span, with the session its line belongs to and that line's text."""
    starts, at = [], 0
    lines = text.plain.split("\n")
    for line in lines:
        starts.append(at)
        at += len(line) + 1
    for span in text.spans:
        line = max(i for i, start in enumerate(starts) if start <= span.start)
        yield sids[line], str(span.style), lines[line]


def everything_he_reads():
    text, _ = drawn(show_quiet=False)
    yield text.plain
    yield drawn(show_quiet=True)[0].plain
    yield view.list_header(model.counts(ROWS), NEON, 41).plain
    yield view.find_line(NEON, 41).plain
    for key, what, _ in tmuxctl.LIST_KEYS + tmuxctl.CLAUDE_KEYS:
        yield f"{key} {what}"
    for line in dialogs.help_lines(NEON, "3.0.0"):
        yield line.plain
    for dialog in (dialogs.NewSession, dialogs.TypeInto, dialogs.Find, dialogs.Note, dialogs.ThemePicker):
        for key, what, _ in dialog.KEYS:
            yield f"{key} {what}"


@pytest.mark.parametrize("p", PALETTES.values(), ids=PALETTES.keys())
def test_the_loud_color_is_only_for_a_session_waiting_for_him(p):  # P4
    text, sids = drawn(p=p)
    for sid, style, line in spans_by_line(text, sids):
        if p.needs in style and sid is None:
            assert line.startswith("╭─ Waiting for you"), f"{p.needs} on {line!r}"  # only that band's own box title
        elif p.needs in style:
            assert sid in ("needs-1", "asks-1"), f"{p.needs} on {sid}: {style}"  # the waiting card, and an ask's "?"


@pytest.mark.parametrize("p", PALETTES.values(), ids=PALETTES.keys())
def test_keys_and_titles_never_use_the_loud_color(p):  # P4: Mission's keys were amber, its "waiting" color
    assert p.key != p.needs
    assert p.needs not in tmuxctl.key_bar(p, tmuxctl.LIST_KEYS) + tmuxctl.side_bar(p)


def test_every_box_closes_and_lines_up():  # Pepe asked for the header and each band in a thin rounded box
    text, sids = drawn()
    lines = text.plain.split("\n")
    header = view.list_header(model.counts(ROWS), NEON, 41).plain.split("\n")
    assert header[0].startswith("╭─ agents ") and header[2].startswith("╰")
    inside = False
    for line in header + lines:
        if line.startswith("╭"):
            assert not inside and line.endswith("╮")
            inside = True
        elif line.startswith("╰"):
            assert inside and line.endswith("╯")
            inside = False
        elif inside:
            assert line.startswith("│") and line.endswith("│"), line
        assert len(line) == 41 or not line.strip("│ ╭╮╰╯─"), line
    assert not inside
    titles = [line[3:].split(" ─")[0] for line in lines if line.startswith("╭")]
    assert titles == ["Waiting for you", "Working", "Done"]


def test_a_cut_off_summary_keeps_a_gap_before_the_context_warning():
    full = row("full-1", "working", detail="fixing the dim-mode header so it stops being bold", ctx=960_000, band=2)
    second = view.card(full, NEON, 41, NOW, 0, selected=False, live=False, watched=False)[1].plain
    assert "…  context 99% full " in second


def test_a_long_name_is_cut_before_it_touches_its_age():  # the boxed list once drew "…test branch39h"
    long = row("long-1", "working", name="code review of the payments test branch", band=2)
    first = view.card(long, NEON, 39, NOW, 0, selected=False, live=False, watched=False)[0].plain.rstrip()
    age = model.row_age(long, NOW)
    assert first.endswith(age) and first[: -len(age)].endswith("… ") and "…" in first, first


def test_no_project_stripe_uses_a_loud_color():  # P4
    louds = {p.needs for p in PALETTES.values()}
    assert not louds & {color for _, color in PROJECT_COLORS}


def test_bold_is_only_for_the_cursor_card_and_the_waiting_one():  # P4
    text, sids = drawn(selected="work-1")
    for sid, style, _ in spans_by_line(text, sids):
        if "bold" in style:
            assert sid in ("work-1", "needs-1"), f"bold on {sid}: {style}"


def test_nothing_is_bold_on_the_list_while_he_types_to_claude_except_the_waiting_card():  # P6
    text, sids = drawn(selected="work-1", dim=True)
    for sid, style, _ in spans_by_line(text, sids):
        if "bold" in style:
            assert sid == "needs-1"


def test_no_jargon_anywhere_he_reads():  # P5
    for words in everything_he_reads():
        for banned in BANNED:
            assert banned not in words, f"{banned!r} in {words!r}"


def test_the_key_bar_is_quiet_text_not_chips():  # P3
    for bar in (tmuxctl.key_bar(NEON, tmuxctl.LIST_KEYS), tmuxctl.side_bar(NEON)):
        assert "bg=" not in bar and "bold" not in bar


def test_the_bar_shows_only_the_way_back_on_the_claude_side():  # P3, P6
    assert [what for _, what, _ in tmuxctl.CLAUDE_KEYS] == ["back to your sessions"]
    assert len(tmuxctl.LIST_KEYS) <= 7


def test_the_theme_key_says_theme():  # P7
    assert ("t", "theme", "t") in tmuxctl.LIST_KEYS
    assert any("change the theme (now Neon)" in line.plain for line in dialogs.help_lines(NEON, "3.0.0"))


def test_the_header_counts_in_words():  # P5
    header = view.list_header(model.counts(ROWS), NEON, 41).plain
    assert "1 waiting" in header and "2 working" in header and "1 done" in header and "…" not in header


def test_all_keys_fits_a_zoomed_pane():  # 27 rows since the line over the keys; 96 columns less the box and padding
    lines = dialogs.help_lines(NEON, "3.0.0")
    assert len(lines) + 2 <= 27 and all(len(line.plain) <= 90 for line in lines)


def test_done_and_idle_take_one_line_and_sit_back():  # design B, Pepe's pick 2026-10-09
    text, sids = drawn(selected="work-1", show_quiet=True)
    lines_of = {sid: sids.count(sid) for sid in set(sids) if sid}
    assert lines_of["work-1"] == 2 and lines_of["needs-1"] == 2
    assert lines_of["done-1"] == 1 and lines_of["idle-1"] == 1
    for sid, style, _ in spans_by_line(text, sids):
        if sid in ("done-1", "idle-1", "idle-2"):
            assert " on " not in style, f"a fill on {sid}: {style}"  # only the cursor's line is filled


def test_a_one_line_row_shows_a_few_words_of_recap_or_none():  # never a lone "…" after a long name
    short = row("d1", "done", name="docs", finishedAt=NOW, away="Rewrote the setup guide for new laptops.", band=3)
    long = row("d2", "done", name="mobile app release notes draft", finishedAt=NOW, away="The notes are done.", band=3)
    for r in (short, long):
        text = view.line(r, NEON, 39, NOW, 0, selected=False, live=False, watched=False)[0].plain
        assert "  …" not in text and len(text) == 39, text
    assert "Rewrote the" in view.line(short, NEON, 39, NOW, 0, selected=False, live=False, watched=False)[0].plain
