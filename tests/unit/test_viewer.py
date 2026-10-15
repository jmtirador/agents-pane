"""The viewer: a pane on the right side must outlive any error, and it notices when Claude leaves its session (decision 0006)."""

import os
import subprocess
import time

import pytest

from cockpit import viewer


class Parked(Exception):
    pass


@pytest.fixture
def parked(monkeypatch):
    """park() waits forever in real life; here it raises, carrying what the viewer would say."""
    def park(pane, why):
        raise Parked(why)
    monkeypatch.setattr(viewer, "park", park)
    monkeypatch.setattr(viewer.time, "sleep", lambda s: None)
    monkeypatch.setattr(viewer, "job_state", lambda job: "working")


def test_a_missing_claude_parks_the_viewer_instead_of_closing_the_right_side(monkeypatch, parked):
    # the v4 review: with `claude` gone (mid-update), the viewer died, its pane closed and the next pick swapped the list away
    def missing(*args, **kw):
        raise FileNotFoundError("claude")
    monkeypatch.setattr(viewer.subprocess, "Popen", missing)
    with pytest.raises(Parked, match="couldn't open"):
        viewer.attach("%9", "aaaa0001")


def test_any_error_parks_the_viewer(monkeypatch, parked):
    monkeypatch.setattr(viewer, "ignore_claude_keys", lambda: None)
    monkeypatch.setenv("TMUX_PANE", "%9")
    monkeypatch.setattr(viewer.sys, "argv", ["viewer", "aaaa0001"])
    monkeypatch.setattr(viewer, "attach", lambda pane, job: 1 / 0)
    with pytest.raises(Parked, match="went wrong"):
        viewer.main()


def test_it_reads_a_command_line():
    assert "pytest" in viewer.command_line(os.getpid())
    assert viewer.command_line(2**22 + 12345) is None  # no such process


def test_an_attach_that_turns_into_claudes_own_session_list_is_closed(monkeypatch):
    # F5 on real Claude 2.1.300: ←, /exit and Ctrl+C twice turn `claude attach <job>` into `claude agents`, in place
    real = subprocess.Popen
    monkeypatch.setattr(viewer.subprocess, "Popen", lambda args: real(["/bin/bash", "-c", 'exec -a "claude agents" sleep 30']))
    started = time.time()
    viewer.run_attach("aaaa0001")
    assert time.time() - started < 2


def test_an_attach_claude_renames_some_other_way_is_left_alone(monkeypatch):
    # the re-review: Claude sets its own process title; if an update changes it, healthy attaches must not die
    real = subprocess.Popen
    monkeypatch.setattr(viewer.subprocess, "Popen", lambda args: real(["/bin/bash", "-c", 'exec -a "claude attach-v2 x" sleep 1']))
    started = time.time()
    viewer.run_attach("aaaa0001")
    assert time.time() - started >= 0.9


def test_an_attach_on_its_session_is_left_alone(monkeypatch):
    real = subprocess.Popen
    monkeypatch.setattr(viewer.subprocess, "Popen", lambda args: real(["/bin/bash", "-c", 'exec -a "claude attach aaaa0001" sleep 1']))
    started = time.time()
    viewer.run_attach("aaaa0001")
    assert time.time() - started >= 0.9  # it ran until it ended by itself
