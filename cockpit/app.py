"""The cockpit's left pane: every Claude Code session as a colored card; the picked one runs live on the right."""

import glob
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from . import __version__, chat, model, search, sessions, store, tmuxctl, view
from .dialogs import CSS as DIALOG_CSS
from .dialogs import Dialog, Find, Note, ThemePicker, TypeInto, help_lines
from .theme import PALETTES, install
from .view import NEW_CHAT

IN_TMUX = bool(os.environ.get("TMUX"))
PAST = {"stop": "stopped", "remove": "removed"}
KEY = {"stop": "S", "remove": "X"}  # "remove" starts with R, which is rename (the drift audit)

# ---------------------------------------------------------------- the list


class Cards(VerticalScroll, can_focus=False):
    pass


class CardText(Static):
    def on_click(self, event: events.Click):
        at = event.get_content_offset(self)
        if at:
            self.screen.clicked(at.y, event.chain)


SETTLE_S = 0.12  # a run of arrow presses waits this long after the last one


def where_it_is(row):
    """Where a session the right side can't attach is, and what Enter does about it (F6)."""
    if row.get("desktop") and row["alive"]:
        return "It's open in the Claude app. Switch there to answer it."
    if row["jobId"] and row["state"] == "stopped":
        return "It's stopped. Enter brings it back."
    if row["jobId"]:
        return "It isn't running right now. Enter starts it again where it left off."
    if row["alive"] and row["tmux"]:
        return "It's open in another tmux window. Enter switches there."
    if row["alive"]:
        return "It's open in a terminal tab outside tmux. Switch to that tab to use it."
    return "It has ended. Enter brings it back in the background."


def note_and_keys(row):
    """For the peek: where the session is in a few words, and only the keys that do something for it there."""
    if row.get("desktop") and row["alive"]:
        return "It's open in the Claude app. Switch there to answer it.", []
    if row["jobId"] and row["state"] == "stopped":
        return "It's stopped.", [("enter", "bring it back"), ("r", "reply")]
    if row["jobId"]:
        return "It isn't running right now.", [("enter", "start it again here"), ("r", "reply")]
    if row["alive"] and row["tmux"]:
        return "It's open in another tmux window.", [("enter", "switch there")]
    if row["alive"]:
        return "It's open in a terminal tab outside tmux. Switch to that tab to use it.", []
    return "It has ended.", [("enter", "bring it back in the background")]


def peek_of(row, now):
    """What the right side shows for a session it can't attach (G1): the welcome viewer reads the reply itself."""
    asking, working = row["state"] in ("needs", "asks"), row["state"] in ("working", "quiet")
    note, keys = note_and_keys(row)
    return {"sid": row["sid"], "path": row.get("path") or "", "name": row["name"], "label": model.long_label(row, now),
            "state": row["state"], "where": f"in {sessions.tilde(row['cwd'])}" if row["cwd"] else "", "asked": row["lastPrompt"],
            "recap": row["away"], "question": row["question"] if asking else "", "options": row["options"] if asking else [],
            "doing": model.second_line(row) if working else "", "note": note, "keys": keys, "color": model.project_color(row["cwd"])}


class ListHeader(Static):
    """The list's first box: its name and the counts, in words (it replaces v2's tmux title line)."""


class FindLine(Static):
    def on_click(self):
        self.screen.action_find()


