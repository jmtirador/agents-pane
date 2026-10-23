"""The welcome screen's words fit its box (64 columns, minus the "Tip: " prefix)."""

from cockpit.theme import PALETTES
from cockpit.welcome import TIPS, keys_line


def test_every_tip_fits_on_one_line():
    assert all(len("Tip: " + tip) <= 60 for tip in TIPS)


def test_the_way_back_has_one_name_everywhere():  # P5: it said "back to the list" here and "back to your sessions" in the bar
    assert "ctrl+] back to your sessions" in keys_line(PALETTES["neon"]).plain
    assert len(keys_line(PALETTES["neon"]).plain) <= 62


# ---------------------------------------------------------------- v4.1: the peek (G1)

import json  # noqa: E402

import pytest  # noqa: E402

from cockpit import store, tmuxctl, welcome  # noqa: E402


@pytest.fixture
def peeked(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PATH", str(tmp_path / "state.json"))
    sent = []
    monkeypatch.setattr(tmuxctl, "tmux", lambda *args: sent.append(args) or __import__("subprocess").CompletedProcess(args, 0, "", ""))
    monkeypatch.setattr(tmuxctl, "pane", lambda role: "%1" if role == "list" else "")
    transcript = tmp_path / "s1.jsonl"
    reply = "## The plan\n\n- move the export to a worker\n- **retry** failed rows\n\nWant me to start?"
    transcript.write_text(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": reply}]}}) + "\n")
    store.write_peek({"sid": "s1", "path": str(transcript), "name": "export rework", "label": "last active 3d ago", "where": "~/Projects/finch",
                      "asked": "make the export not time out", "recap": "Planned the export rework.", "question": "", "options": [],
                      "note": "It isn't running right now.", "keys": [["enter", "start it again here"], ["r", "reply"]], "doing": ""})
    return sent


def shown(app):
    return __import__("html").unescape(app.export_screenshot()).replace("\xa0", " ")


async def test_a_peek_shows_the_session_what_he_asked_and_its_last_reply(peeked):
    app = welcome.Welcome()
    async with app.run_test(size=(76, 28)) as pilot:
        await pilot.pause(0.3)
        text = shown(app)
        for words in ("export rework", "last active 3d ago", "make the export not time out", "retry", "Planned the export rework",
                      "isn't running", "start it again here"):
            assert words in text, words
        assert not app.query_one("#all").display  # no new-session box under a peek: typing there started a session (the critic)


async def test_enter_alone_on_a_peek_opens_it_and_esc_goes_back(peeked):
    app = welcome.Welcome()
    async with app.run_test(size=(76, 28)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause(0.6)
        assert ("send-keys", "-t", "%1", "Enter") in peeked and ("select-pane", "-t", "%1") in peeked
        peeked.clear()
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert ("select-pane", "-t", "%1") in peeked and not any(c[0] == "send-keys" for c in peeked)


async def test_a_sentence_typed_on_a_peek_does_nothing(peeked):  # the runtime tester: "can you fix it" started a session
    app = welcome.Welcome()
    async with app.run_test(size=(76, 28)) as pilot:
        await pilot.pause(0.3)
        for words in ("can you fix it", "a quick fix", "where is it"):
            await pilot.press(*[{" ": "space"}.get(ch, ch) for ch in words], "enter")
            await pilot.pause(0.6)
        assert not any(c[0] in ("send-keys", "select-pane") for c in peeked) and "nothing to type into" in shown(app)


async def test_a_blank_peek_shows_nothing_and_no_peek_is_the_welcome(peeked):
    store.write_peek({"blank": True})
    app = welcome.Welcome()
    async with app.run_test(size=(76, 28)) as pilot:
        await pilot.pause(0.3)
        assert not app.query_one("#all").display and not app.query_one("#peek").display
        store.write_peek({})
        await pilot.pause(0.3)
        assert app.query_one("#all").display


async def test_a_theme_change_and_a_new_peek_at_once_show_the_new_peek(peeked):  # review 6
    app = welcome.Welcome()
    async with app.run_test(size=(76, 28)) as pilot:
        await pilot.pause(0.3)
        store.save({**store.load(), "theme": "tokyo"})
        store.write_peek({**store.read_peek(), "name": "another session"})
        app.seen["peek"] = app.seen["state"] = None  # both changed in the same tick
        app.watch()
        await pilot.pause(0.2)
        assert "another session" in shown(app)


async def test_a_pending_enter_never_acts_on_another_card(peeked):  # second pass: Enter, then a click on another card
    app = welcome.Welcome()
    async with app.run_test(size=(76, 28)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("enter")
        store.write_peek({**store.read_peek(), "sid": "s2", "name": "another"})
        await pilot.pause(0.6)
        assert not any(c[0] == "send-keys" for c in peeked)


async def test_enter_right_after_esc_still_opens_and_the_hint_goes(peeked):  # second pass
    app = welcome.Welcome()
    async with app.run_test(size=(76, 28)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("x")
        assert "nothing to type into" in shown(app)
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert "nothing to type into" not in shown(app)
        await pilot.pause(1.1)  # past the typing window of the "x"
        peeked.clear()
        await pilot.press("escape", "enter")
        await pilot.pause(0.6)
        assert ("send-keys", "-t", "%1", "Enter") in peeked
