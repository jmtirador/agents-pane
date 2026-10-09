"""python -m cockpit runs the session list; `new "prompt"` starts a session and shows it live; `--version` prints the version."""

import os
import sys

from . import __version__, tmuxctl

if sys.argv[1:2] == ["--version"]:
    print(__version__)
elif sys.argv[1:2] == ["new"]:
    job, why = tmuxctl.start(" ".join(sys.argv[2:]), os.getcwd())
    if not job:
        sys.exit(why)
    tmuxctl.show_live(job)
    tmuxctl.focus("live")
else:
    from .app import CockpitApp

    app = CockpitApp()
    app.run()
    sys.exit(app.return_code or 0)  # a crash must not look like a clean exit, or the launcher closes the pane
