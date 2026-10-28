"""The right side when no running session is on it: a peek at the cursor's session, or the new chat.

The peek (problems G1) is for a session it can't attach (its process stopped, a chat elsewhere, an ended one): what it
is, what he asked, its last reply and its recap, read from files, so nothing starts. The list writes what to show in a
small file (store.write_peek) and this checks it with a stat 20 times a second.

The new chat (problems H1-H3, after OpenCode's home screen) shows while the list's cursor is on "+ new chat": the
wordmark over one chat box with a bar in the mode's color and a "mode · model · effort" line; Tab cycles the mode,
ctrl+l the model, ctrl+t the effort, ctrl+f the folder; Enter starts the session and this same viewer becomes it.

It sits on the terminal's own background (decision 0002). The wordmark keeps its gradient on purpose:
Pepe called it "awesome" (2026-10-07), and it's the brand, not a state color.
"""

import os
import time

from rich.markdown import Markdown
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import OptionList, Static, TextArea
from textual.widgets.option_list import Option

from . import chat, sessions, store, tmuxctl
from .theme import PALETTES, current, install, mix

MARK = [  # ANSI Shadow, with a rounded S so it doesn't read as a 5
    " █████╗  ██████╗ ███████╗███╗   ██╗████████╗ ██████╗",
    "██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝██╔════╝",
    "███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ╚█████╗ ",
    "██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║    ╚═══██╗",
    "██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ██████╔╝",
    "╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═════╝ ",
]


PLACEHOLDER = 'Ask anything…  "fix the flaky checkout test"'
TAB_GUARD_S = 0.4  # Tab in the list gives the box the keys; a second Tab this soon is that double-tap, not a mode change
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


CHAT_KEYS = (("tab", "mode"), ("ctrl+l", "model"), ("ctrl+t", "effort"), ("ctrl+f", "folder"))
PICKING_KEYS = (("↑↓", "pick"), ("enter", "start here"), ("esc", "cancel"))


def hints(p, picking=False):
    """One quiet line of the keys that work right now, under the box (OpenCode: "tab agents  ctrl+p commands")."""
    return Text("   ").join(Text.assemble((key, p.key), (" " + what, p.text3)) for key, what in (PICKING_KEYS if picking else CHAT_KEYS))


def branch(folder):
    """The git branch of a folder (or of the repo it's in), from .git/HEAD: 0.03 ms, against 4.4 ms for git itself."""
    path = os.path.abspath(folder or "")
    while True:
        dot = os.path.join(path, ".git")
        try:
            if os.path.isfile(dot):  # a worktree: .git names its real git folder
                with open(dot) as f:
                    dot = os.path.join(path, f.read().partition("gitdir:")[2].strip())
            with open(os.path.join(dot, "HEAD")) as f:
                head = f.read().strip()
            return head.removeprefix("ref: refs/heads/") if head.startswith("ref:") else head[:7]
        except OSError:
            if os.path.dirname(path) == path:
                return ""
            path = os.path.dirname(path)


def mtime(path):
    try:
        return os.stat(path).st_mtime_ns
    except (OSError, TypeError):
        return None


def peek_keys(p, peek):
    """Where the session is, then only the keys that do something for it (the list sends them; Welcome.on_key)."""
    keys = Text("   ").join(Text.assemble((key, p.key), (" " + what, p.text3)) for key, what in peek.get("keys") or [])
    return Text("\n").join([Text(peek.get("note", ""), style=p.text2), keys]) if keys else Text(peek.get("note", ""), style=p.text2)


class Mark(Widget):
    """Redrawn on every refresh, so it switches between big and small as the pane is resized."""

    def render(self):
        return wordmark(self.app.palette, self.app.size.width)


class Peek(Vertical):
    """Takes the keys while a peek shows: Textual hands them to the hidden box otherwise (Welcome.on_key)."""

    can_focus = True


