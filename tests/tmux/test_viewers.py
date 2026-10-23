"""v4: warm viewers on a private tmux server with a fake claude (decision 0006, problems F1, F4, F5)."""

import json
import subprocess
import time

import conftest
import pytest

pytestmark = pytest.mark.tmux

A, A_SID = "aaaa0001", "aaaa0001-0000-4000-8000-000000000001"
B, B_SID = "bbbb0002", "bbbb0002-0000-4000-8000-000000000002"


def two_sessions(rig):
    rig.add_session(sid=A_SID, job=A, prompt="first job", status="busy")
    rig.add_session(sid=B_SID, job=B, prompt="second job", status="busy")
    rig.launch()
    rig.attach()
    rig.wait_for(lambda: "first job" in rig.screen("list") and "second job" in rig.screen("list"), "both cards")
    rig.wait_for(lambda: rig.active() == "list", "the list with the keys")


def on_right(rig, job):
    return f"FAKE CLAUDE attached to {job}" in rig.screen("live")


def attaches(rig, job):
    return rig.log("calls.log").count(f"claude attach {job}")


def walk_to(rig, job):
    """Move the cursor with the arrows until the right side shows this job."""
    for key in ("Down", "Down", "Down", "Up", "Up", "Up"):
        if on_right(rig, job):
            return
        rig.press(key)
        time.sleep(0.5)
    rig.wait_for(lambda: on_right(rig, job), f"{job} on the right")


def test_going_back_to_a_session_reuses_its_viewer(rig):  # F1: no fresh attach, no wait
    two_sessions(rig)
    walk_to(rig, A)
    walk_to(rig, B)
    rig.press("Up" if rig.screen("list").index("first job") < rig.screen("list").index("second job") else "Down")
    started = time.time()
    rig.wait_for(lambda: on_right(rig, A), "the first session back on the right")
    assert time.time() - started < 1.0
    assert attaches(rig, A) == 1  # the same viewer swapped back in, not a second claude attach


def test_hidden_viewers_are_out_of_reach(rig):  # decision 0006: next-window and the status bar can't land on one
    two_sessions(rig)
    walk_to(rig, A)
    walk_to(rig, B)
    windows = rig.tmux("list-windows", "-t", "=agents", "-F", "#{window_name}").stdout.split()
    assert windows == ["cockpit"]
    assert rig.tmux("has-session", "-t", "=agents-viewers").returncode == 0


@pytest.mark.parametrize("way_out", ["/exit", "/ctrl-z"])  # ← and Ctrl+C twice act like /exit
def test_leaving_a_session_inside_claude_brings_it_back_and_the_keys_to_the_list(rig, way_out):  # F5: "ctrl c just closes the claude window"
    two_sessions(rig)
    walk_to(rig, A)
    rig.press("Enter")
    rig.wait_for(lambda: rig.active() == "live", "the keys on the Claude side")
    time.sleep(1.6)  # longer than a failed start, so the viewer reads the exit as his detach
    rig.keys("live", "-l", way_out)
    rig.keys("live", "Enter")
    rig.wait_for(lambda: attaches(rig, A) == 2, "the same session attached again")
    rig.wait_for(lambda: on_right(rig, A) and rig.active() == "list", "it back on the right, the keys back in the list")
    assert "AGENT VIEW" not in rig.screen("live")
    assert not rig.tmux("list-panes", "-a", "-F", "#{pane_current_command}").stdout.count("sleep")  # Claude's list was closed


def test_a_stopped_session_is_not_brought_back_by_itself(rig):  # decision 0006: a reattach would undo a stop
    two_sessions(rig)
    walk_to(rig, A)
    time.sleep(1.6)
    (rig.config / "jobs" / A / "state.json").write_text(json.dumps({"sessionId": A_SID, "state": "stopped"}))
    rig.keys("live", "-l", "/exit")
    rig.keys("live", "Enter")
    rig.wait_for(lambda: "This session is stopped" in rig.screen("live"), "the viewer saying it's stopped")
    time.sleep(1.5)
    assert attaches(rig, A) == 1


def test_q_closes_the_dashboard_and_frees_the_hidden_viewers(rig):  # F4
    two_sessions(rig)
    walk_to(rig, A)
    walk_to(rig, B)
    rig.press("q")
    rig.wait_for(lambda: not rig.tmux("list-clients", "-t", "=agents").stdout.strip(), "the client gone")
    assert rig.tmux("has-session", "-t", "=agents").returncode == 0  # everything keeps running
    rig.wait_for(lambda: rig.tmux("has-session", "-t", "=agents-viewers").returncode != 0, "the hidden viewers closed")


def test_a_dead_right_side_comes_back_and_never_takes_the_list(rig):  # the v4 review, then the v4.1 runtime tester
    two_sessions(rig)
    listp = rig.panes()["list"]
    rig.tmux("kill-pane", "-t", rig.panes()["live"])
    rig.wait_for(lambda: list(rig.panes()) == ["list"], "only the list left")
    rig.press("Down")
    rig.wait_for(lambda: set(rig.panes()) == {"list", "live"}, "a new right side")
    assert rig.panes()["list"] == listp and rig.option("list", "pane_width") == "42"


