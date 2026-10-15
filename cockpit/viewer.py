"""One viewer: `claude attach <job>` kept running in its own pane, or the welcome screen (decision 0006).

The list swaps viewers into the right side instead of restarting `claude attach` for every pick. This process
must never end on its own while its pane may be showing: the right side would close with it. So Claude's keys
(Ctrl+C, Ctrl+\\, Ctrl+Z) can't end it, and when he leaves the session inside Claude it attaches again. SIGHUP
keeps its default, so the viewer dies with its pane and nothing is left behind.
"""

import ctypes
import os
import signal
import subprocess
import sys
import time

from . import sessions, tmuxctl

DETACHED_AFTER_S = 1.5  # an attach that ran this long ended because he detached; a quicker exit is a failure
TRIES = 3
WATCH_S = 0.3  # how often a viewer checks that its attach is still on its session


def ignore_claude_keys():
    """A handler that does nothing (not SIG_IGN), so children started after this get the default actions back."""
    for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTSTP):
        signal.signal(sig, lambda *_: None)


def job_state(job):
    """The job's state from Claude's own file; None when the session is gone."""
    data = sessions.read_json(os.path.join(sessions.JOBS_DIR, job, "state.json"))
    return data.get("state", "") if data else None


def showing_and_active(pane):
    """Is this pane on the right side with the keys? Only then does a detach hand the keys back to the list."""
    out = tmuxctl.tmux("display-message", "-p", "-t", pane, "#{session_name}\t#{window_name}\t#{pane_active}").stdout.strip()
    return out == f"{tmuxctl.SESSION}\tcockpit\t1"


def command_line(pid):
    """A process's command line, or None. macOS has no /proc; sysctl(KERN_PROCARGS2) reads it in ~0.03 ms (ps: ~2.4 ms)."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().replace(b"\0", b" ").decode(errors="replace").strip()
    except OSError:
        pass
    try:
        libc = ctypes.CDLL(None)
        mib = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN, KERN_PROCARGS2
        size = ctypes.c_size_t(0)
        if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0):
            return None
        buf = ctypes.create_string_buffer(size.value)
        if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0):
            return None
    except (AttributeError, OSError):
        return None
    raw = buf.raw[: size.value]
    argc = int.from_bytes(raw[:4], sys.byteorder)
    args = [a for a in raw[4:].split(b"\0")[1:] if a][:argc]  # the program's path, NUL padding, then its arguments
    return " ".join(a.decode(errors="replace") for a in args)


def run_attach(job):
    """`claude attach <job>` until it ends or leaves the session.

    Inside an attach, ←, /exit and Ctrl+C twice don't exit: the same process turns into `claude agents`, Claude's
    own session list (measured on Claude Code 2.1.300). The list on the left is his session list, so that one is
    closed and the caller attaches again; only Ctrl+Z really exits.
    """
    child = subprocess.Popen(["claude", "attach", job])
    while True:
        try:
            return child.wait(WATCH_S)
        except subprocess.TimeoutExpired:
            if "claude agents" in (command_line(child.pid) or ""):  # only that: a title we don't know is left alone
                child.terminate()
                try:
                    return child.wait(2)
                except subprocess.TimeoutExpired:
                    child.kill()
                    return child.wait()


def park(pane, why):
    """Say why there's nothing to show and wait to be closed: the list swaps something else in and closes this pane."""
    tmuxctl.set_pane_option(pane, "@ap_parked", "1")
    sys.stdout.write(f"\x1bc\r\n  {why}\r\n")
    sys.stdout.flush()
    while True:
        time.sleep(3600)


def attach(pane, job):
    failures = 0
    while True:
        started = time.time()
        try:
            run_attach(job)
        except OSError:  # no `claude` (mid-update, say): a quick failure, tried again below
            pass
        sys.stdout.write("\x1bc")  # whatever Claude left on the screen or in the terminal's modes goes
        sys.stdout.flush()
        state = job_state(job)
        if state is None:
            park(pane, "This session was removed.")
        if state == "stopped":
            park(pane, "This session is stopped. Press enter in the list to bring it back.")
        if time.time() - started >= DETACHED_AFTER_S:
            failures = 0  # he left it inside Claude (←, /exit, Ctrl+C twice, Ctrl+Z): show it again, keys back to the list
            if showing_and_active(pane):
                tmuxctl.focus("list")
            continue
        failures += 1
        if failures >= TRIES:
            park(pane, "Claude Code couldn't open this session. Press enter in the list to try again.")
        time.sleep(1)


def welcome(pane):
    """The welcome screen; when it starts a session, this viewer becomes that session's viewer."""
    from . import quick_esc
    from .welcome import Welcome  # Textual only here: a job viewer starts without it

    quick_esc.install()

    while True:
        sys.stdout.write("\x1bc")
        sys.stdout.flush()
        job = Welcome().run()
        if job:
            tmuxctl.set_pane_option(pane, "@ap_job", job)  # the right side's @ap_job is what the list reads
            return job


def main():
    ignore_claude_keys()
    pane = os.environ["TMUX_PANE"]
    try:
        job = sys.argv[1]
        if job == "welcome":
            job = welcome(pane)
        attach(pane, job)
    except Exception as e:  # this pane may be the right side: if it closed, {right} would be the list (the v4 review)
        park(pane, f"Something went wrong here: {e}. Press enter in the list to try again.")


if __name__ == "__main__":
    main()
