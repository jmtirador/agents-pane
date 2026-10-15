"""What the list does when keys are pressed: which session goes live, what tmux is asked, what needs two presses."""

import json

import pytest
from helpers import row

from cockpit import store, tmuxctl


def gave_keys(cockpit, pane):
    """The keys sent to this pane (only while no dialog is open, which tmux checks: the re-review)."""
    return any(c[-1] == f"select-pane -t {pane}" for c in cockpit.tmux.named("if-shell"))


async def test_enter_shows_the_session_live_and_moves_the_keys_there(cockpit):
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("enter")
        await cockpit.settle(pilot)
        assert cockpit.tmux.slot_job == "work-aaa"  # the job id of the card the cursor starts on, swapped onto the right
        assert gave_keys(cockpit, cockpit.tmux.viewers[cockpit.tmux.slot_job])


async def test_the_list_marks_its_own_session_as_a_cockpit(cockpit):
    # the global Ctrl+] binding flips sides only in a marked session; a cockpit made by an older launcher had no mark
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        assert ("set-option", "-t", tmuxctl.OPTS, "@ap_cockpit", "1") in cockpit.tmux.named("set-option")
        assert tmuxctl.OPTS.startswith("=") and tmuxctl.OPTS.endswith(":")  # exactly this session, never a window name


async def test_a_dialog_takes_the_whole_window_and_gives_it_back(cockpit):
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("n")
        await cockpit.settle(pilot)
        assert cockpit.tmux.zoomed
        await pilot.press("escape")
        await cockpit.settle(pilot)
        assert not cockpit.tmux.zoomed


async def test_stop_needs_two_presses_of_capital_s(cockpit):
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("S")
        await cockpit.settle(pilot)
        assert cockpit.claude_calls == []
        await pilot.press("S")
        await cockpit.settle(pilot, 0.5)
        assert cockpit.claude_calls == [("stop", "work-aaa")]


async def test_typing_a_reply_into_the_list_cannot_stop_or_delete_anything(cockpit):
    # v4 (F3): with the keys still in the list, "yes sure" pressed s twice and stopped the session he meant to answer
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        for word in ("yes sure", "ss xx", "sounds good, fix it", "So Sam", "Xo Xo"):  # the v4 review: "So Sam" stopped it
            await pilot.press(*[{" ": "space", ",": "comma"}.get(ch, ch) for ch in word])
            await pilot.press("escape", "escape")  # close whatever a letter opened
            await cockpit.settle(pilot)
        assert cockpit.claude_calls == []


@pytest.mark.parametrize(("key", "verb"), [("S", "stop"), ("X", "remove")])
async def test_the_confirm_names_the_key_to_press_again(cockpit, key, verb):  # the drift audit: X said "Press R again"
    async with cockpit.app.run_test(size=(42, 28), notifications=True) as pilot:
        await cockpit.settle(pilot)
        await pilot.press(key)
        await cockpit.settle(pilot)
        said = [n.message for n in cockpit.app._notifications]
        assert any(m.startswith(f"Press {key} again to {verb} it.") for m in said), said


@pytest.mark.parametrize("key", ["q", "ctrl+c"])
async def test_q_and_ctrl_c_close_the_dashboard(cockpit, key):  # v4 (F4): nothing he tried closed it
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press(key)
        await cockpit.settle(pilot)
        assert ("switch-client", "-l") in cockpit.tmux.named("switch-client")  # back to where he came from, or out of tmux


async def test_watch_is_remembered(cockpit):
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("w")
        await cockpit.settle(pilot)
        with open(store.PATH) as f:
            assert json.load(f)["watched"] == ["work-aaaa"]


async def test_q_leaves_without_stopping_anything(cockpit):
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("q")
        await pilot.pause(0.2)
        assert cockpit.tmux.named("switch-client") or cockpit.tmux.named("detach-client")
        assert cockpit.claude_calls == []


