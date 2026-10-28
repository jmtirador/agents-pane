"""What the list does when keys are pressed: which session goes live, what tmux is asked, what needs two presses."""

import json
import threading

import pytest
from helpers import row

from cockpit import search, store, tmuxctl


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
        await pilot.press("slash")
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


async def test_a_chat_it_cannot_show_gets_a_peek_saying_where_it_is(cockpit):  # F6, G1
    cockpit.rows.append(row("tab-cccc", "working", name="old chat", jobId=None, tmux=None))
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        cockpit.app.screen.select("tab-cccc")
        await cockpit.settle(pilot, 0.4)
        assert cockpit.tmux.slot_job == "welcome" and "terminal tab outside tmux" in store.read_peek()["note"]


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
        assert "stop-ccc" not in cockpit.tmux.viewers and cockpit.tmux.slot_job == "welcome"
        assert ["enter", "bring it back"] in store.read_peek()["keys"]


async def test_the_right_side_follows_when_the_card_on_it_goes_away(cockpit):  # F6, from the v4 review (X twice on the shown card)
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("down")
        await cockpit.settle(pilot, 0.4)
        assert cockpit.tmux.slot_job == "done-bbb"
        cockpit.rows[:] = [r for r in cockpit.rows if r["sid"] != "done-bbbb"]
        await cockpit.settle(pilot, 1.5)
        assert cockpit.app.screen.selected == "work-aaaa" and cockpit.tmux.slot_job == "work-aaa"


# ---------------------------------------------------------------- v4.1: a peek for every session it can't attach (G1, G7, G9, G10, G12)


def sleeping():
    return row("old-dddd", "idle", name="old work", alive=False, lastPrompt="fix the export", away="Fixed the export.",
               itSaid="Fixed.", lastChange=row("x")["lastChange"] - 3 * 86400_000)


async def test_resting_on_a_session_that_isnt_running_shows_its_peek(cockpit):  # G1: 17 of his 20 showed only the logo
    cockpit.rows.append(sleeping())
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        cockpit.app.screen.action_quiet()
        cockpit.app.screen.select("old-dddd")
        await cockpit.settle(pilot, 0.4)
        peek = store.read_peek()
        assert (peek["name"], peek["asked"], peek["recap"]) == ("old work", "fix the export", "Fixed the export.")
        assert cockpit.tmux.slot_job == "welcome" and "old-ddd" not in cockpit.tmux.viewers  # nothing started or attached


async def test_a_running_session_blanks_the_peek_behind_it(cockpit):  # G1: the hidden peek never shows the wrong session later
    cockpit.rows.append(sleeping())
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        cockpit.app.screen.action_quiet()
        cockpit.app.screen.select("old-dddd")
        await cockpit.settle(pilot, 0.4)
        cockpit.app.screen.select("work-aaaa")
        await cockpit.settle(pilot, 0.4)
        assert cockpit.tmux.slot_job == "work-aaa" and store.read_peek() == {"blank": True}


async def test_the_right_side_follows_the_cursor_from_the_first_screen(cockpit):  # G7: the logo until a key was pressed
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        assert cockpit.tmux.slot_job == cockpit.app.screen.row(cockpit.app.screen.selected)["jobId"]


async def test_one_arrow_press_switches_at_once(cockpit):  # G9: a 120 ms wait on every press
    cockpit.rows[:] = [row("work-aaaa", "working", name="one"), row("tab-cccc", "working", name="two", jobId=None, tmux=None)]
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        await pilot.press("down")
        await cockpit.settle(pilot, 0.03)
        assert cockpit.tmux.slot_job == "welcome" and store.read_peek()["name"] == "two"


async def test_nothing_pulses_while_no_one_is_looking(cockpit):  # G10: ~6% of a core for a screen nobody saw
    cockpit.tmux.attached = 0
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        screen = cockpit.app.screen
        drawn = []
        screen.redraw = lambda: drawn.append(1)
        screen.spin()
        assert drawn == []
        cockpit.tmux.attached = 1
        await cockpit.settle(pilot, 1.5)
        screen.spin()
        assert drawn


