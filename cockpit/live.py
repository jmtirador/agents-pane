"""The live pane's one long-running process: Claude Code attached to the picked session, or the welcome screen.

The list asks for a switch by setting the pane option @ap_want and sending this process SIGUSR1. The pane
itself is never re-created: tmux 3.7c crashes the whole server when a respawn-pane fails and the same pane
is respawned again, and a failed respawn did happen in testing. Swapping children inside one process avoids it.
Nothing may end this process either, because the pane closes with it.
"""

import os
import signal
import subprocess
import sys
import time

from . import tmuxctl

RESET = "\x1bc"  # a full terminal reset between children, so no mode one leaves on leaks into the next


def main():
    pane = os.environ["TMUX_PANE"]
    child, asked = None, False

    def switch(*_):
        nonlocal asked
        asked = True
        if child and child.poll() is None:
            child.send_signal(signal.SIGHUP)  # what tmux sends when it closes a pane

    signal.signal(signal.SIGUSR1, switch)  # first thing: SIGUSR1's default action would end this process
    for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTSTP):
        signal.signal(sig, lambda *_: None)  # keys meant for Claude must never end this process; children get the defaults back

    while True:
        asked, started = False, time.time()
        try:
            job = tmuxctl.pane_option(pane, "@ap_want")
            sys.stdout.write(RESET)
            sys.stdout.flush()
            child = subprocess.Popen(["claude", "attach", job] if job else [sys.executable, "-m", "cockpit.welcome"])
            if asked:
                child.send_signal(signal.SIGHUP)  # a switch came in while it was starting
            child.wait()
            if not asked and job and tmuxctl.pane_option(pane, "@ap_want") == job:
                tmuxctl.set_pane_option(pane, "@ap_want", "")  # he left the session (Ctrl+Z): back to the welcome screen
        except Exception as e:  # e.g. claude missing mid-update: say so, fall back to the welcome screen, keep going
            print(f"\r\nThe live pane hit a problem: {e}\r\nTrying again…", flush=True)
            time.sleep(2)
            tmuxctl.set_pane_option(pane, "@ap_want", "")
            continue
        if not asked and time.time() - started < 1:
            time.sleep(1)  # something exits at once (a removed session, a crash): don't spin


if __name__ == "__main__":
    main()
