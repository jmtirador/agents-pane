"""The right side's words fit it (72 columns inside the new chat's padding), and the peek and the new chat behave."""

from cockpit.theme import PALETTES
from cockpit.welcome import hints


def test_the_hints_are_one_quiet_line():  # Pepe on the first render: two lines of hints looked incongruent
    line = hints(PALETTES["neon"]).plain
    assert "\n" not in line and len(line) <= 72 and "tab mode" in line


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
    """The screen as text: the SVG's tags out, so differently styled neighbors ("tab" "mode") read as they look."""
    return __import__("html").unescape(__import__("re").sub(r"<[^>]+>", "", app.export_screenshot())).replace("\xa0", " ")


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


# ---------------------------------------------------------------- v4.2: the new chat (H1-H3)

from cockpit import chat  # noqa: E402


@pytest.fixture
def composing(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(chat, "PATH", str(tmp_path / "new-chat.json"))
    monkeypatch.setattr(chat, "default_effort", lambda: "xhigh")
    sent = []
    monkeypatch.setattr(tmuxctl, "tmux", lambda *args: sent.append(args) or __import__("subprocess").CompletedProcess(args, 0, "", ""))
    monkeypatch.setattr(tmuxctl, "pane", lambda role: "%1" if role == "list" else "")
    started = []
    monkeypatch.setattr(tmuxctl, "start", lambda prompt="", cwd=None, name=None, resume=None, choice=None:
                        started.append((prompt, cwd, choice)) or ("cafe0001", ""))
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    store.write_peek({"compose": True, "folder": str(repo), "folders": [str(repo), str(tmp_path)]})
    return started, sent, repo


async def test_the_new_chat_is_one_box_with_its_mode_model_and_effort(composing):
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.3)
        text = shown(app)
        assert "anything" in text and "Yolo" in text and "xhigh" in text and ":main" in text
        assert "tab mode" in text and "ctrl+f folder" in text and "▀▀▀▀" in text  # OpenCode's shallow edge under the box


async def test_a_long_mode_line_keeps_a_gap_and_the_branch(composing, monkeypatch, tmp_path):  # the 4.2 README picture:
    monkeypatch.setattr(chat, "default_effort", lambda: "")  # "default effort~/Projects/agents-pan…", the branch cut off
    monkeypatch.setattr(welcome.sessions, "HOME", str(tmp_path))
    repo = tmp_path / "Projects" / "agents-pane"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/master\n")
    store.write_peek({"compose": True, "folder": str(repo), "folders": [str(repo)]})
    app = welcome.Welcome()
    app.choice = {"mode": "edits", "model": "", "effort": ""}  # the longest line: Accept edits · default model · default effort
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.3)
        info, folder = app.query_one("#info"), app.query_one("#folder-line")
        text = folder.render().plain
        assert text == "…/agents-pane:master" and len(text) <= folder.size.width  # never cut by the ellipsis
        assert folder.region.x - info.region.right >= 2


def drawn_on(app, selector):
    """The backgrounds a widget's first line is drawn with."""
    return {seg.style.bgcolor.name if seg.style and seg.style.bgcolor else None for seg in app.query_one(selector).render_line(0)}


async def test_a_viewer_started_before_the_list_wrote_anything_draws_the_whole_box(tmp_path, monkeypatch):  # the 4.2
    monkeypatch.setattr(store, "PATH", str(tmp_path / "state.json"))  # README demo: an empty mode line on the terminal's
    monkeypatch.setattr(chat, "PATH", str(tmp_path / "new-chat.json"))  # own background, then the panel color painted
    monkeypatch.setattr(chat, "default_effort", lambda: "xhigh")  # over the box but never behind its text
    monkeypatch.setattr(tmuxctl, "launch_folder", lambda: str(tmp_path))
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.3)
        assert "Yolo" in shown(app)
        store.write_peek({"compose": True, "folder": str(tmp_path), "folders": [str(tmp_path)]})  # the list, a moment later
        await pilot.pause(0.4)
        panel = PALETTES["neon"].sel
        assert drawn_on(app, "#info") == {panel} and drawn_on(app, "#folder-line") == {panel}


async def test_tab_ctrl_l_and_ctrl_t_change_the_mode_model_and_effort(composing):
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.6)  # past the double-Tab guard
        await pilot.press("tab", "ctrl+l", "ctrl+t")
        await pilot.pause(0.2)
        text = shown(app)
        assert "Auto" in text and "Opus" in text and "low" in text
        await pilot.press("shift+tab")
        await pilot.pause(0.2)
        assert "Yolo" in shown(app)


