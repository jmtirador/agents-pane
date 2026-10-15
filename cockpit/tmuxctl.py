"""Everything the cockpit asks of tmux and the claude CLI: the viewers, the look, the bars, messages.

The cockpit is one tmux window, agents:cockpit: the list on the left (@ap_role=list) and, on the right, whichever
viewer is showing. A viewer is a pane running cockpit/viewer.py for one session (or the welcome screen); hidden
viewers wait in a separate session, agents-viewers, and showing one swaps it in (decision 0006). Every viewer is
tagged @ap_role=live and @ap_job=<job or "welcome">, and the tags move with the pane.
"""

import os
import re
import shlex
import subprocess
import sys
import time

from .theme import Palette

SESSION = os.environ.get("AGENTS_PANE_SESSION", "agents")  # "agents-preview" runs a branch beside the real cockpit
WINDOW = f"{SESSION}:cockpit"
# set-option reads -t as a pane, where a bare "agents" can match a window named "agents…" in whatever session
# runs the command; "=agents:" is exactly this session (and "=agents" where -t is a session)
OPTS = f"={SESSION}:"
VIEWERS = f"{SESSION}-viewers"  # hidden viewers live here, out of reach of next-window and the status bar
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP_WARM = 4  # hidden viewers kept attached; one idle `claude attach` measured 144 MB and no CPU
WARM_FOR_S = 15 * 60  # a hidden viewer not shown for this long is closed
LIST_WIDTH = 42
ALERT = "#{S:#{@ap_alert}}"  # the needs-you chip lives on the agents session, so it vanishes with it
ANSI = re.compile(r"\x1b\[[0-9;]*m")
EMPTY_PROMPT = re.compile(r"^❯\s*$", re.M)

# The bottom bar, one set per side: (key shown, what it does, the key a click sends to the list).
# A click on "ctrl+]" sends F12 (a "]" can't go in a click range's name), which the list maps to the same switch.
LIST_KEYS = [("↑↓", "pick", "Down"), ("enter", "open", "Enter"), ("n", "new", "n"), ("/", "find", "/"), ("t", "theme", "t"),
             ("?", "all keys", "?"), ("q", "close", "q")]
CLAUDE_KEYS = [("ctrl+]", "back to your sessions", "F12"), ("", "close", "q")]


