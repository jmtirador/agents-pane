"""Pure rules for the cockpit: who comes first, which color a project gets, how ages read.

No I/O here, so every rule in SPEC.md can be tested without tmux or a session.
"""

import hashlib
import os

from .sessions import home_rel, short_cwd
from .theme import HOME_COLOR, PROJECT_COLORS, SPARE_COLORS

COMPACT_AT = 970_000  # his three auto-compactions fired at 966,885 / 968,068 / 972,520

BAND = {"needs": 1, "asks": 1, "failed": 1, "working": 2, "quiet": 2, "done": 3, "idle": 4, "stopped": 4}
BAND_LABEL = {1: "Waiting for you", 2: "Working", 3: "Done", 4: "Idle"}
GLYPH = {"needs": "?", "asks": "?", "failed": "✗", "working": "●", "quiet": "●", "done": "✓", "idle": "∙", "stopped": "○"}


def band(row):
    return BAND[row["state"]]


def fresh_order(rows):
    """Who needs you first: oldest ask on top, running jobs in start order, newest finish first."""
    def key(r):
        b = band(r)
        if b == 1:
            return (10 + (r["state"] == "failed"), r.get("finishedAt") or r["lastChange"], r["sid"])
        if b == 2:
            return (20, r.get("startedAt") or 0, r["sid"])
        if b == 3:
            return (30, -(r.get("finishedAt") or 0), r["sid"])
        return (40, -r["lastChange"], r["sid"])
    return [r["sid"] for r in sorted(rows, key=key)]


def stable_order(rows, previous, selected):
    """The selected row keeps its place while everything else re-sorts (htop's stable mode), but never leaves its band."""
    order = fresh_order(rows)
    if selected not in order or selected not in previous:
        return order
    bands = {r["sid"]: band(r) for r in rows}
    mine = bands[selected]
    order.remove(selected)
    start = next((i for i, s in enumerate(order) if bands[s] >= mine), len(order))
    end = next((i for i, s in enumerate(order) if bands[s] > mine), len(order))
    order.insert(max(start, min(previous.index(selected), end)), selected)
    return order


def visible(rows, order, show_quiet, selected):
    """Rows in display order, with quiet ones folded away unless shown or selected."""
    by_sid = {r["sid"]: r for r in rows}
    ordered = [by_sid[s] for s in order if s in by_sid] + [r for s, r in by_sid.items() if s not in order]
    shown = [r for r in ordered if band(r) < 4 or show_quiet or r["sid"] == selected]
    quiet = [r for r in ordered if r not in shown]
    return shown, quiet


def counts(rows):
    """What the title shows: waiting on him right now, working (quiet included), and done."""
    out = {"needs": 0, "working": 0, "done": 0}
    for r in rows:
        state = "working" if r["state"] == "quiet" else r["state"]
        if state in out:
            out[state] += 1
    return out


def project_color(cwd):
    """A color per project folder, the same every time."""
    if not short_cwd(cwd):  # home and ~/Projects
        return HOME_COLOR
    rel = home_rel(cwd)
    for prefix, color in PROJECT_COLORS:
        if rel.startswith(prefix):
            return color
    top = "/".join(rel.split("/")[:2])
    return SPARE_COLORS[int(hashlib.md5(top.encode()).hexdigest(), 16) % len(SPARE_COLORS)]


def age(ms, now):
    if not ms:
        return ""
    s = max(0, round((now - ms) / 1000))
    if s < 60:
        return f"{s}s"
    m = s // 60
    if m < 60:
        return f"{m}m"
    h = m // 60
    return f"{h}h" if h < 48 else f"{h // 24}d"


def row_age(row, now):
    if row["state"] == "working":
        return age(row.get("turnStart") or row.get("startedAt"), now)
    if row["state"] in ("quiet", "idle", "stopped"):
        return age(row["lastChange"], now)
    return age(row.get("finishedAt") or row["lastChange"], now)


def second_line(row):
    """What the card says under the name: the question, the live activity, or where it left off."""
    if row["state"] in ("needs", "asks"):
        return row["question"] or row["detail"]
    if row["state"] == "failed":
        return row["error"] or row["itSaid"]
    if row["state"] in ("working", "quiet"):
        last = row["steps"][-1] if row["steps"] else None
        detail = row["detail"]
        if detail.startswith(("/", "~/")):  # a bare file path says less than its name
            detail = os.path.basename(detail.rstrip("/")).replace("\\ ", " ")
        return detail or (f"{last['tool']} {last['what']}" if last else "thinking")
    return row["away"] or row["itSaid"] or row["detail"] or row["lastPrompt"]


def ctx_pct(row):
    return round(row["ctx"] / COMPACT_AT * 100) if row.get("ctx") else 0