class ListScreen(Screen):
    BINDINGS = [
        Binding("down,j", "move(1)", show=False),
        Binding("up,k", "move(-1)", show=False),
        Binding("home,g", "edge(0)", show=False),
        Binding("end,G", "edge(-1)", show=False),
        Binding("enter", "open", show=False),
        Binding("tab", "to_live", show=False),
        # Ctrl+] reaches the list only before tmux's own binding is installed; F12 is what a click on the bar's flip key sends
        Binding("ctrl+right_square_bracket,f12", "flip", show=False),
        Binding("n", "new", show=False),
        Binding("r", "reply", show=False),
        Binding("R", "rename", show=False),
        Binding("slash", "find", show=False),
        Binding("w", "watch", show=False),
        # capitals, pressed twice: typing a reply while the keys are still here can't stop or delete a session (F3)
        Binding("S", "twice('stop')", show=False),
        Binding("X", "twice('remove')", show=False),
        Binding("e", "quiet", show=False),
        Binding("t", "look", show=False),
        Binding("u", "usage", show=False),
        Binding("question_mark", "help", show=False),
        Binding("q", "app.leave", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.state = store.load()
        self.palette = PALETTES.get(self.state["theme"], PALETTES["neon"])
        self.watched = set(self.state["watched"])
        self.watcher = sessions.Watcher()
        self.rows, self.order, self.sids = [], [], []
        self.selected = self.live = self.pending = None
        self.slot = "?"  # what the tmux thread last saw (or asked for) on the right side; "?" until it first reads it
        self.switches = self.landed = 0  # changes of the right side asked for, and run on the tmux thread (switch)
        self.warm = set()  # jobs with a viewer, as of the last read: switching to one is instant (G9)
        self.peeked = None  # the peek on the right side, as last written ({} the welcome screen, None a live session)
        self.attached = None  # is anyone looking? None until the first read (G10, G12)
        self.moved_at = 0.0
        self.ticks = 0
        self.show_quiet, self.frame, self.armed, self.armed_at = False, 0, None, 0.0
        self.dim = False  # while he's typing to Claude, the list steps back
        self.switch_timer, self.published, self.warning, self.checked, self.drawn = None, None, "", 0.0, None
        self.tmux_calls = ThreadPoolExecutor(max_workers=1)  # one at a time, in order: zoom toggles and switches can't cross
        self.snapping = threading.Lock()

    def compose(self) -> ComposeResult:
        yield ListHeader()
        with Cards():
            yield CardText(id="cards")
        yield FindLine()

    def on_mount(self):
        if IN_TMUX:
            self.background(tmuxctl.bind_keys)  # first, so Ctrl+] works as soon as possible
            self.background(self.restyle)
            search.update_elsewhere(wait=False)  # find's index catches up in its own process (G8)
        self.snap()
        self.set_interval(1.0, self.snap)
        self.set_interval(0.6, self.spin)

    def on_resize(self):
        self.draw_findline()
        self.redraw()

    def set_dim(self, dim):
        if dim != self.dim:
            self.dim = dim
            self.redraw()

    # ------------------------------------------------ data

    def background(self, fn, *args):
        """tmux and notification calls, off the UI thread and in the order they were asked for."""
        def run():
            try:
                fn(*args)
            except Exception as e:  # a failed call must never take the list down
                self.app.call_from_thread(self.app.notify, str(e), title="tmux call failed", severity="error")
        self.tmux_calls.submit(run)

    @work(thread=True, group="snap", exit_on_error=False)
    def snap(self):
        if not self.snapping.acquire(blocking=False):
            return  # the last one is still reading: skip a beat instead of piling up
        try:
            rows = self.watcher.snapshot()
            if time.time() - self.checked >= 30:
                self.checked = time.time()
                self.warning = sessions.registry_warning(rows)
                if IN_TMUX:
                    self.background(tmuxctl.ensure_alert)
            self.app.call_from_thread(self.apply, rows)
            if IN_TMUX:
                self.background(self.read_slot)
                self.ticks += 1
                if self.ticks % 5 == 0:
                    self.background(tmuxctl.tidy, {r["jobId"] for r in rows if r["jobId"]})
        except Exception as e:
            self.warning = f"can't read sessions: {e}"
            self.app.call_from_thread(self.redraw)
        finally:
            self.snapping.release()

    def read_slot(self):
        """What the right side shows, read on the tmux thread; a change the list didn't ask for came from the welcome
        screen (it started a session) or `yolo "prompt"`. A switch asked for while this look waited in the queue lands
        after it, so went_live drops the look when the list has asked for more switches than had landed (the reviews)."""
        asked = self.landed  # every switch counted here has run, on this same thread
        job, self.warm, attached = tmuxctl.look()
        if attached != self.attached or (attached and date.today().isoformat() not in self.state["opens"]):
            self.app.call_from_thread(self.looking, attached)  # also a new day with the same client still attached
        if job and job != self.slot:
            first = self.slot == "?"
            self.slot = job
            self.app.call_from_thread(self.went_live, None if job == "welcome" else job, first, asked)

    def looking(self, attached):
        """A client attached (or left). The pulse only runs while someone can see it (G10), and a day he opens it counts
        toward `u`, not a day the list process happened to start (G12)."""
        self.attached = attached
        today = date.today().isoformat()
        if attached and today not in self.state["opens"]:
            self.state["opens"] = (self.state["opens"] + [today])[-60:]
            store.save(self.state)

    def went_live(self, job, first=False, asked=None):
        if asked is not None and asked != self.switches:
            return  # n was handled while this look was out: the box it asked for lands next, and the next look agrees
        self.live = job
        if job:  # a session took the right side (the chat box became it, or `yolo "prompt"`): no peek or box is up (review 2)
            self.peeked = None
        selected = self.selected
        self.point_at(job)
        self.redraw()
        if self.selected != selected:  # leaving a session (no job) doesn't move the cursor, so it doesn't scroll
            self.reveal()
        self.background(self.publish)
        if first and not job:
            self.follow()  # the dashboard opened on the welcome screen: show the cursor's card (G7)

    def point_at(self, job):
        """Select the card of a session that just went live, or as soon as its card appears."""
        row = self.row_by_job(job)
        if row:
            self.selected = row["sid"]
        elif job:
            self.pending = job

    def apply(self, rows):
        selected = self.selected  # a card that went away, or one that showed up late, moves the cursor: then reveal it
        cards = [s for s in self.card_sids() if s != NEW_CHAT]
        was_at = cards.index(self.selected) if self.selected in cards else None
        before = {r["sid"]: r["state"] for r in self.rows}
        for r in rows:
            if before.get(r["sid"], r["state"]) != r["state"]:
                self.changed(r, before[r["sid"]])
        self.rows = rows
        self.order = model.stable_order(rows, self.order, self.selected)
        if self.pending and (found := self.row_by_job(self.pending)):
            self.selected, self.pending = found["sid"], None
        if self.selected != NEW_CHAT and not self.row(self.selected):
            shown, _ = model.visible(rows, self.order, self.show_quiet, None)
            live_row = self.row_by_job(self.live)
            if was_at is not None and shown:  # it was removed: the card that slid into its place, shown on the right too
                self.selected = shown[min(was_at, len(shown) - 1)]["sid"]
                if self.dim and IN_TMUX:  # he was typing in the one that went: the keys come back, not to its neighbour
                    self.background(tmuxctl.focus, "list")
                self.follow_soon()
            else:
                self.selected = live_row["sid"] if live_row else shown[0]["sid"] if shown else NEW_CHAT
        self.redraw()
        if self.selected != selected:
            self.reveal()
        if IN_TMUX:
            self.background(self.publish)
        self.keep_right()

    def keep_right(self):
        """The right side keeps up with the cursor's card between moves: a peek redraws when what it shows changed
        (review 2), a peeked session that started running gets its viewer, and no card at all is the welcome screen."""
        if not IN_TMUX or self.switch_timer or self.slot in ("?", "") or self.live:
            return
        row = self.row(self.selected)
        if not row:  # the new chat: written once on arrival, never again while he types in it
            if not (self.peeked or {}).get("compose"):
                self.follow()
        elif (row["jobId"] and row["alive"]) or peek_of(row, int(time.time() * 1000)) != self.peeked:
            self.follow()

    def changed(self, row, was):
        """A watched session that stops working gets a Mac notification; a session newly waiting for him gets a toast."""
        running = ("working", "quiet")
        if row["sid"] in self.watched and was in running and row["state"] not in running:
            verb = {"needs": "is waiting for you", "asks": "asked you something", "failed": "hit an error"}.get(row["state"], "finished")
            self.background(tmuxctl.notify, f"{row['name']} {verb}", model.second_line(row) or "")
            self.app.notify(model.second_line(row) or " ", title=f"{row['name']} {verb}")
            self.watched.discard(row["sid"])
            self.save()
        elif row["state"] == "needs":
            self.app.notify(model.second_line(row) or " ", title=f"{row['name']} is waiting for you", severity="warning")

    def publish(self):
        """The tmux side: how many sessions wait for him, for the bar on the Claude side and his other sessions."""
        waiting = model.counts(self.rows)["needs"]
        key = (self.palette.name, waiting)
        if key != self.published:
            self.published = key
            tmuxctl.publish(self.palette, waiting)

    def restyle(self):
        tmuxctl.style(self.palette)
        self.published = None
        self.publish()

    def save(self):
        self.state["watched"] = sorted(self.watched)
        store.save(self.state)

    def row(self, sid):
        return next((r for r in self.rows if r["sid"] == sid), None)

    def row_by_job(self, job):
        return next((r for r in self.rows if job and r["jobId"] == job), None)

    # ------------------------------------------------ drawing

    def redraw(self):
        # a card he can see stays in view when cards move (a band change, idle shown, new cards above it);
        # one he scrolled away from stays away, so a redraw never undoes his own scrolling (2026-10-09)
        keep = self.in_view()
        width = max(20, self.size.width - 1)
        text, self.sids = view.render(self.rows, self.order, self.palette, width, int(time.time() * 1000), self.frame,
                                      selected=self.selected, live=self.live, watched=self.watched, show_quiet=self.show_quiet,
                                      warning=self.warning, dim=self.dim)
        header = view.list_header(model.counts(self.rows), self.palette, width, self.dim)
        if (text, header) != self.drawn:  # most ticks change nothing on screen, and a repaint costs ~10 ms
            self.drawn = (text, header)
            self.query_one(CardText).update(text)
            self.query_one(ListHeader).update(header)
        if keep:
            self.call_after_refresh(self.keep_visible, False)

    def draw_findline(self):
        self.query_one(FindLine).update(view.find_line(self.palette, max(10, self.size.width - 1)))

    def reveal(self):
        """Bring the cursor's card into view with a little air around it, once the new lines are laid out: when he
        moves the cursor (even onto the card it's already on, like g on the first card) or it moves for him."""
        self.call_after_refresh(self.keep_visible)

    def card_lines(self):
        """The first and last line of the cursor's card, or None when it isn't drawn."""
        if self.selected not in self.sids:
            return None
        first = self.sids.index(self.selected)
        return first, first + self.sids.count(self.selected) - 1

    def in_view(self):
        lines = self.card_lines()
        if not lines:
            return False
        cards = self.query_one(Cards)
        top = round(cards.scroll_y)
        return top <= lines[0] and lines[1] < top + cards.size.height

    def keep_visible(self, air=True):
        lines = self.card_lines()
        if not lines:
            return
        first, last = lines
        cards = self.query_one(Cards)
        top, height = round(cards.scroll_y), cards.size.height
        pad = 1 if air else 0
        if first - pad < top:
            cards.scroll_to(y=max(0, first - 2 * pad), animate=False)
        elif last + pad >= top + height:
            cards.scroll_to(y=last + 1 + pad - height, animate=False)

    def spin(self):
        self.frame += 1
        now = int(time.time() * 1000)
        if self.attached is not False and any(model.pulses(r, now) for r in self.rows):  # nobody looking: no pulse (G10)
            self.redraw()

    # ------------------------------------------------ moving and opening

    def card_sids(self):
        return list(dict.fromkeys(s for s in self.sids if s))

    def select(self, sid):
        if not sid:
            return
        if sid != self.selected:
            self.selected = sid
            self.redraw()
            self.follow_soon()
        self.reveal()  # also when it's the card it's on: g on the first card after scrolling away brings it back

    def follow_soon(self):
        """One move switches the right side at once (G9); a run of moves, or one that would start a new viewer
        (144 MB for a card he's only passing; the v4.1 critic), waits for the cursor to settle."""
        now = time.time()
        burst, self.moved_at = now - self.moved_at < SETTLE_S, now
        if self.switch_timer:
            self.switch_timer.stop()
            self.switch_timer = None
        row = self.row(self.selected)
        starts_one = row and row["jobId"] and row["alive"] and row["jobId"] not in self.warm
        if row and not burst and not starts_one:
            self.follow()
        else:
            self.switch_timer = self.set_timer(SETTLE_S, self.follow)

    def follow(self):
        """The right side always shows the cursor's card (F6): its viewer, or a note when it can't be shown here.
        Only a running session gets a viewer: an attach would start a stopped or sleeping one just because the
        cursor passed it (the v4 review). Enter or a click starts it on purpose."""
        self.switch_timer = None
        row = self.row(self.selected)
        if not IN_TMUX:
            return
        if not row:  # the new chat row, or no card at all: the chat box (H1), never an old peek (review 1)
            if not (self.peeked or {}).get("compose"):
                self.new_chat()
            return
        if row["jobId"] and row["alive"]:
            if row["jobId"] != self.live:
                self.show(row["jobId"])
        else:
            self.peek(row)

    def show(self, job, fresh=False):
        self.live, self.peeked = job, None
        self.switch(self.put_on_right, job, fresh)
        self.point_at(job)  # after the switch, which drops an older pending
        self.redraw()
        self.reveal()

    def switch(self, fn, *args):
        """Queue a change of the right side, counted when asked and when it has run, so a look that ran before it
        can't undo it (read_slot). It replaces any session the cursor was waiting to follow (third review)."""
        self.switches += 1
        self.pending = None
        self.background(self.landing, fn, *args)

    def landing(self, fn, *args):
        try:
            fn(*args)
        finally:
            self.landed += 1

    def put_on_right(self, job, fresh):
        if self.slot == "welcome":
            try:
                store.write_peek({"blank": True})  # the peek it hides goes blank, so it can't come back showing the wrong session
            except OSError:
                pass
        self.slot = job  # on the tmux thread, so read_slot can't see the old answer after this
        tmuxctl.view(job, fresh=fresh)

    def peek(self, row):
        """A session the right side can't attach: what it is, what he asked, what it said (G1). Nothing starts."""
        self.live = None
        self.peeked = peek_of(row, int(time.time() * 1000))
        self.redraw()
        self.switch(self.put_peek, self.peeked)

    def new_chat(self):
        """The new chat on the right (H1): the welcome viewer's chat box, with the folders it can start in."""
        self.live = None
        projects = glob.glob(os.path.join(sessions.HOME, "Projects", "*", ""))
        folders = sorted(f for f in {r["cwd"] for r in self.rows if r["cwd"]} | {p.rstrip("/") for p in projects}
                         if os.path.isdir(f))  # a deleted worktree's sessions stay listed; it can't start there (review 2)
        self.peeked = {"compose": True, "folders": folders}
        self.redraw()
        self.switch(self.put_peek, self.peeked)

    def put_peek(self, peek):
        if peek.get("compose"):  # where `yolo` last ran, read now: the welcome viewer lives for days (the design critic)
            peek = {**peek, "folder": tmuxctl.launch_folder()}
        try:
            store.write_peek(peek)  # before the swap, so the welcome viewer is already redrawing when it comes into view
        except OSError:
            pass  # a full disk costs the peek, never the switch
        self.slot = "welcome"
        tmuxctl.view("welcome")

    def clicked(self, line, chain):
        if not 0 <= line < len(self.sids):
            return
        if self.sids[line]:  # one click opens it: on the right, with the keys (F2), like any chat app
            if self.switch_timer:  # cleared too, or action_open follows the old card first (the second review)
                self.switch_timer.stop()
                self.switch_timer = None
            self.selected = self.sids[line]
            self.redraw()
            self.reveal()
            row = self.row(self.selected)
            if (row and row["jobId"]) or self.selected == NEW_CHAT:
                self.action_open()
            else:
                self.follow()
        elif line == len(self.sids) - 1 and (self.show_quiet or model.visible(self.rows, self.order, False, self.selected)[1]):
            self.action_quiet()  # the "N idle sessions hidden" line (not the last box's border when there's no such line)

    def on_key(self, event: events.Key):
        if event.key not in ("S", "X"):
            self.armed = None  # S and X count only back to back, so "So Sam" typed here by mistake stops nothing (F3)

    def action_move(self, delta):
        sids = self.card_sids()
        if sids:
            at = sids.index(self.selected) if self.selected in sids else 0
            self.select(sids[max(0, min(len(sids) - 1, at + delta))])

    def action_edge(self, end):
        sids = self.card_sids()
        if sids:
            self.select(sids[end])

    def action_open(self):
        if self.switch_timer:  # a settle still pending from the last move must not swap a peek back over this (review 5),
            self.switch_timer.stop()  # but the right side still catches up with the card first (the second pass)
            self.switch_timer = None
            self.follow()
        row = self.row(self.selected)
        if self.selected == NEW_CHAT and IN_TMUX:
            self.peeked = None  # n, Enter or a click always puts a box up: the last one may have just become a session
            self.follow()  # that the list, reading the right side once a second, hasn't seen yet (review 2)
            self.background(tmuxctl.focus, "live")  # the keys into the chat box
            return
        if not row or not IN_TMUX:
            return
        if row["jobId"]:
            self.show(row["jobId"], fresh=True)  # fresh: a stopped or stuck viewer starts over; attach brings it back
            self.background(tmuxctl.focus, "live")
        elif row["alive"] and row["tmux"]:
            self.background(tmuxctl.jump, row["tmux"])
        elif row["alive"]:
            self.app.notify(where_it_is(row), title=row["name"])
        else:
            self.reopen(row["sid"], row["cwd"], row["name"], row["mode"])

    @work(thread=True, exit_on_error=False, group="reopen")
    def reopen(self, sid, cwd, name, mode=None):
        """Bring an ended session back in the background, in the mode it had (a plan session stays a plan session).
        mode None: a find result, which has no row, so it's read from its transcript (review 2)."""
        if mode is None:
            mode = sessions.mode_of(search.read_meta(sid).get("path"))
        self.app.call_from_thread(self.app.notify, "Bringing it back in the background…", title=name)
        job, why = tmuxctl.start(cwd=cwd, resume=sid, choice={**chat.DEFAULT, "mode": chat.from_transcript(mode)})
        self.app.call_from_thread(self.opened, job, why, name)

    def opened(self, job, why, name):
        if not job:
            self.app.notify(why, title=f"Couldn't open {name}", severity="error")
            return
        self.show(job)
        self.background(tmuxctl.focus, "live")

    def action_flip(self):
        """One press, one switch of sides, like tmux's Ctrl+] binding."""
        if IN_TMUX:
            self.background(tmuxctl.flip)

    def action_to_live(self):
        """Tab: the keys go to the Claude side, by its pane id; a toggle here undid itself on a double Tab (B2)."""
        if IN_TMUX:
            self.background(tmuxctl.focus, "live")

    # ------------------------------------------------ dialogs

    def dialog(self, screen, then, zoom=True):
        """Open a dialog with the whole window to itself (or in the list, zoom=False), and give the live pane its space back after."""
        if IN_TMUX:
            self.background(tmuxctl.focus, "list")
            if zoom:
                self.background(tmuxctl.zoom, True)
            self.background(tmuxctl.set_keys, self.palette, screen.KEYS)

        def done(result):
            if IN_TMUX:
                if zoom:
                    self.background(tmuxctl.zoom, False)
                self.background(tmuxctl.set_keys, self.palette)
            if result is not None:
                then(result)

        self.app.push_screen(screen, done)

    def action_new(self):
        """A new chat (H1): the cursor on the "+ new chat" row, its chat box on the right with the keys. Not select():
        its follow would put the box up once, and opening it puts it up again."""
        self.selected = NEW_CHAT
        self.redraw()
        self.reveal()
        self.action_open()

    def typed_row(self, verb):
        """The selected session, if text can be typed into it from here."""
        row = self.row(self.selected)
        if not row:
            return None
        if not row["jobId"]:
            self.app.notify(f"Only background sessions can {verb} from here. Enter opens this one.", title=row["name"])
            return None
        return row

    def action_reply(self):
        row = self.typed_row("get a reply")
        if not row:
            return
        if row["options"]:
            self.action_open()  # a question with choices is answered in its own chat
            return
        said = row["question"] or row["itSaid"] or model.second_line(row)
        self.dialog(TypeInto(row, "reply", said, f"type to {row['name']}, enter sends"), lambda text: self.send(row, text, "sent"))

    def action_rename(self):
        row = self.typed_row("be renamed")
        if row:
            self.dialog(TypeInto(row, "rename", "", "a short name", row["name"]), lambda name: self.send(row, f"/rename {name}", "renamed"))

    @work(thread=True, exit_on_error=False, group="send")
    def send(self, row, text, done):
        ok = tmuxctl.type_into(row["jobId"], text)
        self.app.call_from_thread(self.app.notify, text[:80] if ok else "Its chat didn't open in time. Try enter to open it.",
                                  title=f"{done}: {row['name']}" if ok else f"Couldn't reach {row['name']}", severity="information" if ok else "error")

    def action_find(self):
        self.dialog(Find(), self.found)

    def found(self, hit):
        row = self.row(hit["sid"])
        if row:
            self.select(row["sid"])
            self.action_open()
        else:
            self.reopen(hit["sid"], hit["cwd"], hit["name"])

    def action_help(self):
        self.dialog(Note("all keys", help_lines(self.palette, __version__)), lambda _: None)

    @work(thread=True, exit_on_error=False, group="usage")
    def action_usage(self):
        """How often he opens it: of the last two weeks' days with 2+ sessions running, how many he opened it on."""
        started = date.fromisoformat(min(self.state["opens"]))
        since = max(started, date.today() - timedelta(days=13)).isoformat()
        busy = {d for d in sessions.busy_days(14) if d >= since}
        hit = busy & set(self.state["opens"])
        p = self.palette
        lines = [Text.assemble(("Busy days", p.text), (f" (2+ sessions) since {since}: ", p.text2), (str(len(busy)), p.work)),
                 Text.assemble(("Opened the cockpit on ", p.text2), (str(len(hit)), p.done), (" of them.", p.text2))]
        self.app.call_from_thread(self.dialog, Note("how often you use this", lines), lambda _: None)

    # ------------------------------------------------ managing

    def action_watch(self):
        row = self.row(self.selected)
        if not row:
            return
        if row["sid"] in self.watched:
            self.watched.discard(row["sid"])
            self.app.notify("Not watching it anymore.", title=row["name"])
        else:
            self.watched.add(row["sid"])
            self.app.notify("You'll get a Mac notification when it finishes or waits for you.", title=f"Watching {row['name']}")
        self.save()
        self.redraw()

    def action_twice(self, what):
        """Stop and remove need the key twice within two seconds."""
        row = self.row(self.selected)
        if not row:
            return
        if not row["jobId"]:
            self.app.notify(f"Only background sessions can be {PAST[what]} from here.", title=row["name"])
            return
        if what == "stop" and not row["alive"]:
            self.app.notify("It isn't running. Press X twice to remove it.", title=row["name"])
            return
        if self.armed == (what, row["sid"]) and time.time() - self.armed_at < 2:
            self.armed = None
            self.manage(what, row)
        else:
            self.armed, self.armed_at = (what, row["sid"]), time.time()
            self.app.notify(f"Press {KEY[what]} again to {what} it." + (" Its chat is kept." if what == "stop" else " This can't be undone."),
                            title=row["name"], timeout=2)

    @work(thread=True, exit_on_error=False, group="manage")
    def manage(self, what, row):
        code, out = tmuxctl.claude("stop" if what == "stop" else "rm", row["jobId"])
        if code:
            why = out.splitlines()[0] if out else "no reason given"
            self.app.call_from_thread(self.app.notify, why, title=f"Couldn't {what} {row['name']}", severity="error")
        else:
            after = "Enter brings it back." if what == "stop" else "Gone for good."
            self.app.call_from_thread(self.app.notify, after, title=f"{PAST[what].capitalize()}: {row['name']}")

    def action_quiet(self):
        self.show_quiet = not self.show_quiet
        self.redraw()

    def action_look(self):
        """t: the theme menu. It stays in the list without zooming, so each theme he moves to shows live everywhere."""
        self.dialog(ThemePicker(self.palette.name, self.use_theme), lambda name: self.use_theme(name, keep=True), zoom=False)

    def use_theme(self, name, keep=False):
        """Recolor the list, the dialogs and the tmux frame; keep saves it and redraws the welcome screen in it too."""
        if name != self.palette.name:
            self.palette = PALETTES[name]
            self.app.theme = self.palette.theme_name
            self.draw_findline()
            self.redraw()
            if IN_TMUX:
                self.background(self.restyle)
                if not keep:  # restyling resets the bar; the menu is still open
                    self.background(tmuxctl.set_keys, self.palette, ThemePicker.KEYS)
        if keep and name != self.state["theme"]:
            self.state["theme"] = name
            store.save(self.state)



class CockpitApp(App):
    ENABLE_COMMAND_PALETTE = False
    NOTIFICATION_TIMEOUT = 3  # out of the way sooner (F2)
    # Ctrl+C closes the dashboard like q does (F4), or the dialog that's open; Claude's own Ctrl+C lives on the right side
    BINDINGS = [Binding("ctrl+q,ctrl+c", "close", show=False, priority=True)]
    # the terminal paints the background (decision 0002); cards and dialogs carry their own
    CSS = """
    Screen { background: ansi_default; }
    ListHeader { dock: top; height: 3; }
    Cards { background: ansi_default; scrollbar-size-vertical: 1; scrollbar-gutter: stable;
            scrollbar-color: $ap-line; scrollbar-color-hover: $ap-dim; scrollbar-background: ansi_default; }
    CardText { width: 100%; }
    FindLine { dock: bottom; height: 1; margin: 1 0 0 0; }
    FindLine:hover { text-style: underline; }
    /* the list's width, so it doesn't wrap; a thin rounded line like every other box, not the "done" green bar */
    Toast { background: $surface; width: 100%; max-width: 100%; padding: 0 1; border: round $ap-line; }
    ToastRack { dock: top; align: right top; }  /* at the bottom they covered the last cards and ate clicks (F2) */
    Toast.-information { border: round $ap-line; }
    Toast.-warning { border: round $warning; }
    Toast.-error { border: round $error; }
    Toast.-information .toast--title { color: $ap-key; }
    """ + DIALOG_CSS

    def __init__(self):
        super().__init__(ansi_color=True)  # lets "ansi_default" mean the terminal's own background

    def get_theme_variable_defaults(self):
        return PALETTES["neon"].variables()

    def on_app_blur(self):
        if isinstance(self.screen, ListScreen):
            self.screen.set_dim(True)

    def on_app_focus(self):
        if isinstance(self.screen, ListScreen):
            self.screen.set_dim(False)

    def on_mount(self):
        screen = ListScreen()
        install(self, screen.palette)
        self.push_screen(screen)

    def action_leave(self):
        """Close the dashboard; every session keeps running."""
        if IN_TMUX:
            self.screen_stack[1].background(tmuxctl.leave)
        else:
            self.exit()

    def action_close(self):
        if isinstance(self.screen, Dialog):
            self.screen.action_close()
        else:
            self.action_leave()