async def test_a_day_counts_when_he_opens_it_not_when_the_list_starts(cockpit):  # G12
    cockpit.tmux.attached = 0
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        assert store.load()["opens"] == []
        cockpit.tmux.attached = 1
        await cockpit.settle(pilot, 1.5)
        assert len(store.load()["opens"]) == 1


async def test_a_peek_offers_only_the_keys_that_work_for_it(cockpit):  # G1: "enter open it here" on a chat in the Claude app
    cockpit.rows[:] = [row("old-dddd", "idle", name="old work", alive=False),
                       row("app-eeee", "working", name="study plan", jobId=None, desktop=True, detail="writing the plan")]
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        screen = cockpit.app.screen
        screen.action_quiet()
        screen.select("old-dddd")
        await cockpit.settle(pilot, 0.4)
        assert [k for k, _ in store.read_peek()["keys"]] == ["enter", "r"]
        screen.select("app-eeee")
        await cockpit.settle(pilot, 0.4)
        peek = store.read_peek()
        assert peek["keys"] == [] and "Claude app" in peek["note"] and peek["doing"] == "writing the plan"


# ---------------------------------------------------------------- the v4.1 review


async def test_with_every_card_idle_the_right_side_is_the_new_chat(cockpit):  # review 1: yesterday's peek stayed
    cockpit.rows[:] = [row("old-dddd", "idle", name="old work", alive=False)]
    store.write_peek({"name": "yesterday's session", "keys": []})
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        assert store.read_peek()["compose"] and cockpit.tmux.slot_job == "welcome"


async def test_a_peek_follows_its_session_while_he_rests_on_it(cockpit):  # review 2: the header froze
    cockpit.rows[:] = [row("tab-cccc", "working", name="chat", jobId=None, tmux=None, detail="drafting")]
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        assert store.read_peek()["state"] == "working"
        cockpit.rows[0] = row("tab-cccc", "needs", name="chat", jobId=None, tmux=None, question="Send it?")
        await cockpit.settle(pilot, 1.5)
        peek = store.read_peek()
        assert (peek["state"], peek["question"]) == ("needs", "Send it?")


async def test_enter_right_after_moving_is_not_undone_by_the_settle(cockpit):  # review 5
    cockpit.rows[:] = [row("work-aaaa", "working", name="one"), row("stop-cccc", "stopped", name="two", alive=False)]
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        screen = cockpit.app.screen
        screen.action_quiet()
        screen.moved_at = __import__("time").time()  # as if he just pressed an arrow: the move waits to settle
        screen.select("stop-cccc")
        screen.action_open()  # Enter at once
        await cockpit.settle(pilot, 0.5)
        assert cockpit.tmux.slot_job == "stop-ccc" and screen.live == "stop-ccc"


async def test_a_day_counts_when_he_has_it_open_across_midnight(cockpit, monkeypatch):  # review 7
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        store.save({**store.load(), "opens": []})
        cockpit.app.screen.state["opens"] = []  # a new day, the same attached client
        await cockpit.settle(pilot, 1.5)
        assert len(cockpit.app.screen.state["opens"]) == 1


async def test_enter_right_after_moving_onto_a_chat_elsewhere_still_shows_its_peek(cockpit):  # second pass
    cockpit.rows[:] = [row("work-aaaa", "working", name="one"), row("tmx-cccc", "working", name="two", jobId=None, tmux="%9")]
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        screen = cockpit.app.screen
        screen.select("work-aaaa")
        await cockpit.settle(pilot, 0.5)
        assert cockpit.tmux.slot_job == "work-aaa"
        screen.moved_at = __import__("time").time()
        screen.select("tmx-cccc")
        screen.action_open()  # Enter before the move settled: it switches to that window, and the right side follows
        await cockpit.settle(pilot, 0.5)
        assert cockpit.tmux.slot_job == "welcome" and store.read_peek()["name"] == "two"


