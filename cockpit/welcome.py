"""The live pane when no session is on it: the wordmark, a box that starts a new session right here, and a tip.

It sits on the terminal's own background (decision 0002). The wordmark keeps its gradient on purpose:
Pepe called it "awesome" (2026-10-07), and it's the brand, not a state color.
"""

import os
from datetime import date

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Input, Static

from . import sessions, tmuxctl
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


def tip(day=None):
    """One tip a day, so the features get found without a manual."""
    return TIPS[(day or date.today()).toordinal() % len(TIPS)]


class Mark(Widget):
    """Redrawn on every refresh, so it switches between big and small as the pane is resized."""

    def render(self):
        return wordmark(self.app.palette, self.app.size.width)


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
    """

    def __init__(self):
        super().__init__(ansi_color=True)  # lets "ansi_default" mean the terminal's own background
        self.palette = current()
        self.folder = tmuxctl.launch_folder()

    def get_theme_variable_defaults(self):
        return PALETTES["neon"].variables()

    def compose(self) -> ComposeResult:
        p = self.palette
        with Vertical(id="all"):
            yield Mark()
            yield Static("Pick a session on the left, or start a new one here.", id="tag")
            with Vertical(id="box") as box:
                box.border_title = "new session"
                yield Input(placeholder="what should it do?")
                yield Static(id="where")
            yield Static(keys_line(p), id="keys")
            yield Static(f"Tip: {tip()}", id="tip")

    def on_mount(self):
        install(self, self.palette)
        self.where(f"in {sessions.tilde(self.folder)}")
        self.query_one(Input).focus()

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


def main():
    job = Welcome().run()
    if job:  # cockpit/live.py, which ran this screen, shows the new session next
        tmuxctl.set_pane_option(os.environ.get("TMUX_PANE"), "@ap_want", job)


if __name__ == "__main__":
    main()