async def test_enter_starts_it_here_with_the_choices_and_remembers_them(composing):
    started, _, repo = composing
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("tab", "tab")  # Plan
        await pilot.press(*"fix it", "ctrl+j", *"then test", "enter")
        await pilot.pause(0.3)
        assert started == [("fix it\nthen test", str(repo), {"mode": "plan", "model": "", "effort": ""})]
        assert app.return_value == "cafe0001"
    assert chat.load()["mode"] == "plan"


async def test_a_session_that_wont_start_keeps_the_text_and_says_why(composing, monkeypatch):  # the critic: auto can refuse
    monkeypatch.setattr(tmuxctl, "start", lambda *a, **k: (None, "Auto mode isn't available yet: run claude --permission-mode auto once"))
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.6)
        await pilot.press(*"fix it", "enter")
        await pilot.pause(0.3)
        assert "isn't available yet" in shown(app) and app.query_one("TextArea").text == "fix it"


async def test_a_double_tab_does_not_flip_the_mode(composing):  # the critic: Tab in the list, then Tab again
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.05)
        app.composer_focused()  # the keys just arrived
        await pilot.press("tab")
        await pilot.pause(0.1)
        assert "Yolo" in shown(app)


async def test_esc_gives_the_keys_back_and_keeps_the_draft(composing):
    _, sent, _ = composing
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.6)
        await pilot.press(*"half a thought", "escape")
        await pilot.pause(0.2)
        assert ("select-pane", "-t", "%1") in sent and app.query_one("TextArea").text == "half a thought"


async def test_ctrl_f_picks_another_folder(composing, tmp_path):
    started, _, _ = composing
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("ctrl+f")
        await pilot.pause(0.2)
        assert "enter start here" in shown(app) and "esc cancel" in shown(app) and "tab mode" not in shown(app)  # the keys that work now
        await pilot.press("down", "enter")
        await pilot.pause(0.2)
        assert "tab mode" in shown(app)
        await pilot.press(*"go", "enter")
        await pilot.pause(0.3)
        assert started and started[-1][1] == str(tmp_path)


async def test_the_folder_list_keeps_the_keys_when_they_come_back(composing, tmp_path):  # review 2: Enter started in the old folder
    started, _, _ = composing
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.6)
        await pilot.press(*"go", "ctrl+f")
        await pilot.pause(0.2)
        app.on_app_focus()  # the keys went to the list and came back
        await pilot.pause(0.2)
        await pilot.press("down", "enter")
        await pilot.pause(0.2)
        assert app.folder == str(tmp_path) and "tab mode" in shown(app)
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert started and started[-1][1] == str(tmp_path)


async def test_the_double_tab_that_brings_the_keys_back_leaves_the_folder_list_open(composing):  # second review
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("ctrl+f")
        await pilot.pause(0.2)
        app.on_app_focus()  # the first Tab, in the list, brought the keys here
        await pilot.press("tab")  # the second one lands in the folder list
        await pilot.pause(0.2)
        assert app.query_one(welcome.Folders).display and app.focused is app.query_one(welcome.Folders)


async def test_tab_in_the_folder_list_closes_it(composing):  # review 2: the list and its hints stayed up
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("ctrl+f", "tab")
        await pilot.pause(0.2)
        assert not app.query_one(welcome.Folders).display and "tab mode" in shown(app)


async def test_a_backslash_before_the_cursor_makes_a_new_line_there(composing):  # review 2: it ate the next character
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.6)
        await pilot.press(*"ab\\c", "left", "enter")
        await pilot.pause(0.2)
        assert app.query_one(welcome.Prompt).text == "ab\nc"
        await pilot.press("end", "\\", "enter")
        await pilot.pause(0.2)
        assert app.query_one(welcome.Prompt).text == "ab\nc\n"


async def test_a_folder_that_is_gone_is_said_not_started_in_home(composing, tmp_path):  # review 2: the old form refused it
    started, _, _ = composing
    app = welcome.Welcome()
    async with app.run_test(size=(76, 27)) as pilot:
        await pilot.pause(0.6)
        app.folder, app.picked = str(tmp_path / "deleted-worktree"), True
        await pilot.press(*"go", "enter")
        await pilot.pause(0.3)
        assert not started and "no folder" in shown(app) and app.query_one(welcome.Prompt).text == "go"


async def test_a_short_pane_keeps_the_box_and_drops_the_wordmark(composing):  # the critic: 22 rows overflowed
    app = welcome.Welcome()
    async with app.run_test(size=(76, 16)) as pilot:
        await pilot.pause(0.3)
        assert "anything" in shown(app) and not app.query_one(welcome.Mark).display  # the bar is blocks too, so ask the widget
