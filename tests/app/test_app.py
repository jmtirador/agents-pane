"""What the list does when keys are pressed: which session goes live, what tmux is asked, what needs two presses."""

import json

from helpers import row

from cockpit import store, tmuxctl

LIVE = "%2"


async def test_enter_shows_the_session_live_and_moves_the_keys_there(cockpit):
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("enter")
        await cockpit.settle(pilot)
        wants = [c for c in cockpit.tmux.named("set-option") if "@ap_want" in c]
        assert wants and wants[-1][-1] == "work-aaa"  # the job id of the card the cursor starts on
        assert ("select-pane", "-t", LIVE) in cockpit.tmux.named("select-pane")


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


async def test_stop_needs_two_presses(cockpit):
    async with cockpit.app.run_test(size=(42, 28)) as pilot:
        await cockpit.settle(pilot)
        await pilot.press("s")
        await cockpit.settle(pilot)
        assert cockpit.claude_calls == []
        await pilot.press("s")
        await cockpit.settle(pilot, 0.5)
        assert cockpit.claude_calls == [("stop", "work-aaa")]


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
        assert cockpit.tmux.named("detach-client")
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
