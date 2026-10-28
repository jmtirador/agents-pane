"""The list's dialogs: reply or rename, find an old session, and the read-only notes (keys, usage).

Every dialog lists its own keys for the bottom bar (KEYS), and the list zooms to the whole window while
one is open. The words are plain on purpose (problem P5): no symbol-only key names, no abbreviations.
"""

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from . import model, search, sessions
from .theme import ORDER, PALETTES

CSS = """
/* Everything sits on the terminal's own gray, boxes are lines only (like Claude Code's prompt box): a see-through
   backdrop blends that gray to black, and a filled box shows a rim outside its rounded line. */
ModalScreen { align: center middle; background: ansi_default; }
.dialog { width: 96; max-width: 100%; height: auto; max-height: 100%; padding: 1 2; background: ansi_default;
          border: round $ap-line; border-title-color: $ap-key; }
.dialog Input { margin: 0 0 1 0; border: round $ap-line; background: ansi_default; }
.dialog Input:focus { border: round $ap-key; background-tint: $foreground 0%; }
Input > .input--placeholder { color: $ap-dim; }
.dialog .label { color: $foreground; }
.dialog .quote { color: $ap-text2; margin: 0 0 1 0; padding: 0 1; border-left: outer $ap-line; }
.dialog .hint { color: $ap-dim; }
.dialog OptionList { height: auto; max-height: 24; margin: 0 0 1 0; border: none; padding: 0; background: ansi_default;
                     scrollbar-background: ansi_default; scrollbar-color: $ap-line; scrollbar-color-hover: $ap-dim; }
.dialog OptionList > .option-list--option-highlighted { background: $panel; text-style: none; }
.dialog OptionList:focus > .option-list--option-highlighted { background: $panel; text-style: bold; }
/* the theme menu sits low in the list, which stays in view (no zoom, nothing over it) so each theme shows live */
Note .dialog { padding: 0 2; }  /* all keys fits the 27 rows a zoomed pane has */
ThemePicker { align: center bottom; background: transparent; }
ThemePicker .dialog { width: 100%; padding: 0 1; margin: 0 1 2 0; }  /* lines up with the boxes, left of the scrollbar */
ThemePicker .dialog OptionList { margin: 0; }
"""


def help_lines(p, version):
    """The full key list for `?`, grouped, in the current theme's colors."""
    groups = {
        "Moving around": [
            ("↑ ↓  j k", "pick a session; the right side shows it"),
            ("g G", "jump to the top or the bottom"),
            ("enter", "open it on the right and type to it (a stopped one starts again)"),
            ("tab", "go to the Claude side"),
            ("ctrl+]", "switch sides, from either side"),
        ],
        "Doing things": [
            ("n", "start a new chat: type, pick its mode, model and folder"),
            ("r", "reply without leaving the list"),
            ("/", "find an old session by what it was about"),
            ("w", "get a Mac notification when it finishes"),
        ],
        "Managing": [
            ("R", "rename it"),
            ("S", "stop it (capital S, twice; its chat is kept)"),
            ("X", "remove it for good (capital X, twice)"),
            ("e", "show or hide idle sessions"),
            ("t", f"change the theme (now {p.label})"),
            ("u", "how often you've used this"),
            ("q", "close the dashboard (or ctrl+c); everything keeps running"),
        ],
    }
    lines = []
    for group, keys in groups.items():
        lines.append(Text(group, style=f"bold {p.text}"))
        lines += [Text.assemble((key.ljust(10), p.key), (what, p.text2)) for key, what in keys]
        lines.append(Text(""))
    lines.append(Text("On the Claude side: ctrl+c twice or ctrl+z brings you back here; it keeps running.", style=p.text3))
    lines.append(Text(f"agents-pane {version}", style=p.text3))
    return lines


class Dialog(ModalScreen):
    """A boxed dialog. While it is open the list pane takes the whole window, then hands it back."""

    BINDINGS = [Binding("escape", "close", show=False)]
    TITLE = ""
    KEYS = [("enter", "ok", "Enter"), ("esc", "cancel", "Escape")]  # the bottom bar while it is open

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog") as box:
            box.border_title = self.TITLE
            yield from self.body()

    def body(self):
        yield from ()

    def action_close(self):
        self.dismiss(None)


class TypeInto(Dialog):
    """Reply or rename: one line typed into a session as if typed in its chat."""

    KEYS = [("enter", "send", "Enter"), ("esc", "cancel", "Escape")]

    def __init__(self, row, title, said, placeholder, value=""):
        super().__init__()
        self.row, self.TITLE, self.said, self.placeholder, self.value = row, title, said, placeholder, value

    def body(self):
        color = model.project_color(self.row["cwd"])
        yield Static(Text.assemble((self.row["name"], "bold"), ("  " + self.row["where"], color)), classes="label")
        if self.said:
            yield Static(self.said, classes="quote")
        yield Input(self.value, placeholder=self.placeholder)
        yield Static("It's typed into the session for you, and the session keeps running.", classes="hint")

    @on(Input.Submitted)
    def submit(self, event):
        if event.value.strip():
            self.dismiss(event.value.strip())


