"""The cockpit's rules (order, colors, ages) and its drawing, without tmux or a live session."""

import os
import unittest

from helpers import NOW, row

from cockpit import model, view
from cockpit.theme import HOME_COLOR, PALETTES

NEON = PALETTES["neon"]


class Order(unittest.TestCase):
    def test_needs_you_first_then_working_then_done_then_quiet(self):
        rows = [row("idle1"), row("done1", "done", finishedAt=NOW - 5000), row("work1", "working"), row("needs1", "needs")]
        self.assertEqual(model.fresh_order(rows), ["needs1", "work1", "done1", "idle1"])

    def test_the_selected_card_keeps_its_place_within_its_band(self):
        # Changed for B1 (2026-10-08): it used to expect ["a", "c", "b"], a working card above a "needs you" one,
        # which is the cross-band pinning that drew a band label twice.
        rows = [row("a", "working", startedAt=2), row("b", "working", startedAt=1), row("c", "needs")]
        self.assertEqual(model.stable_order(rows, ["a", "b", "c"], "a"), ["c", "a", "b"])

    def test_quiet_ones_fold_away_unless_shown_or_selected(self):
        rows = [row("w", "working"), row("q", "idle")]
        order = model.fresh_order(rows)
        self.assertEqual([r["sid"] for r in model.visible(rows, order, False, None)[0]], ["w"])
        self.assertEqual([r["sid"] for r in model.visible(rows, order, False, "q")[0]], ["w", "q"])
        self.assertEqual([r["sid"] for r in model.visible(rows, order, True, None)[0]], ["w", "q"])

    def test_counts_fold_quiet_working_into_working(self):
        rows = [row("a", "working"), row("b", "quiet"), row("c", "needs"), row("d", "done"), row("e", "asks")]
        self.assertEqual(model.counts(rows), {"needs": 1, "working": 2, "done": 1})


class Looks(unittest.TestCase):
    def test_a_project_keeps_its_color_and_home_is_neutral(self):
        self.assertEqual(model.project_color(os.path.expanduser("~/Projects/finch/backend")), "#ff9e64")
        self.assertEqual(model.project_color(os.path.expanduser("~")), HOME_COLOR)
        other = os.path.expanduser("~/Projects/some-new-thing")
        self.assertEqual(model.project_color(other), model.project_color(other + "/src"))

    def test_ages_read_short(self):
        self.assertEqual([model.age(NOW - s * 1000, NOW) for s in (5, 90, 7200, 5 * 86400)], ["5s", "1m", "2h", "5d"])

    def test_the_tools_he_sees_most_are_in_words(self):  # G4: "using SendMessage" was the second most common step
        for tool in ("SendMessage", "ToolSearch", "TaskStop", "Artifact", "Monitor", "ListAgents", "CronCreate", "EnterWorktree"):
            self.assertNotIn(tool, model.describe(tool, ""), tool)

    def test_mix_goes_from_one_color_to_the_other(self):
        self.assertEqual(view.mix("#000000", "#ffffff", 0), "#000000")
        self.assertEqual(view.mix("#000000", "#ffffff", 1), "#ffffff")


class Drawing(unittest.TestCase):
    def draw(self, rows, width=41, **kw):
        options = {"selected": None, "live": None, "watched": set(), "show_quiet": False, **kw}
        text, sids = view.render(rows, model.fresh_order(rows), NEON, width, NOW, 0, **options)
        return text.plain.split("\n"), sids, text

    def test_every_line_fills_the_width_exactly(self):
        rows = [row("needs-a-very-long-session-name-that-goes-on", "needs", question="x" * 200), row("w", "working"), row("q")]
        lines, sids, _ = self.draw(rows)
        self.assertTrue(all(len(line) == 41 for line in lines), lines)
        self.assertEqual(len(lines), len(sids))

    def test_each_card_line_maps_back_to_its_session(self):
        lines, sids, _ = self.draw([row("w", "working"), row("d", "done", finishedAt=NOW)])
        self.assertEqual([s for s in sids if s], ["w", "w", "d"])  # a done session is one line (design B)

    def test_a_raw_path_shows_as_its_file_name(self):
        detail = "/Users/x/Downloads/Quarterly\\ report.html"
        self.assertEqual(model.second_line(row("w", "working", detail=detail)), "Quarterly report.html")

    def test_a_card_waiting_on_him_has_orange_text_not_a_fill(self):
        # Pepe (2026-10-09): "instead of highlighting the entire card as pink ... change the text font color to orange"
        _, _, text = self.draw([row("n", "needs", question="ship it?")])
        styles = [str(span.style) for span in text.spans]
        self.assertFalse(any(f"on {NEON.needs}" in s for s in styles))
        self.assertTrue(any(s.startswith(f"bold {NEON.needs}") for s in styles))  # its name

    def test_the_waiting_text_pulses(self):
        waiting = row("n", "needs", question="ship it?", band=1)
        bright, faded = (view.card(waiting, NEON, 41, NOW, frame, selected=False, live=False, watched=False)[0] for frame in (0, 1))
        self.assertNotEqual([str(s.style) for s in bright.spans], [str(s.style) for s in faded.spans])

    def test_idle_sessions_fold_into_one_line(self):
        # v3 (P5): plain words; v2 said "+ 2 quiet · oldest 2h" and "e shows"
        lines, _, _ = self.draw([row("w", "working"), row("q1"), row("q2")])
        self.assertTrue(any("2 idle sessions hidden" in line and line.rstrip().endswith("e to show") for line in lines))

    def test_no_sessions_says_how_to_start(self):
        lines, sids, _ = self.draw([])
        self.assertTrue(any("n starts one" in line for line in lines))
        self.assertFalse(any(sids))


if __name__ == "__main__":
    unittest.main()
