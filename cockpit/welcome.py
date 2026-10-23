"""The right side when no running session is on it: a peek at the cursor's session, or the welcome screen.

The peek (problems G1) is for a session it can't attach (its process stopped, a chat elsewhere, an ended one): what it
is, what he asked, its last reply and its recap, read from files, so nothing starts. The list writes what to show in a
small file (store.write_peek) and this checks it with a stat 20 times a second. The welcome screen (the wordmark, a box
that starts a new session here, a tip) shows only when there's no card to peek at.

It sits on the terminal's own background (decision 0002). The wordmark keeps its gradient on purpose:
Pepe called it "awesome" (2026-10-07), and it's the brand, not a state color.
"""

import os
import time
from datetime import date

from rich.markdown import Markdown
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Input, Static

from . import sessions, store, tmuxctl
from .theme import PALETTES, current, install, mix

MARK = [  # ANSI Shadow, with a rounded S so it doesn't read as a 5
    " █████╗  ██████╗ ███████╗███╗   ██╗████████╗ ██████╗",
    "██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝██╔════╝",
    "███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ╚█████╗ ",
    "██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║    ╚═══██╗",
    "██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ██████╔╝",
    "╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═════╝ ",
]


TIPS = [  # each fits on one line of the 64-column box
    "? in the list shows every key.",
    "t in the list changes the theme.",
    "w on a card sends a Mac notification when it finishes.",
    "/ finds an old session by what it was about.",
    "r replies to a session without leaving the list.",
]


TAG = "Pick a session on the left, or start a new one here."
TYPING_S = 1.0  # a key this soon after another is typing, never a command (the v4.1 runtime tester)
ALONE_S = 0.3  # and an offered key acts only if nothing follows it this soon
BACK = ("escape", "tab", "up", "down", "left", "right", "pageup", "pagedown")


def wordmark(p, width):
    """AGENTS in block letters, fading from the theme's own color to its key color; a small mark when the pane is narrow."""
    if width < len(MARK[0]) + 4:
        return Text("agents", style=f"bold {p.key}")
    out = Text()
    for y, line in enumerate(MARK):
        for x, ch in enumerate(line):
            color = mix(p.brand, p.key, x / (len(line) - 1))
            out.append(ch, f"bold {color}" if ch == "█" else mix(color, p.base, 0.5))
        if y < len(MARK) - 1:
            out.append("\n")
    return out


def keys_line(p):
    """The two keys that matter here, named the same way as in the bar."""
    return Text.assemble(("enter", p.key), (" starts it here     ", p.text3), (tmuxctl.CLAUDE_KEYS[0][0], p.key), (f" {tmuxctl.CLAUDE_KEYS[0][1]}", p.text3))


def mtime(path):
    try:
        return os.stat(path).st_mtime_ns
    except (OSError, TypeError):
        return None


def peek_keys(p, peek):
    """Where the session is, then only the keys that do something for it (the list sends them; Welcome.on_key)."""
    keys = Text("   ").join(Text.assemble((key, p.key), (" " + what, p.text3)) for key, what in peek.get("keys") or [])
    return Text("\n").join([Text(peek.get("note", ""), style=p.text2), keys]) if keys else Text(peek.get("note", ""), style=p.text2)


def tip(day=None):
    """One tip a day, so the features get found without a manual."""
    return TIPS[(day or date.today()).toordinal() % len(TIPS)]


class Mark(Widget):
    """Redrawn on every refresh, so it switches between big and small as the pane is resized."""

    def render(self):
        return wordmark(self.app.palette, self.app.size.width)


class Peek(Vertical):
    """Takes the keys while a peek shows: Textual hands them to the hidden box otherwise (Welcome.on_key)."""

    can_focus = True