class Find(Dialog):
    TITLE = "find an old session"
    KEYS = [("↓", "pick from the list", "Down"), ("enter", "open the top one", "Enter"), ("esc", "cancel", "Escape")]

    def __init__(self):
        super().__init__()
        self.hits, self.timer = {}, None
        self.shown_for, self.open_when_found = None, False  # the text the hits on screen belong to

    def body(self):
        yield Input(placeholder="what was it about?  e.g. invoice export")
        yield Static("Looks through every prompt, title, recap and reply.", classes="hint")  # above the hits, so a long list can't hide it
        yield OptionList(id="hits")

    def on_mount(self):
        self.query_one(Input).focus()

    @on(Input.Changed)
    def typed(self, event):
        self.open_when_found = False  # he typed on after Enter: he hasn't confirmed this text yet
        if self.timer:
            self.timer.stop()
        self.timer = self.set_timer(0.2, lambda: self.search(event.value))  # the index answers in ~0.1 s (G8)

    @work(thread=True, exit_on_error=False, exclusive=True)
    def search(self, query):
        done = []  # whether the index caught up, which matters with no hits too (the runtime tester)
        refresh = lambda: done.append(search.update_elsewhere()) or done[-1]  # noqa: E731
        hits = search.find(query, 30, refresh=refresh) if len(query.strip()) >= 2 else []
        self.app.call_from_thread(self.show, query, hits, False in done)

    def show(self, query, hits, partial=False):
        if query != self.query_one(Input).value:
            return  # typed on since; the search for the newer text will show
        self.shown_for = query
        self.hits = {h["sid"]: h for h in hits}
        found = self.query_one(OptionList)
        found.clear_options()
        room = max(20, found.size.width - 12)  # the list wraps long lines, so cut them to fit first
        for h in hits:
            color = model.project_color(h["cwd"])
            where = sessions.short_cwd(h["cwd"])
            title = Text.assemble((f"{h['date']:>5}  ", "dim"), (h["name"], ""), ("  " + where if where else "", color),  # bold only on the picked row
                                  no_wrap=True, overflow="ellipsis")
            snippet = Text("       " + h["snippet"], style="dim")
            for line in (title, snippet):
                line.truncate(room + 7, overflow="ellipsis")
            found.add_option(Option(Text("\n").join([title, snippet]), id=h["sid"]))
        found_words = f"{len(hits)} found. Enter opens the top one; ↓ picks another." if hits else "Nothing yet."
        if partial or (hits and hits[0].get("partial")):
            found_words += " Still indexing your sessions, so some may be missing."
        self.query_one(".hint", Static).update(found_words)
        if self.open_when_found:
            self.open_when_found = False
            if hits:
                self.dismiss(hits[0])

    def on_key(self, event):
        if event.key == "down" and isinstance(self.focused, Input) and self.hits:
            self.open_when_found = False  # he's picking by hand
            self.query_one(OptionList).focus()
            event.stop()

    @on(Input.Submitted)
    def first(self, event):
        """Open the top result for the text in the box now (B4: a fast Enter used to open the previous text's)."""
        if self.timer:
            self.timer.stop()
        if self.shown_for == event.value:
            if self.hits:
                self.dismiss(next(iter(self.hits.values())))
        else:
            self.open_when_found = True
            self.search(event.value)

    @on(OptionList.OptionSelected)
    def picked(self, event):
        self.dismiss(self.hits[event.option.id])


def swatch(p):
    """A theme's name and what it changes, as dots: its own color, working, done, and the keys."""
    return Text.assemble((f" {p.label:<17}", ""), *[("● ", color) for color in (p.brand, p.work, p.done, p.key)])


class ThemePicker(Dialog):
    """t: the themes, each with its colors. Moving to one shows it live; enter keeps it; esc puts the old one back."""

    TITLE = "theme"
    KEYS = [("↑↓", "try", "Down"), ("enter", "keep", "Enter"), ("esc", "put back", "Escape")]

    def __init__(self, current, look):
        super().__init__()
        self.current, self.look = current, look

    def body(self):
        yield OptionList(*[Option(swatch(PALETTES[name]), id=name) for name in ORDER])

    def on_mount(self):
        themes = self.query_one(OptionList)
        themes.highlighted = ORDER.index(self.current)
        themes.focus()

    @on(OptionList.OptionHighlighted)
    def looked(self, event):
        self.look(event.option.id)

    @on(OptionList.OptionSelected)
    def kept(self, event):
        self.dismiss(event.option.id)

    def action_close(self):
        self.dismiss(self.current)  # esc keeps the theme he had


class Note(Dialog):
    """Keys and usage: text to read; any key closes it (the bar says esc, the plainest one)."""

    KEYS = [("esc", "close", "Escape")]

    def __init__(self, title, lines):
        super().__init__()
        self.TITLE, self.lines = title, lines

    def body(self):
        yield Static(Text("\n").join(self.lines))

    def on_key(self, event):
        event.stop()
        self.dismiss(None)

    def on_click(self):
        self.dismiss(None)
