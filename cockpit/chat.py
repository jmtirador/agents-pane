"""A new chat's mode, model and effort (problems H2): the choices, what each puts on the `claude --bg` command line,
and the last ones he picked.

The modes are Claude Code's permission modes (code.claude.com/docs/en/permission-modes), with yolo first because
that's how he works. Checked on throwaway sessions (Claude Code 2.1.312): `--bg` honors `--permission-mode`,
`--model` and `--effort` (max too).
"""

import json
import os

from .sessions import CLAUDE_DIR, read_json

# (choice, label, what it does, its color: a theme attribute or a hex, never a state color like the waiting orange)
MODES = [
    ("yolo", "Yolo", "runs everything without asking", "brand"),
    ("auto", "Auto", "runs everything, with Claude's safety checks", "#7aa2f7"),
    ("plan", "Plan", "reads and plans, edits nothing", "#bb9af7"),
    ("edits", "Accept edits", "edits files without asking, asks for the rest", "#94e2d5"),
    ("manual", "Manual", "asks before anything but reading", "text2"),
]
FLAGS = {"yolo": ["--dangerously-skip-permissions"], "auto": ["--permission-mode", "auto"], "plan": ["--permission-mode", "plan"],
         "edits": ["--permission-mode", "acceptEdits"], "manual": ["--permission-mode", "manual"],
         "dontask": ["--permission-mode", "dontAsk"]}  # not offered, but a dontAsk session comes back as one
# a transcript's permission mode back to a choice, so a session brought back keeps its mode (the v4.2 design critic)
FROM_TRANSCRIPT = {"bypassPermissions": "yolo", "auto": "auto", "plan": "plan", "acceptEdits": "edits", "default": "manual", "manual": "manual",
                   "dontAsk": "dontask"}
MODELS = [("", "default model"), ("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku"), ("fable", "Fable")]
EFFORTS = [("", "default"), ("low", "low"), ("medium", "medium"), ("high", "high"), ("xhigh", "xhigh"), ("max", "max")]
DEFAULT = {"mode": "yolo", "model": "", "effort": ""}
_NAME = os.environ.get("AGENTS_PANE_SESSION", "agents")  # a preview cockpit keeps its own, like store.py
PATH = os.path.join(CLAUDE_DIR, "agents-pane", "new-chat.json" if _NAME == "agents" else f"new-chat-{_NAME}.json")


def cycle(choices, current, step):
    """The next (or previous) choice, wrapping around; an unknown one starts over."""
    keys = [key for key, *_ in choices]
    return keys[(keys.index(current) + step) % len(keys)] if current in keys else keys[0]


def label(choices, current):
    return next((text for key, text, *_ in choices if key == current), choices[0][1])


def color(mode, palette):
    found = next((c for key, _, _, c in MODES if key == mode), "brand")
    return found if found.startswith("#") else getattr(palette, found)


def default_effort():
    """His own default effort (settings.json effortLevel), so the line says "xhigh", not "default"."""
    return (read_json(os.path.join(CLAUDE_DIR, "settings.json")) or {}).get("effortLevel") or ""


def from_transcript(mode):
    """No mode record is how he always ran them (yolo); a mode it doesn't know asks, never skips (review 2)."""
    return FROM_TRANSCRIPT.get(mode, "manual") if mode else "yolo"


def flags(choice):
    """The claude flags for a choice: its mode, and a model and effort only when he picked one."""
    out = list(FLAGS.get(choice.get("mode"), FLAGS["yolo"]))
    if choice.get("model"):
        out += ["--model", choice["model"]]
    if choice.get("effort"):
        out += ["--effort", choice["effort"]]
    return out


def load():
    try:
        with open(PATH) as f:
            saved = json.load(f)
        offered = {"mode": MODES, "model": MODELS, "effort": EFFORTS}  # one it no longer offers would show as the default
        return {key: saved[key] if saved.get(key) in [c[0] for c in offered[key]] else value for key, value in DEFAULT.items()}
    except (OSError, ValueError, AttributeError):
        return dict(DEFAULT)


def save(choice):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = f"{PATH}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump({key: choice.get(key, value) for key, value in DEFAULT.items()}, f)
    os.replace(tmp, PATH)
