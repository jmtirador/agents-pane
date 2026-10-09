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

from . import __version__, model, sessions, store, tmuxctl, view
from .dialogs import CSS as DIALOG_CSS
from .dialogs import Find, NewSession, Note, ThemePicker, TypeInto, help_lines
from .theme import PALETTES, install

IN_TMUX = bool(os.environ.get("TMUX"))
PAST = {"stop": "stopped", "remove": "removed"}

# ---------------------------------------------------------------- the list


class Cards(VerticalScroll, can_focus=False):
    pass


class CardText(Static):
    def on_click(self, event: events.Click):
        at = event.get_content_offset(self)
        if at:
            self.screen.clicked(at.y, event.chain)


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
        Binding("s", "twice('stop')", show=False),
        Binding("x", "twice('remove')", show=False),
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
        self.asked_for = "?"  # what the tmux thread last asked the live pane for; "?" until it first reads it
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
        today = date.today().isoformat()
        if today not in self.state["opens"]:
            self.state["opens"] = (self.state["opens"] + [today])[-60:]
            store.save(self.state)
        if IN_TMUX:
            self.background(tmuxctl.bind_keys)  # first, so Ctrl+] works as soon as possible
            self.background(self.restyle)
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
                self.background(self.read_live)
        except Exception as e:
            self.warning = f"can't read sessions: {e}"
            self.app.call_from_thread(self.redraw)
        finally:
            self.snapping.release()

    def read_live(self):
        """What the live pane shows. It runs on the tmux thread, after any switch the list queued, so its
        answer is never stale; a change it didn't ask for came from the welcome box, `yolo "prompt"` or Ctrl+Z."""
        want = tmuxctl.wanted() or None
        if want != self.asked_for:
            self.asked_for = want
            self.app.call_from_thread(self.went_live, want)

    def went_live(self, job):
        self.live = job
        selected = self.selected
        self.point_at(job)
        self.redraw()
        if self.selected != selected:  # leaving a session (no job) doesn't move the cursor, so it doesn't scroll
            self.reveal()
        self.background(self.publish)

    def point_at(self, job):
        """Select the card of a session that just went live, or as soon as its card appears."""
        row = self.row_by_job(job)
        if row:
            self.selected = row["sid"]
        elif job:
            self.pending = job

    def apply(self, rows):
        selected = self.selected  # a card that went away, or one that showed up late, moves the cursor: then reveal it
        was_at = self.card_sids().index(self.selected) if self.selected and self.selected in self.sids else None
        before = {r["sid"]: r["state"] for r in self.rows}
        for r in rows:
            if before.get(r["sid"], r["state"]) != r["state"]:
                self.changed(r, before[r["sid"]])
        self.rows = rows
        self.order = model.stable_order(rows, self.order, self.selected)
        if self.pending and (found := self.row_by_job(self.pending)):
            self.selected, self.pending = found["sid"], None
        if not self.row(self.selected):
            shown, _ = model.visible(rows, self.order, self.show_quiet, None)
            live_row = self.row_by_job(self.live)
            if was_at is not None and shown:  # it was removed: the card that slid into its place
                self.selected = shown[min(was_at, len(shown) - 1)]["sid"]
            else:
                self.selected = live_row["sid"] if live_row else shown[0]["sid"] if shown else None
        self.redraw()
        if self.selected != selected:
            self.reveal()
        if IN_TMUX:
            self.background(self.publish)

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
        if any(r["state"] in ("working", "needs") for r in self.rows):  # the working dot and the waiting text pulse
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
            if self.switch_timer:
                self.switch_timer.stop()
            self.switch_timer = self.set_timer(0.3, self.follow)
        self.reveal()  # also when it's the card it's on: g on the first card after scrolling away brings it back

    def follow(self):
        """The live pane follows the selection to any running background session."""
        row = self.row(self.selected)
        if IN_TMUX and row and row["jobId"] and row["alive"] and row["jobId"] != self.live:
            self.show(row["jobId"])

    def show(self, job):
        self.live = job
        self.point_at(job)
        self.background(self.ask_live, job)
        self.redraw()
        self.reveal()

    def ask_live(self, job):
        self.asked_for = job  # on the tmux thread, so read_live can't see the old answer after this
        tmuxctl.show_live(job)

    def clicked(self, line, chain):
        if not 0 <= line < len(self.sids):
            return
        if self.sids[line]:
            self.select(self.sids[line])
            if chain >= 2:
                self.action_open()
        elif line == len(self.sids) - 1 and (self.show_quiet or model.visible(self.rows, self.order, False, self.selected)[1]):
            self.action_quiet()  # the "N idle sessions hidden" line (not the last box's border when there's no such line)

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
        row = self.row(self.selected)
        if not row or not IN_TMUX:
            return
        if row["jobId"]:
            if row["jobId"] != self.live:
                self.show(row["jobId"])
            self.background(tmuxctl.focus, "live")
        elif row["alive"] and row["tmux"]:
            self.background(tmuxctl.jump, row["tmux"])
        elif row["alive"]:
            self.app.notify("It's a chat in a terminal tab outside tmux. Switch to that tab to use it.", title=row["name"])
        else:
            self.reopen(row["sid"], row["cwd"], row["name"])

    @work(thread=True, exit_on_error=False, group="reopen")
    def reopen(self, sid, cwd, name):
        self.app.call_from_thread(self.app.notify, "Bringing it back in the background…", title=name)
        job, why = tmuxctl.start(cwd=cwd, resume=sid)
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
        projects = glob.glob(os.path.join(sessions.HOME, "Projects", "*", ""))
        folders = sorted({sessions.tilde(r["cwd"]) for r in self.rows if r["cwd"]} | {sessions.tilde(p.rstrip("/")) for p in projects})
        self.dialog(NewSession(tmuxctl.launch_folder(), folders), self.create)

    @work(thread=True, exit_on_error=False, group="new")
    def create(self, picked):
        folder, name, prompt = picked
        self.app.call_from_thread(self.app.notify, prompt[:80], title="Starting a session…")
        job, why = tmuxctl.start(prompt, folder, name or None)
        self.app.call_from_thread(self.opened, job, why, name or "the new session")

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
        """His kill rule: over two weeks, open it on at least half the days with 2+ sessions running, or delete it."""
        started = date.fromisoformat(min(self.state["opens"]))
        since = max(started, date.today() - timedelta(days=13)).isoformat()
        busy = {d for d in sessions.busy_days(14) if d >= since}
        hit = busy & set(self.state["opens"])
        p = self.palette
        if date.today() - started < timedelta(days=14):
            verdict, color = f"Too early to judge: the two weeks end {(started + timedelta(days=14)):%a %-m/%-d}.", p.text2
        elif len(hit) < len(busy) / 2:
            verdict, color = "That's under half: your rule says delete it, not redesign it.", p.fail
        else:
            verdict, color = "Your kill rule isn't triggered.", p.done
        lines = [Text.assemble(("Busy days", p.text), (f" (2+ sessions) since {since}: ", p.text2), (str(len(busy)), p.work)),
                 Text.assemble(("Opened the cockpit on ", p.text2), (str(len(hit)), p.done), (" of them.", p.text2)),
                 Text(""), Text(verdict, style=f"bold {color}")]
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
            self.app.notify("It isn't running. Press x twice to remove it.", title=row["name"])
            return
        if self.armed == (what, row["sid"]) and time.time() - self.armed_at < 2:
            self.armed = None
            self.manage(what, row)
        else:
            self.armed, self.armed_at = (what, row["sid"]), time.time()
            self.app.notify(f"Press {what[0]} again to {what} it." + (" Its chat is kept." if what == "stop" else " This can't be undone."),
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
            if IN_TMUX and not self.live:
                self.background(tmuxctl.show_live, "")  # the welcome screen reads the saved theme when it starts



class CockpitApp(App):
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("ctrl+q", "leave", show=False, priority=True), Binding("ctrl+c", "noop", show=False, priority=True)]
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
        tmuxctl.detach() if IN_TMUX else self.exit()

    def action_noop(self):
        pass
