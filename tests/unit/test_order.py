"""B1: the card under the cursor keeps its place, but never outside its own band."""

from helpers import NOW, row

from cockpit import model, view
from cockpit.theme import PALETTES


def bands(rows, order):
    by_sid = {r["sid"]: r for r in rows}
    return [model.band(by_sid[s]) for s in order]


def test_a_card_that_changes_state_stays_inside_its_new_band():
    # the cursor was on "a" at the top while it worked; now it's done, and another session is still working
    rows = [row("a", "done", finishedAt=NOW), row("w", "working", startedAt=NOW - 1000), row("b", "done", finishedAt=NOW - 5000)]
    order = model.stable_order(rows, ["a", "w", "b"], "a")
    assert bands(rows, order) == sorted(bands(rows, order))


def test_inside_its_band_the_card_keeps_its_old_place():
    rows = [row("x", "done", finishedAt=NOW), row("y", "done", finishedAt=NOW - 1000), row("z", "done", finishedAt=NOW - 2000)]
    # fresh order is x, y, z (newest finish first); the cursor was on z at the top
    assert model.stable_order(rows, ["z", "x", "y"], "z") == ["z", "x", "y"]


def band_titles(rows, order):
    text, _ = view.render(rows, order, PALETTES["neon"], 41, NOW, 0, selected="a", live=None, watched=set(), show_quiet=False)
    return [line[3:].split(" ─")[0] for line in text.plain.split("\n") if line.startswith("╭─ ")]


def test_each_band_box_is_drawn_once():
    rows = [row("a", "done", finishedAt=NOW), row("w", "working"), row("b", "done", finishedAt=NOW - 5000)]
    assert band_titles(rows, ["a", "w", "b"]) == ["Done", "Working", "Done"]  # the bug's order: the check can see it
    assert band_titles(rows, model.stable_order(rows, ["a", "w", "b"], "a")) == ["Working", "Done"]