# ---------------------------------------------------------------- v4.2: a new chat feels like a chat (H1-H3)


async def test_n_puts_the_new_chat_on_the_right_with_the_keys(cockpit):  # H1: it was a three-box form
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        await pilot.press("n")
        await cockpit.settle(pilot, 0.4)
        screen = cockpit.app.screen
        peek = store.read_peek()
        assert screen.selected == "new" and peek["compose"] and peek["folder"] == tmuxctl.launch_folder()
        assert cockpit.tmux.slot_job == "welcome" and gave_keys(cockpit, cockpit.tmux.viewers["welcome"])


async def test_the_new_chat_stays_while_he_types(cockpit):  # the design critic: the list replaced it within a second
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        await pilot.press("n")
        await cockpit.settle(pilot, 2.5)  # snapshots and keep_right run meanwhile
        assert cockpit.app.screen.selected == "new" and store.read_peek()["compose"] and cockpit.tmux.slot_job == "welcome"


async def test_the_new_chat_row_sits_above_the_first_card(cockpit):
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        screen = cockpit.app.screen
        first = screen.card_sids()[1]
        screen.select(first)
        await pilot.press("up")
        assert screen.selected == "new"
        await pilot.press("down")
        assert screen.selected == first


async def test_with_no_sessions_the_right_side_is_a_new_chat(cockpit):
    cockpit.rows[:] = []
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        assert cockpit.app.screen.selected == "new" and store.read_peek()["compose"]


async def test_n_after_starting_a_chat_brings_the_box_back(cockpit):  # review 2: the new session kept the right side
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        await pilot.press("n")
        await cockpit.settle(pilot, 0.4)
        # Enter in the box: the welcome viewer becomes the new session's viewer, in the same pane
        cockpit.rows.append(row("cafe0001-x", "working", name="write the readme"))
        cockpit.tmux.viewers = {"cafe0001": cockpit.tmux.viewers.pop("welcome")}
        cockpit.tmux.slot_job = "cafe0001"
        await cockpit.settle(pilot, 1.5)
        assert cockpit.app.screen.live == "cafe0001"
        await pilot.press("n")
        await cockpit.settle(pilot, 0.4)
        assert cockpit.tmux.slot_job == "welcome" and store.read_peek()["compose"]


async def test_n_before_the_list_has_seen_the_new_session_still_brings_the_box_back(cockpit):  # review 2, in real tmux:
    async with cockpit.app.run_test(size=(42, 28)) as pilot:  # the list reads the right side once a second
        await cockpit.settle(pilot, 1.5)
        await pilot.press("n")
        await cockpit.settle(pilot, 0.4)
        cockpit.tmux.viewers = {"cafe0001": cockpit.tmux.viewers.pop("welcome")}  # the box became the session's viewer
        cockpit.tmux.slot_job = "cafe0001"
        await pilot.press("n")  # at once, before the list's next look
        await cockpit.settle(pilot, 0.2)
        assert cockpit.tmux.slot_job == "welcome"


async def test_a_look_that_saw_the_session_before_n_does_not_undo_the_box(cockpit):  # second review: the list and the
    async with cockpit.app.run_test(size=(42, 28)) as pilot:  # right side disagreed until the next move
        await cockpit.settle(pilot, 1.5)
        await pilot.press("n")
        await cockpit.settle(pilot, 0.4)
        cockpit.rows.append(row("cafe0001-x", "working", name="write the readme"))
        cockpit.tmux.viewers = {"cafe0001": cockpit.tmux.viewers.pop("welcome")}
        cockpit.tmux.slot_job = "cafe0001"
        screen = cockpit.app.screen
        asked = screen.switches  # a look starts, and sees the new session...
        await pilot.press("n")  # ...while n is handled on the UI thread
        await cockpit.settle(pilot, 0.2)
        screen.went_live("cafe0001", False, asked)  # then its answer lands
        await cockpit.settle(pilot, 0.2)
        assert cockpit.tmux.slot_job == "welcome" and screen.live is None and screen.selected == "new"


