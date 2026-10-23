"""The cockpit's own small memory: the look, the sessions being watched, the days it was opened."""

import json
import os

from .sessions import CLAUDE_DIR

# a preview cockpit keeps its own, so it never counts toward his usage days or changes the real one's theme or watches
_NAME = os.environ.get("AGENTS_PANE_SESSION", "agents")
PATH = os.path.join(CLAUDE_DIR, "agents-pane", "state.json" if _NAME == "agents" else f"state-{_NAME}.json")
DEFAULT = {"theme": "neon", "watched": [], "opens": []}


def load():
    try:
        with open(PATH) as f:
            return {**DEFAULT, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULT)


def save(state):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH + ".tmp", "w") as f:
        json.dump(state, f)
    os.replace(PATH + ".tmp", PATH)


def peek_path():
    return os.path.join(os.path.dirname(PATH), f"peek-{_NAME}.json")


def write_peek(peek):
    """What the right side shows for a session it can't attach (problems G1): the welcome viewer redraws from this file.
    {"blank": True} while a running session is on the right, so the hidden peek never shows the wrong one later."""
    path = peek_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(peek, f)
    os.replace(path + ".tmp", path)


def read_peek():
    try:
        with open(peek_path()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}
