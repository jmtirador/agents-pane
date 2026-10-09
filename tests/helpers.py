"""Shared test data: a session row with every field the cockpit reads, at a fixed moment."""

import os

NOW = 1_800_000_000_000


def row(sid, state="idle", **extra):
    base = {"sid": sid, "jobId": sid[:8], "kind": "bg", "alive": True, "state": state, "name": sid,
            "cwd": os.path.expanduser("~/Projects/finch"), "where": "finch", "startedAt": NOW - 60_000, "turnStart": NOW - 30_000,
            "finishedAt": None, "lastChange": NOW - 10_000, "question": "", "options": [], "detail": "", "lastPrompt": "",
            "itSaid": "", "away": "", "error": "", "steps": [], "ctx": 0, "mode": "", "tmux": None}
    return {**base, **extra}