def tmux(*args):
    """Run tmux; a failure comes back as a non-zero result, never an exception.

    A lone ";" argument separates commands (see batch). tmux also ends a command at any argument that
    ends in ";", so a value like "fix this;" has its ";" escaped.
    """
    args = [a[:-1] + "\\;" if len(a) > 1 and a.endswith(";") else a for a in args]
    try:
        return subprocess.run(["tmux", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    except OSError as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def batch(commands):
    """Several tmux commands in one process instead of one each (a tmux call costs about 4.5 ms)."""
    return tmux(*[arg for command in commands for arg in (*command, ";")][:-1])


_panes = {}


def pane(role):
    """The pane id for a role. Looked up once: these panes are never re-created and tmux never reuses an id."""
    if role not in _panes:
        for line in tmux("list-panes", "-t", WINDOW, "-F", "#{pane_id} #{@ap_role}").stdout.splitlines():
            pane_id, _, found = line.partition(" ")
            if found:
                _panes[found] = pane_id
    return _panes.get(role)


def pane_option(pane_id, name):
    return tmux("display-message", "-p", "-t", pane_id, f"#{{{name}}}").stdout.strip() if pane_id else ""


def set_pane_option(pane_id, name, value):
    if pane_id:
        tmux("set-option", "-p", "-t", pane_id, name, value)


def viewers():
    """{job: (pane id, "slot" or "hidden", shown at, parked)} for every viewer, read from tmux each time: never from
    the list's memory, which a crash or a second list would get wrong (decision 0006)."""
    found = {}
    fmt = "#{session_name}\t#{window_name}\t#{pane_id}\t#{@ap_role}\t#{@ap_job}\t#{@ap_shown}\t#{@ap_parked}"
    for line in tmux("list-panes", "-a", "-F", fmt).stdout.splitlines():
        session, window, pane_id, role, job, shown, parked = (line.split("\t") + [""] * 7)[:7]
        if role == "live" and job and session in (SESSION, VIEWERS):
            where = "slot" if session == SESSION and window == "cockpit" else "hidden"
            if found.get(job, ("", ""))[1] != "slot":  # a copy waiting to be closed never hides the right side
                found[job] = (pane_id, where, int(shown or 0), parked == "1")
    return found


def slot():
    """The viewer on the right side, (its job, its pane id), or ("", "") when there is none. Found by window, never
    by position: while a dialog zooms the list, tmux's {right} is the list itself (the v4 stress test)."""
    return next(((job, v[0]) for job, v in viewers().items() if v[1] == "slot"), ("", ""))


def showing():
    """The job on the right side ("welcome" for the welcome screen), or "" when it can't be read."""
    return slot()[0]


def viewer_command(job):
    return (f"cd {shlex.quote(ROOT)} && exec env PYTHONPATH={shlex.quote(ROOT)} ESCDELAY=20 "
            f"{shlex.quote(sys.executable)} -m cockpit.viewer {shlex.quote(job)}")


def spawn(job):
    """A new hidden viewer for a job; its pane id, or "" when tmux refused."""
    command = viewer_command(job)
    if tmux("has-session", "-t", f"={VIEWERS}").returncode == 0:
        made = tmux("new-window", "-d", "-P", "-F", "#{pane_id}", "-t", f"={VIEWERS}:", command)
    else:
        made = tmux("new-session", "-d", "-P", "-F", "#{pane_id}", "-s", VIEWERS, "-x", "200", "-y", "50",
                    "-e", f"AGENTS_PANE_SESSION={SESSION}", "-e", "CLAUDE_CODE_TMUX_TRUECOLOR=1", "-e", "COLORTERM=truecolor", command)
    pane_id = made.stdout.strip()
    if pane_id:
        batch([("set-option", "-p", "-t", pane_id, "@ap_role", "live"), ("set-option", "-p", "-t", pane_id, "@ap_job", job)])
    return pane_id


def view(job, fresh=False):
    """Show a session (or "welcome") on the right: swap its warm viewer in, or start one (decision 0006).

    fresh: start a parked viewer over (Enter on a stopped session brings it back); the parked one is closed once
    it's out of the cockpit window, since close() never touches the right side.
    """
    found = viewers()
    old = next((v[0] for v in found.values() if v[1] == "slot"), "")
    if not old:
        return False  # the right side isn't a viewer (it died): {right} would be the list, and a swap would hide it
    pane_id, where, _, parked = found.get(job, ("", "", 0, False))
    if where == "slot" and not (fresh and parked):
        return True
    stale = pane_id if fresh and parked else ""
    if not pane_id or stale:
        pane_id = spawn(job)
        if not pane_id:
            return False
    now = str(int(time.time()))  # a viewer stays warm for WARM_FOR_S after he last saw it, so both ends are stamped
    swapped = batch([("swap-pane", "-Z", "-d", "-s", pane_id, "-t", old),  # -Z: an open dialog keeps the whole window
                     ("set-option", "-p", "-t", pane_id, "@ap_shown", now),
                     ("set-option", "-p", "-t", old, "@ap_shown", now)])
    if stale:
        close(stale)
    return not swapped.returncode


def set_note(text):
    """The welcome screen's line on the right ("" for its usual one)."""
    welcome = viewers().get("welcome", ("",))[0]
    if welcome:
        tmux("set-option", "-p", "-t", welcome, "@ap_note", text)


def close(pane_id):
    """Close a viewer, but never the one on the right side: a race could have swapped it in (decision 0006)."""
    tmux("if-shell", "-F", "-t", pane_id, "#{!=:#{window_name},cockpit}", f"kill-pane -t {pane_id}")


def tidy(jobs):
    """Close hidden viewers he won't need: sessions that are gone, parked ones, ones not shown for a while, and any
    past the few kept warm. jobs: the background sessions the list still shows."""
    now = time.time()
    hidden = sorted(((shown, job, pane_id, parked) for job, (pane_id, where, shown, parked) in viewers().items()
                     if where == "hidden" and job != "welcome"), reverse=True)
    for rank, (shown, job, pane_id, parked) in enumerate(hidden):
        if job not in jobs or parked or now - shown > WARM_FOR_S or rank >= KEEP_WARM:
            close(pane_id)


def close_hidden():
    """Every hidden viewer, when he closes the dashboard; the one on the right stays for next time."""
    tmux("kill-session", "-t", f"={VIEWERS}")


def zoom(on):
    """Give the list the whole window while a dialog is open; hand the space back after."""
    list_pane = pane("list")
    if not list_pane:
        return
    toggle = ("resize-pane", "-Z", "-t", list_pane)
    zoomed = pane_option(list_pane, "window_zoomed_flag") == "1"
    if on and not zoomed:
        tmux(*toggle)
    elif not on:  # a resize while zoomed skipped the width hook, so set the width on the way out
        batch(([toggle] if zoomed else []) + [("resize-pane", "-t", list_pane, "-x", str(LIST_WIDTH))])


def focus(role):
    """Give one side the keys. The right side's pane id changes with every swap, so it's looked up each time; it
    doesn't take them while a dialog is open, because select-pane on it would un-zoom the dialog (the re-review)."""
    if role == "list":
        target = pane("list")
        if target:
            tmux("select-pane", "-t", target)
        return
    target = slot()[1]
    if target:
        tmux("if-shell", "-F", "-t", target, "#{?#{||:#{window_zoomed_flag},#{@ap_dialog}},0,1}", f"select-pane -t {target}")


def flip():
    """Switch sides once: the pane after the active one (with two panes, the other one)."""
    tmux("select-pane", "-t", f"{WINDOW}.+")


def jump(target):
    """Switch to a chat that runs in another tmux pane."""
    return tmux("switch-client", "-t", target).returncode == 0


def leave():
    """Close the dashboard for the client looking at it: back to the tmux session it came from (yolo run inside
    tmux switches into the dashboard), else out of tmux. Every session keeps running."""
    close_hidden()
    if tmux("switch-client", "-l").returncode:
        tmux("detach-client")


def launch_folder():
    """The folder `yolo` was last run from: new sessions start there."""
    return tmux("show-environment", "-t", f"={SESSION}", "AGENTS_PANE_CWD").stdout.strip().partition("=")[2] or os.getcwd()


def key_bar(p: Palette, keys):
    """Keys as quiet text, the key in the look's key color and what it does in gray; clicking one presses it in the list."""
    return " " + "   ".join(f"#[range=user|ap-{send}]" + (f"#[fg={p.key}]{key} " if key else "") + f"#[fg={p.text3}]{what}#[norange]"
                               for key, what, send in keys)


def side_bar(p: Palette):
    """The keys for whichever side has the keys: tmux picks by the focused pane's @ap_role, with no round trip to the app."""
    return f"#{{?#{{==:#{{@ap_role}},live}},{key_bar(p, CLAUDE_KEYS)},{key_bar(p, LIST_KEYS)}}}"


def set_keys(p: Palette, keys=None):
    """The bar shows the keys that work right now: an open dialog's own, or the focused side's.

    A dialog's keys also mean a dialog is open, so @ap_dialog is set with them: Ctrl+] waits for it to close.
    """
    batch([("set-option", "-t", OPTS, "status-left", key_bar(p, keys) if keys else side_bar(p)),
           ("set-option", "-t", OPTS, "@ap_dialog", "1") if keys else ("set-option", "-u", "-t", OPTS, "@ap_dialog")])


def style(p: Palette):
    """A quiet frame for the cockpit only (decisions 0002 and 0003); his other tmux sessions keep their look.

    The terminal paints the background, one thin gray line divides the two sides, there are no title
    lines (Claude Code already shows its own name and context), and the bar lists the focused side's keys.
    """
    window = [
        ("pane-border-lines", "single"),
        ("pane-border-status", "bottom"),  # a plain line over the key bar, with no title on it (Pepe, 2026-10-08)
        ("pane-border-format", ""),
        ("pane-border-indicators", "off"),
        ("pane-border-style", f"fg={p.line}"),
        ("pane-active-border-style", f"fg={p.line}"),
        ("window-style", "bg=default"),
        ("window-active-style", "bg=default"),
    ]
    waiting = "#{?#{==:#{@ap_role},live},#{@ap_waiting},}"  # only while he's on the Claude side: the list shows its own
    session = [
        ("status", "on"),
        ("status-position", "bottom"),
        ("status-justify", "left"),
        ("status-style", f"bg=default fg={p.text3}"),
        ("status-left-length", "200"),
        ("status-left", side_bar(p)),
        ("status-right", f"{waiting}#[fg={p.text3}] %H:%M "),
        ("window-status-format", ""),
        ("window-status-current-format", ""),
        ("mouse", "on"),
        ("@ap_cockpit", "1"),  # the global Ctrl+] and click bindings act only here; set by the list itself, so a
                               # cockpit made by an older launcher gets it too (the review found Ctrl+] typed into Claude)
    ]
    batch([("set-option", "-w", "-t", WINDOW, *o) for o in window] + [("set-option", "-t", OPTS, *o) for o in session]
          + [("set-option", "-s", "focus-events", "on")])  # the list dims while Claude has the keys


def bind_keys():
    """Ctrl+] flips between the list and the live session; clicking a key in the bar presses it in the list.

    Both bindings are global in tmux, so each one checks it is in a cockpit (the launcher marks the
    session with @ap_cockpit, so a preview cockpit works too) and otherwise does exactly what tmux did
    before. Ctrl+] does nothing while a dialog is open (a zoomed one would be squeezed into the list, and
    the theme menu, which doesn't zoom, would be left open behind Claude). A click goes to the list of the cockpit that was clicked, its leftmost pane. The list
    keeps its width when the terminal is resized.
    """
    list_pane = pane("list")
    flip = "if-shell -F '#{||:#{window_zoomed_flag},#{@ap_dialog}}' '' 'select-pane -t :.+'"
    click = "run-shell -b \"tmux send-keys -t '#{session_name}:cockpit.{left}' '#{s/^ap-//:mouse_status_range}'\""
    batch([
        ("bind-key", "-n", "C-]", "if-shell", "-F", "#{@ap_cockpit}", flip, "send-keys C-]"),
        ("bind-key", "-n", "MouseDown1Status", "if-shell", "-F", "#{m:ap-*,#{mouse_status_range}}", click, "switch-client -t ="),
        # not while a dialog has zoomed the list: resizing a pane unzooms the window
        ("set-hook", "-w", "-t", WINDOW, "window-resized", f"if-shell -F '#{{window_zoomed_flag}}' '' 'resize-pane -t {list_pane} -x {LIST_WIDTH}'"),
        # closing the terminal (not q) also frees the hidden viewers; quoted: tmux runs hooks through his zsh
        ("set-hook", "-t", OPTS, "client-detached", f"run-shell -b \"tmux kill-session -t '={VIEWERS}' 2>/dev/null; true\""),
        ("resize-pane", "-t", list_pane, "-x", str(LIST_WIDTH)),
    ])


def publish(p: Palette, waiting):
    """How many sessions wait for him: in the bar while he's on the Claude side, and in his other tmux sessions."""
    words = f"{waiting} waiting for you"
    batch([
        ("set-option", "-t", OPTS, "@ap_waiting", f"#[fg={p.needs} bold]{words}#[default]   " if waiting else ""),
        ("set-option", "-t", OPTS, "@ap_alert", f"#[fg={p.needs} bold]agents: {words}#[default]  " if waiting else ""),
    ])
    ensure_alert()


def ensure_alert():
    """Put the chip's slot back at the front of the global status bar (a tmux.conf reload drops it)."""
    right = tmux("show-options", "-gv", "status-right").stdout.rstrip("\n")
    if ALERT not in right:
        tmux("set-option", "-g", "status-right", ALERT + right.replace("#{@ap_alert}", ""))


def notify(title, text):
    """A Mac notification, for watched sessions that finish."""
    script = f"display notification {applescript(text)} with title {applescript(title)} sound name \"Glass\""
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, stdin=subprocess.DEVNULL)
    except OSError:
        pass


def applescript(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def claude(*args, cwd=None):
    """Run the claude CLI; the output comes back without color codes."""
    try:
        done = subprocess.run(["claude", *args], capture_output=True, text=True, cwd=cwd, timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return done.returncode, ANSI.sub("", done.stdout + done.stderr).strip()


def start(prompt="", cwd=None, name=None, resume=None):
    """Start (or resume) a background session; returns (its id, '') or (None, why it failed)."""
    args = ["--bg", "--dangerously-skip-permissions"]
    if name:
        args += ["-n", name]
    if resume:
        args += ["--resume", resume]
    if prompt:
        args += ["--", prompt]  # a prompt that starts with "-" is still a prompt
    code, out = claude(*args, cwd=cwd if cwd and os.path.isdir(cwd) else os.path.expanduser("~"))
    found = re.search(r"backgrounded · ([0-9a-f]{8})", out)
    return (found.group(1), "") if found else (None, out.splitlines()[0] if out else f"claude exited {code}")


def type_into(job_id, text):
    """Type a message (or a slash command) into a background session as if typed in its chat.

    A hidden window attaches, waits for the empty prompt, types, and closes; the session keeps running.
    """
    made = tmux("new-window", "-d", "-P", "-F", "#{pane_id}", "-t", f"{SESSION}:", "-n", "ap-send", f"claude attach {shlex.quote(job_id)}")
    hidden = made.stdout.strip()
    if not hidden:
        return False
    try:
        for _ in range(60):  # up to 15 s for the chat to draw its prompt
            time.sleep(0.25)
            if EMPTY_PROMPT.search(tmux("capture-pane", "-p", "-t", hidden).stdout):
                break
        else:
            return False
        if tmux("send-keys", "-t", hidden, "-l", "--", text).returncode:  # "--": a reply starting with "-" is text
            return False
        tmux("send-keys", "-t", hidden, "Enter")
        time.sleep(1.5)  # let it land before the window closes
        return True
    finally:
        tmux("kill-pane", "-t", hidden)
        # a second client at another size garbles the viewer on the right until it repaints: nudge it (decision 0006),
        # unless a dialog has the whole window, which a resize would squeeze back into the list (the v4 review)
        list_pane = pane("list")
        if list_pane:
            unzoomed = "#{!=:#{window_zoomed_flag},1}"
            batch([("if-shell", "-F", "-t", list_pane, unzoomed, f"resize-pane -t {list_pane} -x {width}")
                   for width in (LIST_WIDTH + 1, LIST_WIDTH)])
