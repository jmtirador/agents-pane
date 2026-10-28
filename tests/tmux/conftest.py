"""The real launcher on a private tmux server, with a fake `claude`, `osascript` and session files.

Every tmux call goes through a shim that adds `-L <private name>`, so nothing here can reach Pepe's
tmux server (the one that crashed once in v2 testing). An optional second private server attaches a
client at his real size (119x29), so key bindings fire and the full screen, borders and bar included,
can be read back.
"""

import json
import os
import shutil
import subprocess
import time
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REAL_TMUX = shutil.which("tmux")
JOB = "beef0001"
SID = "beef0001-0000-4000-8000-000000000001"

FAKE_CLAUDE = r"""#!/bin/bash
# enough of the claude CLI for the cockpit: --bg, attach, agents, stop, rm
echo "claude $*" >> "$CLAUDE_CONFIG_DIR/calls.log"
case "$1" in
  attach) printf '\033[2J\033[HFAKE CLAUDE attached to %s\n\n❯ \n' "$2"
          while IFS= read -r line; do
            # /exit (like ← and Ctrl+C twice) turns the same process into Claude's own session list, as 2.1.300 does
            [ "$line" = "/exit" ] && { printf '\033[2J\033[HFAKE CLAUDE AGENT VIEW\n'; exec -a "claude agents" sleep 600; }
            [ "$line" = "/ctrl-z" ] && exit 0  # Ctrl+Z really exits (a stopped fake would hang the test instead)
            echo "$2 got: $line" >> "$CLAUDE_CONFIG_DIR/typed.log"; printf '\n⏺ ok\n\n❯ \n'
          done ;;
  agents) echo '[]' ;;
  stop|rm) exit 0 ;;
  *) echo "backgrounded · cafe0001" ;;
esac
"""


