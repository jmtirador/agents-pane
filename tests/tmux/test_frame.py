"""v3's frame, on a private tmux server (problems P1, P2, P3, P6 in docs/problems.md)."""

import pytest

pytestmark = pytest.mark.tmux


def ready(rig):
    rig.launch()
    rig.attach()
    rig.wait_for(lambda: rig.window_option("pane-border-status") == "bottom", "the cockpit's frame applied")


def test_the_terminal_paints_the_background(rig):  # P1
    ready(rig)
    assert rig.window_option("window-style") == "bg=default"
    assert rig.window_option("window-active-style") == "bg=default"
    assert "bg=default" in rig.session_option("status-style")


def test_quiet_lines_and_no_title_lines(rig):  # P2, and Pepe's ask for a line over the keys (2026-10-08)
    ready(rig)
    assert rig.window_option("pane-border-lines") == "single"
    assert rig.window_option("pane-border-format") == ""  # the bottom line carries no title
    assert rig.window_option("pane-border-style") == rig.window_option("pane-active-border-style")
    over_the_bar = rig.whole_screen().rstrip("\n").split("\n")[-2]
    assert set(over_the_bar) <= {"─", "┴"} and "─" in over_the_bar, over_the_bar


def test_the_bar_lists_the_keys_for_the_side_that_has_them(rig):  # P3, P6
    ready(rig)
    bottom = lambda: rig.whole_screen().rstrip("\n").split("\n")[-1]  # noqa: E731
    rig.wait_for(lambda: "go to Claude" in bottom(), "the list's keys in the bar")
    rig.press("Tab")
    rig.wait_for(lambda: "back to your sessions" in bottom() and "go to Claude" not in bottom(), "only the way back in the bar")
    rig.press("C-]")
    rig.wait_for(lambda: "go to Claude" in bottom(), "the list's keys again")


def test_the_list_steps_back_while_claude_has_the_keys(rig):  # P6
    rig.add_session()
    ready(rig)
    rig.wait_for(lambda: "fix the flyer" in rig.screen("list"), "the session's card")
    rig.wait_for(lambda: rig.active() == "list", "the list with the keys")
    # the header's "agents" is bold while the list has the keys and plain while it steps back
    # (ages tick every second, so comparing whole screens would be flaky)
    header_bold = lambda: "\x1b[1m" in rig.screen("list", colors=True).split("\n")[0]  # noqa: E731
    rig.wait_for(header_bold, "a bold header while the list has the keys")
    rig.press("Tab")
    rig.wait_for(lambda: not header_bold(), "the list stepping back")
    rig.press("C-]")
    rig.wait_for(header_bold, "the list back to normal")
