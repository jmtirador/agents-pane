"""Picture tests: the look Pepe approved on 2026-10-08 ("it looks great no problems"), locked in.

Each test draws a screen headless and compares it with the saved SVG in __snapshots__/. A change to the
look fails here on purpose: if the change is wanted, look at the report, then run
`.venv/bin/python -m pytest tests/app/test_pictures.py --snapshot-update` and commit the new pictures.
The clock and the working dot's pulse are frozen, so a picture only changes when the look does.
"""

import os
import time

import pytest
from helpers import NOW, row

from cockpit import app as appmod
from cockpit import chat, store, tmuxctl, welcome

HOME = os.path.expanduser("~")
# his 119x29 terminal less the key bar and the line over it: every pane is 27 rows
LIST = (42, 27)  # the list pane
ZOOMED = (119, 27)  # a dialog has the whole window
LIVE = (76, 27)  # the Claude side


@pytest.fixture
def rows():
    return [
        row("needs-aaa", "needs", name="pricing-page", question="Ship the new pricing table now, or keep the A/B test running?",
            cwd=f"{HOME}/Projects/storefront", where="storefront"),
        row("work-bbbb", "working", name="rate limits", cwd=f"{HOME}/Projects/api", where="api",
            detail="adding a token bucket to the public endpoints", startedAt=NOW - 1_080_000, turnStart=NOW - 1_080_000),
        row("work-cccc", "working", name="schema migration", cwd=f"{HOME}/Projects/api", where="api",
            detail="backfilling the orders table in batches", startedAt=NOW - 50_000, turnStart=NOW - 50_000),
        row("done-dddd", "done", name="flaky test hunt", cwd=f"{HOME}/Projects/storefront", where="storefront",
            finishedAt=NOW - 120_000, away="Found it: a race in the cache warmup."),
        row("idle-eeee", name="docs refresh", lastChange=NOW - 7_200_000),
        row("idle-ffff", name="dependency bumps", lastChange=NOW - 9_000_000),
    ]


class FrozenClock:
    """time, with time() stuck at the rows' NOW."""

    def __getattr__(self, name):
        return getattr(time, name)

    def time(self):
        return NOW / 1000


@pytest.fixture
def still(cockpit, monkeypatch):
    monkeypatch.setattr(appmod, "time", FrozenClock())
    monkeypatch.setattr(appmod.ListScreen, "spin", lambda self: None)  # the working dot's pulse
    monkeypatch.setattr(tmuxctl, "launch_folder", lambda: f"{HOME}/Projects/storefront")  # not a random temp folder
    monkeypatch.setattr(appmod, "__version__", "3.0.0")  # a release mustn't change the pictures
    cockpit.tmux.viewers["work-bbb"] = "%3"
    cockpit.tmux.slot_job = "work-bbb"  # the right side shows "rate limits"
    return cockpit


def theme(name):
    store.save({**store.load(), "theme": name})


async def no_blink(pilot):
    for field in pilot.app.screen.query("Input, TextArea"):
        field.cursor_blink = False
    await pilot.pause(0.3)


@pytest.mark.parametrize("name", ["neon", "mission", "tokyo"])
def test_the_list(still, snap_compare, name):
    theme(name)
    assert snap_compare(still.app, terminal_size=LIST, run_before=no_blink)


def test_the_list_while_claude_has_the_keys(still, snap_compare):
    async def blur(pilot):
        pilot.app.screen.set_dim(True)
        await pilot.pause(0.3)

    assert snap_compare(still.app, terminal_size=LIST, run_before=blur)


def test_the_theme_menu_trying_mission(still, snap_compare):
    assert snap_compare(still.app, terminal_size=LIST, press=["t", "down"], run_before=no_blink)


def test_all_keys(still, snap_compare):
    assert snap_compare(still.app, terminal_size=ZOOMED, press=["question_mark"], run_before=no_blink)


@pytest.fixture
def new_chat(monkeypatch, tmp_path):
    """The new chat with nothing of his: a fixed folder and branch, his default effort, no remembered choice."""
    monkeypatch.setattr(store, "PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(chat, "PATH", str(tmp_path / "new-chat.json"))
    monkeypatch.setattr(chat, "default_effort", lambda: "xhigh")
    monkeypatch.setattr(tmuxctl, "launch_folder", lambda: f"{HOME}/Projects/storefront")
    monkeypatch.setattr(welcome, "branch", lambda folder: "main")
    store.write_peek({"compose": True, "folders": [f"{HOME}/Projects/api", f"{HOME}/Projects/docs-site"]})
    return welcome.Welcome()


def test_the_new_chat(new_chat, snap_compare):  # v4.2: OpenCode's home screen, one chat box (problems H1)
    assert snap_compare(new_chat, terminal_size=LIVE, run_before=no_blink)


def test_the_new_chat_in_plan_mode_picking_a_folder(new_chat, snap_compare):
    async def plan_and_folders(pilot):
        await pilot.pause(welcome.TAB_GUARD_S + 0.1)  # past the double-tap guard, so Tab changes the mode
        await pilot.press("tab", "tab", "ctrl+f")
        await no_blink(pilot)

    assert snap_compare(new_chat, terminal_size=LIVE, run_before=plan_and_folders)