class Prompt(TextArea):
    """The chat box. Its keys are bound with priority, ahead of the TextArea's own: a plain Enter binding lost to its
    newline (the v4.2 design critic). Enter starts it; ctrl+j, or a \\ just before Enter, adds a line (his tmux sends
    shift+Enter as a plain Enter)."""

    BINDINGS = [
        Binding("enter", "app.send", show=False, priority=True),
        Binding("ctrl+j", "newline", show=False, priority=True),
        Binding("tab", "app.mode(1)", show=False, priority=True),
        Binding("shift+tab", "app.mode(-1)", show=False, priority=True),
        Binding("ctrl+l", "app.model", show=False, priority=True),
        Binding("ctrl+t", "app.effort", show=False, priority=True),
        Binding("ctrl+f", "app.folders", show=False, priority=True),
        Binding("escape", "app.back", show=False, priority=True),
    ]

    def action_newline(self):
        self.insert("\n")


class Edge(Widget):
    """The box's half-height bottom edge, OpenCode's "╹▀▀▀": the bar's foot in the mode's color, then the panel's."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bar, self.panel = "", ""

    def paint(self, bar, panel):
        self.bar, self.panel = bar, panel
        self.refresh()

    def render(self):
        return Text.assemble(("╹", self.bar), ("▀" * max(0, self.size.width - 1), self.panel))


class Folders(OptionList):
    BINDINGS = [Binding("escape", "app.close_folders", show=False, priority=True),
                Binding("tab,shift+tab", "app.leave_folders", show=False, priority=True)]  # Tab left it up (review 2)


class Welcome(App):
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("ctrl+q,ctrl+c", "noop", show=False, priority=True)]  # quitting would close the cockpit's right side
    CSS = """
    Screen { background: ansi_default; align: center middle; }
    #all { width: 76; max-width: 100%; height: auto; padding: 0 2; }
    Mark { width: 100%; height: auto; margin: 0 0 1 0; text-align: center; }
    #folders { height: auto; max-height: 8; margin: 0 0 1 0; display: none; padding: 0 1; background: ansi_default;
               border: round $ap-line; border-title-color: $ap-key; }
    #folders:focus { border: round $ap-key; }  /* like a dialog's focused input: it has the keys, the box doesn't */
    #folders > .option-list--option-highlighted { background: $panel; text-style: bold; }  /* the dialogs' row */
    #composer { height: auto; border-left: heavy $ap-key; background: ansi_default; }  /* the bar sits on the terminal */
    /* one step lighter than the cards, like OpenCode's, in the stylesheet: painted from code after the first draw,
       the text inside kept the terminal's background (the 4.2 README demo) */
    #panel { height: auto; padding: 1 2 0 2; background: $panel; }
    #prompt { height: auto; max-height: 6; border: none; padding: 0; scrollbar-size-vertical: 0; background: $panel; }
    #prompt .text-area--placeholder { color: $ap-dim; }
    #status { height: 1; margin: 1 0 0 0; }
    #info { width: auto; height: 1; }  /* the mode line never shrinks; the folder takes what's left */
    #folder-line { width: 1fr; height: 1; margin: 0 0 0 2; text-align: right; text-wrap: nowrap; text-overflow: ellipsis; }
    Edge { height: 1; width: 100%; }
    #hints { width: 100%; text-align: right; margin: 1 0 0 0; }
    #why { height: auto; margin: 1 0 0 0; }
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
        self.folder, self.folders, self.picked = "", [], False  # where a new chat starts; picked: he chose it with ctrl+f
        self.choice = chat.load()  # its mode, model and effort, as he left them last time
        self.peek, self.seen = {}, {"peek": "unread"}  # what's shown, and the files' times when read; the first look
        # always draws, file or not (a viewer that started before the list wrote one showed an empty mode line)
        self.last_key, self.pending, self.focused_at = 0.0, None, 0.0

    def get_theme_variable_defaults(self):
        return PALETTES["neon"].variables()

    def compose(self) -> ComposeResult:
        p = self.palette
        with Vertical(id="all"):
            yield Mark()
            yield Folders(id="folders")
            with Vertical(id="composer"), Vertical(id="panel"):
                yield Prompt(id="prompt", placeholder=PLACEHOLDER, compact=True, highlight_cursor_line=False)
                with Horizontal(id="status"):
                    yield Static(id="info")
                    yield Static(id="folder-line")
            yield Edge()
            yield Static(hints(p), id="hints")
            yield Static(id="why")
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
        self.composer_focused()
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
            self.query_one("#hints", Static).update(hints(p))
            self.show_choice()
        if themed or "peek" in changed:
            self.show(store.read_peek() if "peek" in changed else self.peek)
        elif "reply" in changed and self.peeking:
            self.show_reply()

    @property
    def peeking(self):
        return bool(self.peek) and not self.peek.get("blank") and not self.peek.get("compose")

    @property
    def composing(self):
        return not self.peek or bool(self.peek.get("compose"))

    def show(self, peek):
        """{"compose": True} (or {}) is the new chat, {"blank": True} nothing (a running session is in front), anything
        else a peek."""
        self.peek = peek
        self.seen["reply"] = mtime(peek.get("path"))
        self.query_one("#all").display = self.composing
        self.query_one("#peek").display = self.peeking and not self.composing
        if self.composing:
            self.show_composer()
            return
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

    # ------------------------------------------------ the new chat (H1-H3)

    def show_composer(self):
        """The chat box, in the folder the list sent (where `yolo` ran) unless he picked another with ctrl+f."""
        if not self.picked:
            self.folder = self.peek.get("folder") or self.folder or tmuxctl.launch_folder()
        self.folders = self.peek.get("folders") or self.folders
        self.show_choice()  # and the folder beside it
        self.fit()
        listing = self.query_one(Folders)  # an open folder list keeps the keys, or Enter starts in the old folder (review 2)
        (listing if listing.display else self.query_one(Prompt)).focus()

    def show_choice(self):
        """The bar and "Mode · model · effort" (OpenCode's agent line): the mode in its color, a model or effort he
        picked in the text color, a default quieter."""
        p, choice = self.palette, self.choice
        color = chat.color(choice["mode"], p)
        effort = chat.label(chat.EFFORTS, choice["effort"]) if choice["effort"] else chat.default_effort() or "default effort"
        self.query_one("#info", Static).update(Text.assemble(
            (chat.label(chat.MODES, choice["mode"]), f"bold {color}"), (" · ", p.text3),
            (chat.label(chat.MODELS, choice["model"]), p.text if choice["model"] else p.text2), (" · ", p.text3),
            (effort, p.text if choice["effort"] else p.text2)))
        self.query_one("#composer").styles.border_left = ("heavy", color)
        self.query_one(Edge).paint(color, p.sel)  # $panel
        self.show_folder()

    def show_folder(self):
        """The folder and its branch, in the room the mode line leaves: a long path keeps its end, so the folder's own
        name and the branch show (the 4.2 README picture cut "agents-pane:master" to "agents-pan…")."""
        here = branch(self.folder)
        tail = f":{here}" if here else ""
        path = sessions.tilde(self.folder)
        parts = path.split("/")
        room = (self.query_one("#status").size.width or 67) - len(self.query_one("#info", Static).render().plain) - 2
        shown = next((p for p in (path, "…/" + "/".join(parts[-2:]), "…/" + parts[-1]) if len(p) + len(tail) <= room), "…/" + parts[-1])
        self.query_one("#folder-line", Static).update(Text(shown + tail, style=self.palette.text3))

    def fit(self):
        """On a short pane the box always stays: the wordmark goes first, then the hints (the critic)."""
        rows, picking = self.size.height, self.query_one(Folders).display
        self.query_one(Mark).display = rows >= 19 and not picking  # the folder list takes the wordmark's place
        self.query_one("#hints").display = rows >= 10

    def on_resize(self):
        if self.composing:
            self.fit()
            self.call_after_refresh(self.show_folder)  # the room it has is known once the box is laid out again

    def composer_focused(self):
        self.focused_at = time.monotonic()

    def on_app_focus(self):
        """The keys just came to this pane (tmux focus events): the Tab guard starts, and the peek is read again."""
        self.composer_focused()
        self.seen.pop("peek", None)
        self.watch()

    def action_mode(self, step):
        if time.monotonic() - self.focused_at < TAB_GUARD_S:
            return  # the second Tab of the double-tap that brought the keys here
        self.choice["mode"] = chat.cycle(chat.MODES, self.choice["mode"], step)
        self.show_choice()

    def action_model(self):
        self.choice["model"] = chat.cycle(chat.MODELS, self.choice["model"], 1)
        self.show_choice()

    def action_effort(self):
        self.choice["effort"] = chat.cycle(chat.EFFORTS, self.choice["effort"], 1)
        self.show_choice()

    def action_folders(self):
        """ctrl+f: the folders it can start in, right above the box, where the wordmark was."""
        here = os.path.abspath(self.folder)
        folders = [here] + [f for f in self.folders if os.path.abspath(f) != here]
        listing = self.query_one(Folders)
        listing.clear_options()
        listing.add_options([Option(sessions.tilde(f), id=f) for f in folders])
        listing.border_title = "start it in"
        listing.display = True
        listing.highlighted = 0
        self.query_one("#hints", Static).update(hints(self.palette, picking=True))
        self.fit()
        listing.focus()

    @on(OptionList.OptionSelected, "#folders")
    def folder_picked(self, event):
        self.folder, self.picked = event.option.id, True
        self.show_folder()
        self.action_close_folders()

    def action_leave_folders(self):
        if time.monotonic() - self.focused_at >= TAB_GUARD_S:  # the double-tap's second Tab keeps it (second review)
            self.action_close_folders()

    def action_close_folders(self):
        self.query_one(Folders).display = False
        self.query_one("#hints", Static).update(hints(self.palette))
        self.fit()
        self.query_one(Prompt).focus()

    def action_back(self):
        """Esc: the keys go back to the list; the draft stays for when he comes back."""
        tmuxctl.focus("list")

    def action_send(self):
        box = self.query_one(Prompt)
        if box.read_only:
            return
        row, col = box.cursor_location
        if col and box.document.get_line(row)[col - 1] == "\\":  # Claude Code's own way to add a line: a backslash just before Enter
            box.action_delete_left()
            box.insert("\n")
            return
        if box.text.strip() and not os.path.isdir(self.folder):  # the old form refused it; claude would start in ~ (review 2)
            self.say(f"There's no folder at {sessions.tilde(self.folder)}. ctrl+f picks another.", self.palette.fail)
        elif box.text.strip():
            box.read_only = True
            self.say("starting it…", self.palette.work)
            self.start(box.text.strip(), self.folder, dict(self.choice))

    def say(self, text, color):
        self.query_one("#why", Static).update(Text(text, style=color, justify="right"))

    @work(thread=True)
    def start(self, prompt, folder, choice):
        job, why = tmuxctl.start(prompt, folder, choice=choice)
        self.call_from_thread(self.started, job, why, choice)

    def started(self, job, why, choice):
        if job:
            try:
                chat.save(choice)  # remembered only once a session really started with it
            except OSError:
                pass
            self.exit(job)
            return
        self.say(why or "Claude Code didn't start it.", self.palette.fail)  # the text and the mode stay, to try again
        box = self.query_one(Prompt)
        box.read_only = False
        box.focus()

    def action_noop(self):
        pass


if __name__ == "__main__":
    Welcome().run()  # on its own, for a look; in the cockpit it runs inside cockpit/viewer.py