async def test_t_opens_the_theme_menu_and_each_theme_shows_as_he_moves(cockpit):
    # Pepe (2026-10-08): "i like all 3 of these, they should be made choosable"
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        screen = cockpit.app.screen_stack[1]
        await pilot.press("t")
        await cockpit.settle(pilot)
        assert not cockpit.tmux.zoomed  # the list stays in view, so the theme shows live
        await pilot.press("down")
        await cockpit.settle(pilot)
        assert screen.palette.name == "mission" and cockpit.app.theme == "agents-mission"
        assert store.load()["theme"] == "neon"  # only looking, not kept yet
        await pilot.press("enter")
        await cockpit.settle(pilot)
        assert store.load()["theme"] == "mission"


async def test_esc_in_the_theme_menu_puts_the_old_theme_back(cockpit):
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        screen = cockpit.app.screen_stack[1]
        await pilot.press("t", "down", "down")
        await cockpit.settle(pilot)
        assert screen.palette.name == "tokyo"
        await pilot.press("escape")
        await cockpit.settle(pilot)
        assert screen.palette.name == "neon" and cockpit.app.theme == "agents-neon"
        assert store.load()["theme"] == "neon"


def many(working=12, idle=6, waiting=0):
    """Enough sessions to scroll, each with its own job id (row() takes the first 8 characters of the sid)."""
    return ([row(f"n{i:02d}-xxxxx", "needs", name=f"ask {i}") for i in range(waiting)]
            + [row(f"w{i:02d}-xxxxx", "working", name=f"task {i}") for i in range(working)]
            + [row(f"i{i:02d}-xxxxx", name=f"old {i}") for i in range(idle)])


