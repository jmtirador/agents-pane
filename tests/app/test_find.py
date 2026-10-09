"""B4: Enter in Find opens a result for what's in the box now, and nothing you didn't confirm."""

import os
import time

from cockpit import sessions


def hit(sid, name):
    return {"sid": sid, "name": name, "snippet": name, "at": 0, "date": "10/8", "cwd": os.path.expanduser("~/Projects/finch")}


def fake_search(query, limit=20):
    return {"log": [hit("old-log", "log cleanup")], "login": [hit("old-login", "login bug")]}.get(query.strip(), [])


def slow_search(query, limit=20):
    time.sleep(0.5)  # a real search over every transcript can take a couple of seconds
    return [hit(f"old-{query}", query)]


async def test_enter_right_after_typing_opens_the_current_query(cockpit, monkeypatch):
    monkeypatch.setattr(sessions, "search", fake_search)
    async with cockpit.app.run_test(size=(96, 30)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("slash", *"log")
        await pilot.pause(0.8)  # the results for "log" are showing
        await pilot.press(*"in", "enter")  # Enter before the 0.35 s pause after typing
        await cockpit.settle(pilot, 1.0)
        assert [s["resume"] for s in cockpit.started] == ["old-login"]


async def test_enter_with_nothing_found_opens_nothing(cockpit, monkeypatch):
    monkeypatch.setattr(sessions, "search", fake_search)
    async with cockpit.app.run_test(size=(96, 30)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("slash", *"zzz", "enter")
        await cockpit.settle(pilot, 1.0)
        assert cockpit.started == []


async def test_typing_after_enter_cancels_the_open(cockpit, monkeypatch):
    monkeypatch.setattr(sessions, "search", slow_search)
    async with cockpit.app.run_test(size=(96, 30)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("slash", *"sch", "enter", "x")  # changed his mind before the results came back
        await cockpit.settle(pilot, 2.0)
        assert cockpit.started == []


async def test_picking_by_hand_cancels_the_open(cockpit, monkeypatch):
    monkeypatch.setattr(sessions, "search", slow_search)
    async with cockpit.app.run_test(size=(96, 30)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("slash", *"sch")
        await pilot.pause(1.5)  # the results for "sch" are showing
        await pilot.press(*"ema", "enter", "down")  # Enter, then reached for the list before the new results came
        await cockpit.settle(pilot, 1.0)
        assert cockpit.started == []