async def test_a_look_queued_before_n_but_run_after_it_does_not_undo_the_box(cockpit):  # third review: the count was
    async with cockpit.app.run_test(size=(42, 28)) as pilot:  # read when the look ran, not when it was queued
        await cockpit.settle(pilot, 1.5)
        await pilot.press("n")
        await cockpit.settle(pilot, 0.4)
        cockpit.rows.append(row("cafe0001-x", "working", name="write the readme"))
        await cockpit.settle(pilot, 1.2)
        screen = cockpit.app.screen
        busy = threading.Event()
        screen.tmux_calls.submit(busy.wait)  # the tmux thread is still on an earlier call
        cockpit.tmux.viewers = {"cafe0001": cockpit.tmux.viewers.pop("welcome")}  # the box became the session's viewer
        cockpit.tmux.slot_job = "cafe0001"
        screen.background(screen.read_slot)  # a look, queued behind that call
        await pilot.press("n")  # its switch queued behind the look
        busy.set()
        await cockpit.settle(pilot, 2.5)  # and two more looks
        assert cockpit.tmux.slot_job == "welcome" and screen.live is None and screen.selected == "new"


async def test_n_then_the_new_sessions_card_appearing_keeps_the_box(cockpit):  # third review: an old pending moved the
    async with cockpit.app.run_test(size=(42, 28)) as pilot:  # cursor to it, and the box was swapped away
        await cockpit.settle(pilot, 1.5)
        await pilot.press("n")
        await cockpit.settle(pilot, 0.4)
        cockpit.tmux.viewers = {"cafe0001": cockpit.tmux.viewers.pop("welcome")}  # before its card exists
        cockpit.tmux.slot_job = "cafe0001"
        await cockpit.settle(pilot, 1.5)
        await pilot.press("n")
        await cockpit.settle(pilot, 0.4)
        cockpit.rows.append(row("cafe0001-x", "working", name="write the readme"))  # the card shows up a tick later
        await cockpit.settle(pilot, 1.5)
        assert cockpit.app.screen.selected == "new" and cockpit.tmux.slot_job == "welcome"


async def test_the_new_chat_offers_only_folders_that_exist(cockpit, tmp_path):  # review 2: a deleted worktree started in ~
    gone = str(tmp_path / "deleted-worktree")
    cockpit.rows[:] = [row("gone-eeee", "idle", cwd=gone), row("here-ffff", "idle", cwd=str(tmp_path))]
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        await pilot.press("n")
        await cockpit.settle(pilot, 0.4)
        folders = store.read_peek()["folders"]
        assert str(tmp_path) in folders and gone not in folders


async def test_a_session_found_with_find_comes_back_in_its_mode(cockpit, tmp_path, monkeypatch):  # review 2: it came back as yolo
    path = tmp_path / "old.jsonl"
    path.write_text('{"type": "permission-mode", "permissionMode": "plan"}\n')
    monkeypatch.setattr(search, "read_meta", lambda sid: {"path": str(path), "cwd": str(tmp_path)})
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        cockpit.app.screen.found({"sid": "old-gggg", "cwd": str(tmp_path), "name": "old plan"})
        await cockpit.settle(pilot, 0.5)
        assert cockpit.started[-1]["resume"] == "old-gggg" and cockpit.started[-1]["choice"]["mode"] == "plan"


async def test_bringing_a_session_back_keeps_its_mode(cockpit):  # the design critic: plan sessions came back as yolo
    cockpit.rows[:] = [row("old-dddd", "idle", name="old plan", jobId=None, alive=False, mode="plan")]
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot, 1.5)
        screen = cockpit.app.screen
        screen.action_quiet()
        screen.select("old-dddd")
        screen.action_open()
        await cockpit.settle(pilot, 0.5)
        assert cockpit.started[-1]["resume"] == "old-dddd" and cockpit.started[-1]["choice"]["mode"] == "plan"
