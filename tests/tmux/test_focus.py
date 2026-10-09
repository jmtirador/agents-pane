"""B2 and B3: which side has the keys after Tab, Enter and Ctrl+], with and without a dialog open."""

import time

import pytest

pytestmark = pytest.mark.tmux


def settled_on(rig, role, seconds=1.5):
    """Wait, then say whether the keys are (still) on this side; a late flip would show up here."""
    time.sleep(seconds)
    return rig.active() == role


def start(rig, session=False):
    if session:
        rig.add_session()
    rig.launch()
    rig.attach()
    rig.wait_for(lambda: "agents" in rig.screen("list") or "No sessions" in rig.screen("list") or "fix the flyer" in rig.screen("list"),
                 "the list drawn")
    rig.wait_for(lambda: rig.active() == "list", "the list starting with the keys")


def test_tab_twice_still_ends_on_the_claude_side(rig):
    start(rig)
    rig.press("Tab", "Tab")
    assert settled_on(rig, "live")


def test_enter_then_tab_ends_on_the_claude_side(rig):
    start(rig, session=True)
    rig.press("Enter", "Tab")
    assert settled_on(rig, "live")


def test_the_bar_flip_key_brings_the_keys_back_from_claude(rig):
    start(rig)
    rig.press("Tab")
    rig.wait_for(lambda: rig.active() == "live", "the Claude side getting the keys")
    rig.keys("list", "F12")  # what a click on the bar's flip key sends to the list
    rig.wait_for(lambda: rig.active() == "list", "the list getting them back")


def test_ctrl_bracket_does_nothing_while_a_dialog_is_open(rig):
    start(rig)
    rig.press("n")
    rig.wait_for(lambda: rig.option("list", "window_zoomed_flag") == "1", "the dialog taking the window")
    rig.press("C-]")
    time.sleep(1)
    assert rig.option("list", "window_zoomed_flag") == "1"
    assert rig.active() == "list"


def test_ctrl_bracket_waits_for_the_theme_menu_too(rig):  # the menu doesn't zoom, so the zoom flag can't guard it
    start(rig)
    rig.press("t")
    rig.wait_for(lambda: rig.session_option("@ap_dialog") == "1", "the menu marking a dialog open")
    rig.press("C-]")
    assert settled_on(rig, "list")
    rig.press("Escape")
    rig.wait_for(lambda: rig.session_option("@ap_dialog") == "", "the mark cleared when it closes")
