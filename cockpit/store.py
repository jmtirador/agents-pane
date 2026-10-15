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