def test_a_reply_leaves_an_open_dialog_alone(rig):  # the v4 review: the repaint nudge after a reply un-zoomed the next dialog
    two_sessions(rig)
    zoomed = lambda: rig.tmux("display-message", "-p", "-t", "=agents:cockpit", "#{window_zoomed_flag}").stdout.strip() == "1"  # noqa: E731
    rig.press("r")
    rig.wait_for(zoomed, "the reply dialog")
    rig.keys("list", "-l", "on it")
    rig.keys("list", "Enter")
    rig.wait_for(lambda: not zoomed(), "the reply dialog closed")
    rig.press("?")  # the next dialog opens while the reply is still being typed in
    rig.wait_for(lambda: " got: on it" in rig.log("typed.log"), "the reply reaching the session")
    time.sleep(2.5)  # type_into waits 1.5 s after typing, then nudges
    assert zoomed()


def test_a_cockpit_from_before_4_is_rebuilt(rig):  # its right side ran live.py, not a viewer: the upgrade is running it again
    rig.launch()
    rig.tmux("set-option", "-p", "-u", "-t", rig.panes()["live"], "@ap_job")  # what a 3.x right side looks like
    rig.launch()
    assert rig.option("live", "@ap_job") == "welcome"  # rebuilt (pane ids can repeat: the server restarts)


@pytest.mark.parametrize("dialog", ["n", "/", "?"])
def test_a_switch_that_lands_under_a_dialog_leaves_the_list_in_place(rig, dialog):  # the v4 stress test: 7 in 7 broke
    two_sessions(rig)
    rig.press("Down", dialog)  # the switch lands 0.12 s later, under the dialog that zoomed the list
    time.sleep(1.0)
    assert set(rig.panes()) == {"list", "live"}  # broken, the list sat in the hidden session and two viewers here
    rig.press("Escape")
    rig.wait_for(lambda: set(rig.panes()) == {"list", "live"} and rig.option("list", "pane_width") == "42", "the list and the right side back")


def test_enter_on_a_parked_right_side_starts_it_over_cleanly(rig):  # the re-review: a duplicate viewer hid the right side
    two_sessions(rig)
    walk_to(rig, A)
    time.sleep(1.6)
    (rig.config / "jobs" / A / "state.json").write_text(json.dumps({"sessionId": A_SID, "state": "stopped"}))
    rig.keys("live", "-l", "/exit")
    rig.keys("live", "Enter")
    rig.wait_for(lambda: "This session is stopped" in rig.screen("live"), "the viewer parked")
    (rig.config / "jobs" / A / "state.json").write_text(json.dumps({"sessionId": A_SID, "state": "working"}))
    rig.press("Enter")  # what the parked message says to do
    rig.wait_for(lambda: attaches(rig, A) == 2 and on_right(rig, A) and rig.active() == "live", "it started over, with the keys")
    rig.press("C-]")
    rig.wait_for(lambda: rig.active() == "list", "the keys back in the list")
    walk_to(rig, B)  # the next move isn't dropped
    jobs = rig.tmux("list-panes", "-a", "-F", "#{@ap_job}").stdout.split()
    assert jobs.count(A) == 1  # the parked one was closed, not left behind


def test_a_session_started_under_an_open_dialog_leaves_the_dialog_alone(rig):  # the re-review: focus unzoomed it
    two_sessions(rig)
    zoomed = lambda: rig.tmux("display-message", "-p", "-t", "=agents:cockpit", "#{window_zoomed_flag}").stdout.strip() == "1"  # noqa: E731
    rig.press("?")
    rig.wait_for(zoomed, "the help dialog")
    rig.launch("one more thing")  # bin/agents-pane "prompt": starts a session, shows it and gives it the keys
    rig.wait_for(lambda: rig.log("calls.log").count("claude attach cafe0001") == 1, "the new session's viewer")
    time.sleep(0.5)
    assert zoomed() and rig.active() == "list"


def test_a_healthy_cockpit_is_never_rebuilt(rig):  # a false rebuild would close his dashboard on every yolo
    two_sessions(rig)
    walk_to(rig, A)
    rig.tmux("set-option", "-t", "=agents:", "@probe", "still here")
    rig.press("?")  # a dialog open, a job viewer on the right
    rig.launch()
    assert rig.session_option("@probe") == "still here"


def test_a_double_click_on_a_card_leaves_the_keys_in_the_session(rig):  # the v4.1 runtime tester: 24 in 24 stayed in the list
    two_sessions(rig)
    y = next(i for i, line in enumerate(rig.whole_screen().splitlines()) if "second job" in line[:42])
    click = f"\x1b[<0;6;{y + 1}M\x1b[<0;6;{y + 1}m"
    subprocess.run([conftest.REAL_TMUX, "-L", rig.outer, "send-keys", "-t", "0", "-l", click + click], env=rig.env)
    time.sleep(1.0)  # tmux's own double-click action ran 0.3 s later and took the keys back
    assert on_right(rig, B) and rig.active() == "live"


def test_a_rebuilt_right_side_reuses_a_warm_viewer(rig):  # second pass: it started a second claude attach
    two_sessions(rig)
    walk_to(rig, A)
    walk_to(rig, B)
    walk_to(rig, A)  # B is warm in the hidden session now
    rig.tmux("kill-pane", "-t", rig.panes()["live"])
    rig.wait_for(lambda: list(rig.panes()) == ["list"], "only the list left")
    rig.press("Down" if rig.screen("list").index("first job") < rig.screen("list").index("second job") else "Up")
    rig.wait_for(lambda: on_right(rig, B), "B back on the right")
    assert attaches(rig, B) == 1  # the warm one moved in; no second attach
