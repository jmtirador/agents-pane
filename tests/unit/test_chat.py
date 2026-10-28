"""A new chat's mode, model and effort (problems H2): what each choice puts on the claude command line, and memory."""

import pytest

from cockpit import chat, tmuxctl


@pytest.fixture
def memory(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "PATH", str(tmp_path / "new-chat.json"))


def test_each_mode_is_its_claude_flag():
    assert chat.flags({"mode": "yolo", "model": "", "effort": ""}) == ["--dangerously-skip-permissions"]
    assert chat.flags({"mode": "plan", "model": "sonnet", "effort": "low"}) == ["--permission-mode", "plan", "--model", "sonnet", "--effort", "low"]
    assert chat.flags({"mode": "manual", "model": "", "effort": ""}) == ["--permission-mode", "manual"]
    assert chat.flags({"mode": "edits", "model": "", "effort": ""}) == ["--permission-mode", "acceptEdits"]
    assert chat.flags({"mode": "auto", "model": "", "effort": ""}) == ["--permission-mode", "auto"]


def test_cycling_wraps_around_both_ways():
    first, last = chat.MODES[0][0], chat.MODES[-1][0]
    assert chat.cycle(chat.MODES, last, 1) == first and chat.cycle(chat.MODES, first, -1) == last
    assert chat.cycle(chat.MODELS, "nonsense", 1) == chat.MODELS[0][0]  # an unknown choice starts the cycle over


def test_choices_are_remembered_and_a_bad_file_is_the_default(memory):
    assert chat.load() == chat.DEFAULT
    chat.save({"mode": "plan", "model": "sonnet", "effort": "low"})
    assert chat.load() == {"mode": "plan", "model": "sonnet", "effort": "low"}
    open(chat.PATH, "w").write("{not json")
    assert chat.load() == chat.DEFAULT


def test_a_saved_choice_it_does_not_offer_is_dropped(tmp_path, monkeypatch):  # review 2: shown as default, sent anyway
    monkeypatch.setattr(chat, "PATH", str(tmp_path / "nc.json"))
    (tmp_path / "nc.json").write_text('{"mode": "plan", "model": "opus-4", "effort": "ultra"}')
    assert chat.load() == {"mode": "plan", "model": "", "effort": ""}


def test_a_mode_it_does_not_offer_comes_back_as_itself_or_asking():  # review 2: dontAsk came back skipping permissions
    assert chat.flags({"mode": chat.from_transcript("dontAsk")})[-1] == "dontAsk"
    assert chat.from_transcript("someNewMode") == "manual"  # never more permissive than asking
    assert chat.from_transcript("") == "yolo"  # a transcript with no mode record: how he always ran them


def test_a_new_session_starts_with_the_choices(monkeypatch):
    calls = []
    monkeypatch.setattr(tmuxctl, "claude", lambda *args, cwd=None: (calls.append(args), (0, "backgrounded · cafe0001"))[1])
    assert tmuxctl.start("fix it", "/tmp", choice={"mode": "plan", "model": "opus", "effort": "max"}) == ("cafe0001", "")
    assert calls[-1] == ("--bg", "--permission-mode", "plan", "--model", "opus", "--effort", "max", "--", "fix it")
    tmuxctl.start("again", "/tmp")  # no choice: yolo, as always
    assert calls[-1] == ("--bg", "--dangerously-skip-permissions", "--", "again")