async def test_a_scroll_stays_where_he_left_it(cockpit):
    # Pepe (2026-10-09): scrolling the list jumped back to the top, worst after showing the idle sessions
    cockpit.rows[:] = many(waiting=1)  # a waiting session pulses, so the list redraws on every spinner frame too
    async with cockpit.app.run_test(size=(42, 20)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("e")  # show the idle sessions too
        await cockpit.settle(pilot)
        cards = cockpit.app.screen.query_one("Cards")
        cards.scroll_to(y=12, animate=False)
        await pilot.pause(2.5)  # a couple of snapshot ticks and spinner frames
        assert round(cards.scroll_y) == 12
        await pilot.press("down")  # moving the cursor still brings its card into view
        await cockpit.settle(pilot)
        assert round(cards.scroll_y) < 12 and cockpit.app.screen.in_view()


async def test_g_on_the_card_it_is_already_on_brings_it_back(cockpit):  # the 3.1.0 review: g did nothing after scrolling away
    cockpit.rows[:] = many()
    async with cockpit.app.run_test(size=(42, 20)) as pilot:
        await cockpit.settle(pilot)
        cards = cockpit.app.screen.query_one("Cards")
        cards.scroll_to(y=20, animate=False)
        await cockpit.settle(pilot)
        await pilot.press("g")
        await cockpit.settle(pilot)
        assert round(cards.scroll_y) == 0


async def test_leaving_a_session_does_not_scroll(cockpit):  # the 3.1.0 review: Ctrl+Z on the Claude side jumped the list to the top
    cockpit.rows[:] = many()
    async with cockpit.app.run_test(size=(42, 20)) as pilot:
        await cockpit.settle(pilot)
        cards = cockpit.app.screen.query_one("Cards")
        cards.scroll_to(y=20, animate=False)
        await cockpit.settle(pilot)
        cockpit.app.screen.went_live(None)
        await cockpit.settle(pilot)
        assert round(cards.scroll_y) == 20


async def test_a_card_he_can_see_stays_in_view_when_it_moves(cockpit):  # the 3.1.0 review: a finished card slid off screen
    cockpit.rows[:] = many(idle=0)
    async with cockpit.app.run_test(size=(42, 20)) as pilot:
        await cockpit.settle(pilot)
        screen = cockpit.app.screen
        await pilot.press("G")  # the last working card, in view
        await cockpit.settle(pilot)
        assert screen.in_view()
        cockpit.rows[0] = row("w00-xxxxx", "done", name="task 0", finishedAt=cockpit.rows[0]["startedAt"] + 1000)
        cockpit.rows[-1] = row("w11-xxxxx", "done", name="task 11", finishedAt=cockpit.rows[-1]["startedAt"] + 2000)
        await cockpit.settle(pilot, 1.5)  # a snapshot moves both into the Done box below
        assert screen.selected == "w11-xxxxx" and screen.in_view()


# ---------------------------------------------------------------- v4: warm viewers and the click model (F2, F6; decision 0006)


async def test_the_cursor_card_is_what_the_right_side_shows(cockpit):  # F6
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("down")
        await cockpit.settle(pilot, 0.4)
        assert cockpit.tmux.slot_job == cockpit.app.screen.row(cockpit.app.screen.selected)["jobId"]


async def test_one_click_opens_a_session_and_gives_it_the_keys(cockpit):  # F2
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        screen = cockpit.app.screen
        line = screen.sids.index("done-bbbb")
        await pilot.click("#cards", offset=(10, line))
        await cockpit.settle(pilot, 0.4)
        assert screen.selected == "done-bbbb" and cockpit.tmux.slot_job == "done-bbb"
        assert gave_keys(cockpit, cockpit.tmux.viewers[cockpit.tmux.slot_job])


async def test_a_chat_it_cannot_show_gets_a_note_on_the_right(cockpit):  # F6
    cockpit.rows.append(row("tab-cccc", "working", name="old chat", jobId=None, tmux=None))
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        cockpit.app.screen.select("tab-cccc")
        await cockpit.settle(pilot, 0.4)
        notes = [c for c in cockpit.tmux.named("set-option") if "@ap_note" in c]
        assert cockpit.tmux.slot_job == "welcome" and notes and "terminal tab outside tmux" in notes[-1][-1]


async def test_a_session_he_typed_into_stays_warm(cockpit):  # F1: the viewer watches for Claude's own list, so it can't drift
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("enter")  # he types into work-aaa
        await cockpit.settle(pilot, 0.4)
        typed = cockpit.tmux.viewers["work-aaa"]
        await pilot.press("down")
        await cockpit.settle(pilot, 0.4)
        assert cockpit.tmux.slot_job == "done-bbb"
        assert not any(c[-1] == f"kill-pane -t {typed}" for c in cockpit.tmux.named("if-shell"))
        stamps = [c for c in cockpit.tmux.named("set-option") if c[-2] == "@ap_shown"]
        assert any(c[c.index("-t") + 1] == typed for c in stamps)  # warm for 15 minutes from when he left it, not from when it came in


async def test_passing_over_a_session_that_isnt_running_doesnt_start_it(cockpit):  # the v4 review: an attach wakes it
    cockpit.rows.append(row("stop-cccc", "stopped", name="parked work", alive=False))
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        cockpit.app.screen.action_quiet()  # the idle box, where stopped sessions are
        cockpit.app.screen.select("stop-cccc")
        await cockpit.settle(pilot, 0.4)
        notes = [c for c in cockpit.tmux.named("set-option") if "@ap_note" in c]
        assert "stop-ccc" not in cockpit.tmux.viewers and cockpit.tmux.slot_job == "welcome"
        assert notes and "Enter brings it back" in notes[-1][-1]


async def test_the_right_side_follows_when_the_card_on_it_goes_away(cockpit):  # F6, from the v4 review (X twice on the shown card)
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("down")
        await cockpit.settle(pilot, 0.4)
        assert cockpit.tmux.slot_job == "done-bbb"
        cockpit.rows[:] = [r for r in cockpit.rows if r["sid"] != "done-bbbb"]
        await cockpit.settle(pilot, 1.5)
        assert cockpit.app.screen.selected == "work-aaaa" and cockpit.tmux.slot_job == "work-aaa"
