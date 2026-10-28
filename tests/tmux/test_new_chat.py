"""v4.2: the new chat, end to end on a private tmux server with a fake claude (problems H1-H3)."""

import json
import time

import pytest

pytestmark = pytest.mark.tmux


def test_n_types_a_chat_on_the_right_and_enter_starts_it_there_in_its_mode(rig):
    rig.add_session(prompt="an older job", status="busy")
    rig.launch()
    rig.attach()
    rig.wait_for(lambda: "an older job" in rig.screen("list") and rig.active() == "list", "the list with the keys")
    rig.press("n")
    rig.wait_for(lambda: "Ask anything" in rig.screen("live") and rig.active() == "live", "the chat box, with the keys")
    time.sleep(0.5)  # past the double-Tab guard: this Tab is his, and changes the mode
    rig.press("-l", "write the readme")
    rig.press("Tab")
    rig.wait_for(lambda: "Auto ·" in rig.screen("live"), "the mode line saying Auto")
    rig.press("Enter")
    rig.wait_for(lambda: "FAKE CLAUDE attached to cafe0001" in rig.screen("live"), "the new session on the right")
    started = next(line for line in rig.log("calls.log").splitlines() if "--bg" in line)
    assert "--permission-mode auto" in started and started.endswith("-- write the readme")
    assert rig.active() == "live"  # he keeps typing into the chat he just started
    assert json.loads((rig.config / "agents-pane" / "new-chat.json").read_text())["mode"] == "auto"  # remembered
    rig.press("C-]")
    rig.wait_for(lambda: rig.active() == "list", "the keys back in the list")
    rig.press("n")  # review 2: the session it just started kept the right side, and took his typing
    rig.wait_for(lambda: "Ask anything" in rig.screen("live") and rig.active() == "live", "a fresh chat box, with the keys")


def test_esc_in_the_chat_box_gives_the_keys_back_and_keeps_the_draft(rig):
    rig.launch()
    rig.attach()
    rig.wait_for(lambda: "Ask anything" in rig.screen("live"), "no sessions: the new chat on the right")
    rig.press("n")
    rig.wait_for(lambda: rig.active() == "live", "the keys in the box")
    rig.press("-l", "half a thought")
    rig.press("Escape")
    rig.wait_for(lambda: rig.active() == "list", "the keys back in the list")
    assert "half a thought" in rig.screen("live")
    assert "--bg" not in rig.log("calls.log")
