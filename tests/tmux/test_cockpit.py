"""The real cockpit on a private tmux server: layout, going live, replying, flipping sides."""

import os
import signal
import subprocess

import pytest
from conftest import JOB

pytestmark = pytest.mark.tmux


def test_the_launcher_builds_a_list_and_a_live_pane(rig):
    rig.launch()
    rig.wait_for(lambda: rig.tmux("display-message", "-p", "-t", rig.panes()["list"], "#{pane_width}").stdout.strip() == "42",
                 "the list at 42 columns")


def test_enter_shows_the_session_live(rig):
    rig.add_session()
    rig.launch()
    rig.wait_for(lambda: "fix the flyer" in rig.screen("list"), "the session's card")
    rig.keys("list", "Enter")
    rig.wait_for(lambda: f"FAKE CLAUDE attached to {JOB}" in rig.screen("live"), "the session in the live pane")
    assert rig.option("live", "@ap_want") == JOB


def test_a_reply_is_typed_into_the_session(rig):
    rig.add_session()
    rig.launch()
    rig.wait_for(lambda: "fix the flyer" in rig.screen("list"), "the session's card")
    rig.keys("list", "r")
    rig.wait_for(lambda: "reply" in rig.screen("list"), "the reply dialog")
    rig.keys("list", "-l", "--", "- ship it\\;")  # the test types through tmux too, so it escapes like the app does
    rig.keys("list", "Enter")
    rig.wait_for(lambda: f"{JOB} got: - ship it;" in rig.log("typed.log"), "the reply reaching the session")


def test_ctrl_bracket_moves_the_keys_between_the_two_sides(rig):
    rig.launch()
    rig.attach()
    rig.wait_for(lambda: rig.active() == "list", "the list starting with the keys")
    rig.press("C-]")
    rig.wait_for(lambda: rig.active() == "live", "the live side getting the keys")
    rig.press("C-]")
    rig.wait_for(lambda: rig.active() == "list", "the list getting them back")


def test_the_list_comes_back_after_a_crash_under_zsh(rig):
    # his tmux runs commands with zsh, where a word starting with "=" is a command lookup: the restart loop's
    # `-t =agents:` made zsh quit, and the list pane closed instead of offering to restart (2026-10-09)
    with open(rig.dir / "test.tmux.conf", "a") as conf:
        conf.write("set -g default-shell /bin/zsh\n")
    rig.launch()
    rig.wait_for(lambda: "agents" in rig.screen("list"), "the list drawn")
    shell = rig.option("list", "pane_pid")
    app = subprocess.run(["pgrep", "-P", shell], capture_output=True, text=True).stdout.split()[0]
    os.kill(int(app), signal.SIGKILL)
    rig.wait_for(lambda: "The list stopped" in rig.screen("list"), "the restart prompt")
    rig.keys("list", "Enter")
    rig.wait_for(lambda: "agents" in rig.screen("list"), "the list back")