class Rig:
    def __init__(self, tmp_path):
        self.name = f"ap-test-{uuid.uuid4().hex[:8]}"
        self.dir = tmp_path
        self.bin = tmp_path / "bin"
        self.config = tmp_path / "claude"
        self.bin.mkdir()
        for sub in ("sessions", "jobs", "projects/-test"):
            (self.config / sub).mkdir(parents=True)
        conf = tmp_path / "test.tmux.conf"
        conf.write_text("set -g default-shell /bin/sh\nset -g base-index 1\nsetw -g pane-base-index 1\nset -g mouse on\n")
        self.shim = self.bin / "tmux"
        self.write(self.shim, f'#!/bin/sh\nexec {REAL_TMUX} -L {self.name} -f {conf} "$@"\n')
        self.write(self.bin / "claude", FAKE_CLAUDE)
        self.write(self.bin / "osascript", '#!/bin/sh\necho "osascript $*" >> "$CLAUDE_CONFIG_DIR/calls.log"\n')
        self.env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE", "AGENTS_PANE_SESSION")}
        self.env.update(PATH=f"{self.bin}:{os.environ['PATH']}", CLAUDE_CONFIG_DIR=str(self.config))
        self.outer = None

    @staticmethod
    def write(path, text):
        path.write_text(text)
        path.chmod(0o755)

    def add_session(self, sid=SID, job=JOB, prompt="fix the flyer", status="idle"):
        """A running background session: a registry entry (alive: it names this test's own process) and a transcript."""
        reg = {"sessionId": sid, "pid": os.getpid(), "kind": "bg", "status": status, "statusUpdatedAt": int(time.time() * 1000),
               "jobId": job, "cwd": str(self.dir), "startedAt": int(time.time() * 1000) - 60_000}
        (self.config / "sessions" / f"{job}.json").write_text(json.dumps(reg))
        (self.config / "jobs" / job).mkdir(parents=True, exist_ok=True)  # what a viewer reads before attaching again
        (self.config / "jobs" / job / "state.json").write_text(json.dumps({"sessionId": sid, "state": "working"}))
        records = [{"type": "user", "timestamp": "2026-10-08T19:00:00.000Z", "cwd": str(self.dir), "message": {"content": prompt}},
                   {"type": "assistant", "timestamp": "2026-10-08T19:00:05.000Z", "message": {"content": [{"type": "text", "text": "Done."}]}}]
        (self.config / "projects" / "-test" / f"{sid}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))

    def tmux(self, *args):
        return subprocess.run([str(self.shim), *args], capture_output=True, text=True, env=self.env)

    def launch(self, *args):
        subprocess.run([os.path.join(ROOT, "bin", "agents-pane"), *args], capture_output=True, text=True, env=self.env, cwd=self.dir)
        self.wait_for(lambda: self.panes().keys() == {"list", "live"}, "the two cockpit panes")

    def panes(self):
        """{role: pane id}; a pane split a moment ago has no role yet and is skipped (it broke zip, 1 run in ~5)."""
        lines = self.tmux("list-panes", "-t", "=agents:cockpit", "-F", "#{@ap_role} #{pane_id}").stdout.splitlines()
        return dict(line.split() for line in lines if len(line.split()) == 2)

    def option(self, role, name):
        return self.tmux("display-message", "-p", "-t", self.panes()[role], f"#{{{name}}}").stdout.strip()

    def screen(self, role, colors=False):
        return self.tmux("capture-pane", "-p", *(["-e"] if colors else []), "-t", self.panes()[role]).stdout

    def window_option(self, name):
        return self.tmux("show-options", "-wv", "-t", "=agents:cockpit", name).stdout.strip()

    def session_option(self, name):
        return self.tmux("show-options", "-v", "-t", "agents", name).stdout.strip()  # (-t here is a pane target: no "=")

    def keys(self, role, *keys):
        """Keys straight into a pane (tmux key bindings don't see these)."""
        self.tmux("send-keys", "-t", self.panes()[role], *keys)

    def attach(self, width=119, height=29):
        """A real client at his size, on a second private server, so bindings fire and the whole screen can be read."""
        self.outer = f"{self.name}-outer"
        subprocess.run([REAL_TMUX, "-L", self.outer, "-f", "/dev/null", "new-session", "-d", "-x", str(width), "-y", str(height),
                        f"{self.shim} attach -t '=agents'"], env=self.env, check=True)  # quoted: zsh expands a bare =word
        self.wait_for(lambda: self.tmux("list-clients", "-t", "=agents").stdout.strip(), "a client attached")

    def press(self, *keys):
        """Keys through the attached client, so tmux key bindings see them."""
        subprocess.run([REAL_TMUX, "-L", self.outer, "send-keys", "-t", "0", *keys], env=self.env)

    def whole_screen(self):
        return subprocess.run([REAL_TMUX, "-L", self.outer, "capture-pane", "-p", "-t", "0"], capture_output=True, text=True).stdout

    def active(self):
        out = self.tmux("list-panes", "-t", "=agents:cockpit", "-F", "#{pane_active} #{@ap_role}").stdout.split("\n")
        return next(line.split()[1] for line in out if line.startswith("1 "))

    def log(self, name):
        path = self.config / name
        return path.read_text() if path.exists() else ""

    def wait_for(self, check, what, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            try:
                if check():
                    return
            except (KeyError, StopIteration, IndexError):
                pass
            time.sleep(0.2)
        raise AssertionError(f"timed out waiting for {what}")

    def close(self):
        if self.outer:
            subprocess.run([REAL_TMUX, "-L", self.outer, "kill-server"], capture_output=True)
        self.tmux("kill-server")
        socket_dir = os.path.join(os.environ.get("TMUX_TMPDIR", "/tmp"), f"tmux-{os.getuid()}")
        for name in (self.name, self.outer):
            if name and os.path.exists(os.path.join(socket_dir, name)):
                os.remove(os.path.join(socket_dir, name))


@pytest.fixture
def rig(tmp_path):
    if not REAL_TMUX:
        pytest.skip("tmux is not installed")
    rig = Rig(tmp_path)
    yield rig
    rig.close()