class Welcome(App):
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("ctrl+q,ctrl+c", "noop", show=False, priority=True)]  # quitting would close the cockpit's right side
    CSS = """
    Screen { background: ansi_default; align: center middle; }
    #all { width: 64; max-width: 100%; height: auto; }
    Mark { width: 100%; height: auto; margin: 0 0 1 0; text-align: center; }
    #tag { width: 100%; text-align: center; color: $ap-text2; margin: 0 0 1 0; }
    #box { height: auto; padding: 0 1; background: ansi_default; border: round $ap-line; border-title-color: $ap-key; }
    #box Input { border: none; height: 1; padding: 0 1; margin: 0 0 0 0; background: $panel; }
    #box Input > .input--placeholder { color: $ap-text2; }
    #where { color: $ap-dim; text-wrap: nowrap; text-overflow: ellipsis; }
    #keys { width: 100%; text-align: center; margin: 1 0 0 0; }
    #tip { width: 100%; text-align: center; color: $ap-dim; margin: 1 0 0 0; }
    #peek { width: 100%; height: 100%; padding: 1 2 0 2; display: none; }
    #peek Static { width: 100%; height: auto; }
    #p-where { color: $ap-dim; margin: 0 0 1 0; }
    #p-question { margin: 0 0 1 0; }
    #p-doing { margin: 0 0 1 0; }
    .p-label { color: $ap-key; }
    #p-asked { color: $ap-text2; margin: 0 0 1 0; }
    #peek #p-reply { height: 1fr; overflow: hidden hidden; }  /* beats "#peek Static": a long reply is cut, the keys stay */
    #p-recap { color: $ap-text2; margin: 1 0 0 0; }
    #p-keys { margin: 1 0 0 0; }
    """

    def __init__(self):
        super().__init__(ansi_color=True)  # lets "ansi_default" mean the terminal's own background
        self.palette = current()
        self.folder = tmuxctl.launch_folder()
        self.peek, self.seen = {}, {}  # what's shown, and the files' times when it was read
        self.last_key, self.pending = 0.0, None

    def get_theme_variable_defaults(self):
        return PALETTES["neon"].variables()

    def compose(self) -> ComposeResult:
        p = self.palette
        with Vertical(id="all"):
            yield Mark()
            yield Static(TAG, id="tag")
            with Vertical(id="box") as box:
                box.border_title = "new session"
                yield Input(placeholder="what should it do?")
                yield Static(id="where")
            yield Static(keys_line(p), id="keys")
            yield Static(f"Tip: {tip()}", id="tip")
        with Peek(id="peek"):
            yield Static(id="p-head")
            yield Static(id="p-where")
            yield Static(id="p-question")
            yield Static(id="p-doing")
            yield Static("You asked", classes="p-label")
            yield Static(id="p-asked")
            yield Static("It said", classes="p-label")
            yield Static(id="p-reply")
            yield Static(id="p-recap")
            yield Static(id="p-keys")

    def on_mount(self):
        install(self, self.palette)
        self.where(f"in {sessions.tilde(self.folder)}")
        self.query_one(Input).focus()
        self.watch()  # a fresh viewer shows the current peek at once, with no signal to wait for (the v4.1 critic)
        self.set_interval(0.05, self.watch)

    def watch(self):
        """The peek file, the peeked transcript and the theme, a stat each, 20 times a second (the note's 0.5 s tmux poll
        cost ~1% of a core; G10). Each is read again only when its file changed."""
        changed = {name: t for name, t in (("peek", mtime(store.peek_path())), ("state", mtime(store.PATH)),
                                           ("reply", mtime(self.peek.get("path")))) if t != self.seen.get(name)}
        self.seen.update(changed)
        themed = "state" in changed and current().name != self.palette.name  # he picked another theme in the list
        if themed:
            self.palette = p = current()
            self.theme = p.theme_name
            self.query_one(Mark).refresh()
            self.query_one("#keys", Static).update(keys_line(p))
        if themed or "peek" in changed:
            self.show(store.read_peek() if "peek" in changed else self.peek)
        elif "reply" in changed and self.peeking:
            self.show_reply()

    @property
    def peeking(self):
        return bool(self.peek) and not self.peek.get("blank")

    def show(self, peek):
        """{} is the welcome screen, {"blank": True} nothing (a running session is in front), anything else a peek."""
        self.peek = peek
        self.seen["reply"] = mtime(peek.get("path"))
        self.query_one("#all").display = not peek
        self.query_one("#peek").display = self.peeking
        if not peek:
            self.query_one(Input).focus()
        if not self.peeking:
            return
        self.query_one(Peek).focus()  # the hidden box mustn't keep the keys: they go back to the list (on_key)
        p = self.palette
        color = peek.get("color") or p.text
        self.query_one("#p-head", Static).update(Text.assemble((peek.get("name", ""), f"bold {color}"), ("   " + peek.get("label", ""), p.text3)))
        self.query_one("#p-where", Static).update(peek.get("where", ""))
        question = peek.get("question", "")
        if question:
            choices = "   ".join(f"{n} {label}" for n, label in enumerate(peek.get("options") or [], 1))
            question = Text.assemble((question, p.needs), ("\n" + choices if choices else "", p.needs))
        self.query_one("#p-question", Static).update(question)
        self.query_one("#p-question").display = bool(question)
        doing = peek.get("doing", "")
        self.query_one("#p-doing", Static).update(Text.assemble(("Now  ", p.key), (doing, p.work)) if doing else "")
        self.query_one("#p-doing").display = bool(doing)
        self.query_one("#p-asked", Static).update(sessions.one_line(peek.get("asked", ""), 300) or "(nothing typed)")
        recap = peek.get("recap", "")
        self.query_one("#p-recap", Static).update(Text.assemble(("Recap  ", p.key), (recap, p.text2)) if recap else "")
        self.query_one("#p-recap").display = bool(recap)
        self.query_one("#p-keys", Static).update(peek_keys(p, peek))
        self.show_reply()

    def show_reply(self):
        reply = sessions.last_reply(self.peek.get("path"))
        shown = Markdown(reply, code_theme="ansi_dark") if reply.strip() else Text("(no reply yet)", style=self.palette.text3)
        self.query_one("#p-reply", Static).update(shown)

    def on_key(self, event: events.Key):
        """A peek has nothing to type into. Handing every key to the list ran the rest of a typed sentence as list
        commands ("can you fix it" started a session; the v4.1 runtime tester), so typing is swallowed with a hint,
        an offered key (Enter, r) acts only when pressed on its own, and Esc, Tab or an arrow gives the keys back."""
        if not self.peeking:
            return
        event.stop()
        now = time.monotonic()
        typing = now - self.last_key < TYPING_S
        if event.is_printable or event.key == "backspace":  # only typing counts as typing: Esc then Enter still opens it
            self.last_key = now
        if self.pending:  # another key right after an offered one: it was part of something typed
            self.pending.stop()
            self.pending = None
            typing = True
        if event.key in BACK:
            self.query_one("#p-keys", Static).update(peek_keys(self.palette, self.peek))  # the hint goes with him
            tmuxctl.focus("list")
        elif event.key in [key for key, _ in self.peek.get("keys") or []] and not typing:
            sid = self.peek.get("sid")
            self.pending = self.set_timer(ALONE_S, lambda key=event.key: self.act(key, sid))
        else:
            hint = Text("This is a peek, with nothing to type into. ", style=self.palette.text2)
            self.query_one("#p-keys", Static).update(hint + Text("esc", style=self.palette.key) + Text(" goes back", style=self.palette.text3))

    def act(self, key, sid):
        """An offered key, pressed on its own: the list does it to the same card, and has the keys again; never to
        another card the list moved to meanwhile (the second pass)."""
        self.pending = None
        if not self.peeking or self.peek.get("sid") != sid:
            return
        listp = tmuxctl.pane("list")
        if listp:
            tmuxctl.tmux("send-keys", "-t", listp, "Enter" if key == "enter" else key)
            tmuxctl.focus("list")

    def where(self, text, style=None):
        self.query_one("#where", Static).update(Text(text, style=style or ""))

    @on(Input.Submitted)
    def submit(self, event):
        if event.value.strip():
            event.input.disabled = True
            self.where("starting it…", self.palette.work)
            self.start(event.value.strip())

    @work(thread=True)
    def start(self, prompt):
        job, why = tmuxctl.start(prompt, self.folder)
        self.call_from_thread(self.started, job, why)

    def started(self, job, why):
        if job:
            self.exit(job)
            return
        self.where(why, self.palette.fail)
        field = self.query_one(Input)
        field.disabled = False
        field.focus()

    def action_noop(self):
        pass


if __name__ == "__main__":
    Welcome().run()  # on its own, for a look; in the cockpit it runs inside cockpit/viewer.py
