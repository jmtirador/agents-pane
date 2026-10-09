"""Where the cockpit keeps its memory."""

import importlib

from cockpit import store


def test_a_preview_cockpit_keeps_its_own_memory(monkeypatch):
    # a preview must not count toward the kill rule, or change the real cockpit's theme or watches
    monkeypatch.setenv("AGENTS_PANE_SESSION", "agents-preview")
    preview = importlib.reload(store).PATH
    monkeypatch.setenv("AGENTS_PANE_SESSION", "agents")
    real = importlib.reload(store).PATH
    monkeypatch.undo()
    importlib.reload(store)
    assert real.endswith("/agents-pane/state.json")
    assert preview.endswith("/agents-pane/state-agents-preview.json")
