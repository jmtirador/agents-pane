"""The list app, headless, with tmux, the claude CLI, the state file and the session reader faked.

Nothing here reaches a real tmux server or a real session: every tmux call is recorded, and a tiny
fake keeps the two bits of tmux state the app reads back (the zoom flag and the live pane's @ap_want).
"""

import subprocess

import pytest
from helpers import NOW, row

from cockpit import app as appmod
from cockpit import sessions, store, tmuxctl

PANES = {"list": "%1", "live": "%2"}


class FakeTmux:
    def __init__(self):
        self.calls = []
        self.zoomed = False
        self.options = {"@ap_want": ""}

    def __call__(self, *args):
        self.calls.append(args)
        commands, current = [], []
        for arg in args:
            if arg == ";":
                commands.append(current)
                current = []
            else:
                current.append(arg)
        commands.append(current)
        out = "".join(self.run(command) for command in commands)
        return subprocess.CompletedProcess(args, 0, out, "")

    def run(self, command):
        name = command[0] if command else ""
        if name == "list-panes":
            return "".join(f"{pid} {role}\n" for role, pid in PANES.items())
        if name == "resize-pane" and "-Z" in command:
            self.zoomed = not self.zoomed
        if name == "set-option" and "-p" in command and command[-2] == "@ap_want":
            self.options["@ap_want"] = command[-1]
        if name == "display-message":
            fmt = command[-1]
            if fmt == "#{window_zoomed_flag}":
                return "1\n" if self.zoomed else "0\n"
            if fmt == "#{@ap_want}":
                return self.options["@ap_want"] + "\n"
            if fmt == "#{pane_pid}":
                return "\n"  # no real process to signal
        return ""

    def named(self, name):
        """Every command with this name, including the ones sent in a batch."""
        found = []
        for args in self.calls:
            command = []
            for arg in (*args, ";"):
                if arg == ";":
                    if command and command[0] == name:
                        found.append(tuple(command))
                    command = []
                else:
                    command.append(arg)
        return found


class Cockpit:
    """The app under test plus everything it asked of the outside world."""

    def __init__(self, monkeypatch, tmp_path, rows):
        self.tmux = FakeTmux()
        self.rows = rows
        self.claude_calls, self.typed, self.notices, self.started = [], [], [], []
        monkeypatch.setattr(tmuxctl, "tmux", self.tmux)
        monkeypatch.setattr(tmuxctl, "start", lambda prompt="", cwd=None, name=None, resume=None: (
            self.started.append({"prompt": prompt, "cwd": cwd, "name": name, "resume": resume}), ("cafe0001", ""))[1])
        monkeypatch.setattr(tmuxctl, "jump", lambda target: True)
        monkeypatch.setattr(tmuxctl, "_panes", {})
        monkeypatch.setattr(tmuxctl, "notify", lambda title, text: self.notices.append((title, text)))
        monkeypatch.setattr(tmuxctl, "claude", lambda *args, cwd=None: (self.claude_calls.append(args), (0, ""))[1])
        monkeypatch.setattr(tmuxctl, "type_into", lambda job, text: self.typed.append((job, text)) or True)
        monkeypatch.setattr(tmuxctl, "launch_folder", lambda: str(tmp_path))
        monkeypatch.setattr(store, "PATH", str(tmp_path / "state.json"))
        monkeypatch.setattr(sessions, "registry_warning", lambda rows: "")
        cockpit = self

        class Watcher:
            def snapshot(self):
                return [dict(r) for r in cockpit.rows]

        monkeypatch.setattr(sessions, "Watcher", Watcher)
        monkeypatch.setattr(appmod, "IN_TMUX", True)
        self.app = appmod.CockpitApp()

    async def settle(self, pilot, seconds=0.2):
        """Let the app react, then wait until its tmux thread has sent everything it queued."""
        await pilot.pause(seconds)
        self.app.screen_stack[1].tmux_calls.submit(lambda: None).result(timeout=5)


@pytest.fixture
def rows():
    return [
        row("work-aaaa", "working", name="finch-fixes", startedAt=NOW - 700_000),
        row("done-bbbb", "done", name="study hub", finishedAt=NOW - 60_000),
    ]


@pytest.fixture
def cockpit(monkeypatch, tmp_path, rows):
    return Cockpit(monkeypatch, tmp_path, rows)
