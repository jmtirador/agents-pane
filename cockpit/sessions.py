#!/usr/bin/env python3
"""Read Claude Code's own session files and describe every session as a row.

Used by the cockpit (a snapshot a second); cockpit/search.py builds find's index from the same files.
Read-only: it never writes a Claude Code file and never touches a session.
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
SESSIONS_DIR = os.path.join(CLAUDE_DIR, "sessions")
JOBS_DIR = os.path.join(CLAUDE_DIR, "jobs")
PROJECTS_DIR = os.path.join(CLAUDE_DIR, "projects")
HOME = os.path.expanduser("~")

QUIET_AFTER_S = 600  # working with no file change for 10 minutes
DONE_FOR_S = 30 * 60  # a finished session stays "done" (ice) for 30 minutes
ASKS_FOR_S = 24 * 3600  # a soft question counts for a day
TAIL_BYTES = 65_536
HEAD_BYTES = 65_536
STEPS_KEPT = 40

OFFER = re.compile(
    r"^(also,?\s*)?(want me to|want to|want (tweaks|a|the|it)|do you want me|"
    r"would you like|should i|shall i|good to (go|paste|send)|ready for me)\b",
    re.I,
)
GREETING = re.compile(r"^(hey|hi|ok|okay|so|yo|pls|please|can you|could you)\b[\s,]*", re.I)
NOISE_PROMPT = re.compile(r"^(<|Caveat|This session is being continued|\[Request interrupted)")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# what a session stuck on a permission prompt wants to do, by tool (G2)
PERMIT = {"Bash": "run", "Edit": "edit", "MultiEdit": "edit", "Write": "write", "NotebookEdit": "edit", "Read": "read", "WebFetch": "open"}


# ---------------------------------------------------------------- reading


_json_cache = {}  # path -> (mtime_ns, size, value): registry and job files change rarely


def read_json(path):
    try:
        st = os.stat(path)
        cached = _json_cache.get(path)
        if cached and cached[:2] == (st.st_mtime_ns, st.st_size):
            return cached[2]
        with open(path, encoding="utf-8") as f:
            value = json.load(f)
    except (OSError, ValueError):
        return None
    _json_cache[path] = (st.st_mtime_ns, st.st_size, value)
    return value


def read_jsonl_bytes(path, start, end):
    """Parse the JSON lines between two byte offsets, dropping a cut first line."""
    try:
        with open(path, "rb") as f:
            f.seek(start)
            lines = f.read(end - start).split(b"\n")
    except OSError:
        return []
    out = []
    for line in lines[1:] if start > 0 else lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def transcripts():
    """Every main-session transcript (subagent transcripts live one level deeper)."""
    return glob.glob(os.path.join(PROJECTS_DIR, "*", "*.jsonl"))


class TranscriptIndex:
    """Maps a session id to its transcript path, rescanning at most every 5 s."""

    def __init__(self):
        self.paths = {}
        self.scanned_at = 0.0

    def find(self, sid, hint=None):
        if hint and os.path.exists(hint):
            self.paths[sid] = hint
        elif not os.path.exists(self.paths.get(sid, "")) and time.time() - self.scanned_at > 5:
            self.scanned_at = time.time()
            self.paths = {os.path.basename(p)[:-6]: p for p in transcripts()}
        return self.paths.get(sid)


# ---------------------------------------------------------------- text helpers


def message_text(rec):
    """The plain text of a user or assistant record, or '' when it has none."""
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text" and b.get("text"))
    return ""


def is_typed_prompt(rec):
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isSidechain"):
        return False
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return False
    text = message_text(rec).strip()
    return bool(text) and not NOISE_PROMPT.match(text)


def one_line(text, limit=400):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def strip_markdown(text):
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"^\s*>.*$", " ", text, flags=re.M)
    return re.sub(r"^\s*#+\s*", "", text, flags=re.M)


def first_sentence(text, limit=240):
    """The reply's first sentence, or its first two when the first is under three words: "Done." says nothing (G5)."""
    parts = SENTENCE_END.split(strip_markdown(text).strip(), maxsplit=2)
    first = " ".join(parts[:2]) if len(parts[0].split()) < 3 else parts[0]
    return one_line(first, limit)


def ends_on_question(text):
    """The last sentence of the last paragraph when it ends in "?", offers included."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", strip_markdown(text)) if p.strip()]
    paragraphs = [p for p in paragraphs if not p.lower().startswith("shortcut hack")]
    final = SENTENCE_END.split(paragraphs[-1])[-1].strip() if paragraphs else ""
    return one_line(final, 300) if final.endswith("?") else None


def asks_question(text):
    """Rule A: the last sentence of the last paragraph is a real question, not an offer.

    Measured on 111 real endings: 3 hits, all real. "Ends with ?" was 70% false.
    """
    final = ends_on_question(text)
    return None if not final or OFFER.match(final.lstrip("-*• ")) else final


def display_name(head, path):
    """His own title, else Claude Code's first auto title (frozen), else the first words he typed."""
    title = head["customTitle"] or head["firstTitle"] or first_title_anywhere(path)
    return one_line(title, 80) or " ".join(GREETING.sub("", one_line(head["firstPrompt"], 200)).split()[:5])


def home_rel(path):
    """The path under the home folder, or the path itself when it isn't under it."""
    return path[len(HOME) + 1 :] if path.startswith(HOME + "/") else path


def tilde(path):
    return "~" if path == HOME else path if home_rel(path) == path else "~/" + home_rel(path)


def short_cwd(cwd):
    """The last two folders of where a session runs, or "" for home and ~/Projects (no hint needed)."""
    if not cwd or cwd in (HOME, os.path.join(HOME, "Projects")):
        return ""
    rel = re.sub(r"^Projects/", "", home_rel(re.sub(r"/\.claude/worktrees/[^/]+", "", cwd)))
    return "/".join(rel.split("/")[-2:])


def short_path(path):
    parts = tilde(path).split("/")
    return "/".join(parts[-2:]) if len(parts) > 3 else tilde(path)


TOOL_WHAT = {"Read": "file_path", "Edit": "file_path", "Write": "file_path", "NotebookEdit": "file_path",
             "Grep": "pattern", "Glob": "pattern", "Skill": "skill"}


def tool_step(block):
    """One line for a tool call: its own description when it has one."""
    name = block.get("name", "tool")
    inp = block.get("input") or {}
    if name.startswith("mcp__"):
        _, server, tool = (name.split("__", 2) + ["", ""])[:3]
        server = server.replace("claude_ai_", "")
        if server.startswith("plugin_"):  # plugin_<plugin>_<server>
            server = server.rsplit("_", 1)[-1]
        return (server, tool) if not UUID.match(server) else (tool, "")  # whole: the card cuts with "…" itself (G4)
    if name in TOOL_WHAT:
        what = inp.get(TOOL_WHAT[name], "")
        what = short_path(what) if TOOL_WHAT[name] == "file_path" else what
    else:
        what = inp.get("description") or inp.get("command") or inp.get("query") or inp.get("url") or inp.get("prompt", "")[:60]
    return name, one_line(what, 120)


def iso_ms(text):
    """Milliseconds since the epoch for an ISO-8601 UTC timestamp ("2026-10-07T01:47:33.467Z")."""
    try:
        return round(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)
    except (AttributeError, TypeError, ValueError):
        return None


def local_time(ms, fmt):
    return time.strftime(fmt, time.localtime(ms / 1000)) if ms else ""


# ---------------------------------------------------------------- one transcript


def read_head(path):
    """First typed prompt, first auto title, any custom title, the working folder, and the mode it started in (an SDK
    session writes it only on its first prompt, never as a permission-mode record; the second v4.2 review)."""
    head = {"firstPrompt": "", "firstTitle": "", "customTitle": "", "cwd": "", "mode": ""}
    for rec in read_jsonl_bytes(path, 0, HEAD_BYTES):
        kind = rec.get("type")
        head["cwd"] = head["cwd"] or rec.get("cwd", "")
        if kind == "user":
            head["mode"] = head["mode"] or rec.get("permissionMode") or ""
        if kind == "ai-title" and not head["firstTitle"]:
            head["firstTitle"] = rec.get("aiTitle") or ""
        elif kind == "custom-title" and not head["customTitle"]:
            head["customTitle"] = rec.get("customTitle") or rec.get("title") or ""
        elif not head["firstPrompt"] and is_typed_prompt(rec):
            head["firstPrompt"] = one_line(message_text(rec), 300)
    return head


_titles = {}  # path -> first auto title past the head, looked up once


def first_title_anywhere(path):
    """The first auto title, even when it was written past the head (long or old sessions)."""
    if path not in _titles:
        try:
            out = subprocess.run(["rg", "-m", "1", "-F", '"type":"ai-title"', path], capture_output=True, text=True, timeout=5).stdout
            _titles[path] = json.loads(out.splitlines()[0]).get("aiTitle", "") if out else ""
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            _titles[path] = ""
    return _titles[path]


def read_tail(path, size):
    """Everything a row and its preview need, from the end of the transcript."""
    return parse_tail(read_jsonl_bytes(path, max(0, size - TAIL_BYTES), size))


def mode_of(path):
    """A transcript's permission mode, the newest in its tail or else the one it started in; "" when it has none."""
    try:
        return read_tail(path, os.path.getsize(path))["mode"] or read_head(path)["mode"]
    except (OSError, TypeError):
        return ""


def parse_tail(recs):
    info = {"lastPrompt": "", "lastPromptAt": None, "lastTurnAt": None, "lastTextAt": None, "awaySummary": "", "awaySummaryAt": None,
            "error": "", "steps": [], "pendingAsk": None, "pendingTool": None, "mode": "", "customTitle": "", "endsOn": None}
    last_text, prompt_mode = "", ""
    open_asks, open_tools = {}, {}
    for rec in recs:
        kind = rec.get("type")
        at = iso_ms(rec.get("timestamp"))
        if kind == "custom-title":  # /rename and -n write it again and again, so the tail sees the newest
            info["customTitle"] = rec.get("customTitle") or info["customTitle"]
        elif kind == "permission-mode":
            info["mode"] = rec.get("permissionMode") or info["mode"]
        elif kind == "last-prompt":
            info["lastPrompt"] = one_line(rec.get("lastPrompt", "")) or info["lastPrompt"]
        elif kind == "system" and rec.get("subtype") == "away_summary":
            info["awaySummary"], info["awaySummaryAt"] = one_line(rec.get("content", "")), at
        elif kind == "user" and not rec.get("isSidechain"):
            content = (rec.get("message") or {}).get("content")
            results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"] if isinstance(content, list) else []
            for b in results:
                open_asks.pop(b.get("tool_use_id"), None)
                open_tools.pop(b.get("tool_use_id"), None)
            if not results and not rec.get("isMeta"):
                info["lastTurnAt"] = at  # a prompt, a peer message or a task notification starts a turn
            if is_typed_prompt(rec):
                info["lastPrompt"], info["lastPromptAt"], info["steps"] = one_line(message_text(rec)), at, []
                prompt_mode = rec.get("permissionMode") or prompt_mode
        elif kind == "assistant" and not rec.get("isSidechain"):
            msg = rec.get("message") or {}
            # failed means the newest assistant record is an API error; anything after it clears it
            info["error"] = one_line(message_text(rec), 200) if rec.get("isApiErrorMessage") else ""
            for b in msg.get("content") if isinstance(msg.get("content"), list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    name, what = tool_step(b)
                    info["steps"].append({"clock": local_time(at, "%H:%M"), "tool": name, "what": what})
                    open_tools[b.get("id")] = (name, what)
                    if name == "AskUserQuestion":
                        open_asks[b.get("id")] = ask_from_input(b.get("input") or {})
            if message_text(rec).strip():
                last_text, info["lastTextAt"] = message_text(rec), at
    info["pendingAsk"] = list(open_asks.values())[-1] if open_asks else None
    info["pendingTool"] = list(open_tools.values())[-1] if open_tools else None
    info["steps"] = info["steps"][-STEPS_KEPT:]
    info["itSaid"], info["asked"] = first_sentence(last_text), asks_question(last_text)  # once per change, not per tick
    info["endsOn"] = ends_on_question(last_text)  # a waiting session waits on its last question, an offer too (G2)
    info["mode"] = info["mode"] or prompt_mode  # a permission-mode record wins; the Claude app writes none (third review)
    return info


def ask_from_input(inp):
    q = (inp.get("questions") or [{}])[0]
    return {"question": one_line(q.get("question", ""), 300), "options": [one_line(o.get("label", ""), 60) for o in (q.get("options") or [])][:9]}


# ---------------------------------------------------------------- the model


class Watcher:
    def __init__(self):
        self.index = TranscriptIndex()
        self.heads = {}  # sid -> (size when read, head)
        self.tails = {}  # sid -> (size, mtime, info)

    def transcript_info(self, sid, hint=None):
        path = self.index.find(sid, hint)
        try:
            st = os.stat(path) if path else None
        except OSError:
            st = None
        if not st:
            return None, None, ""
        known = self.heads.get(sid)
        # a head with no prompt and no title yet is read again only after the file grows
        if not known or (known[0] != st.st_size and not (known[1]["firstPrompt"] or known[1]["firstTitle"])):
            self.heads[sid] = (st.st_size, read_head(path))
        cached = self.tails.get(sid)
        if not cached or cached[:2] != (st.st_size, st.st_mtime):
            cached = (st.st_size, st.st_mtime, read_tail(path, st.st_size))
            self.tails[sid] = cached
        return st, cached[2], path

    def sources(self):
        """Live sessions from the registry, plus background jobs whose process has exited."""
        found = {reg["sessionId"]: {"reg": reg, "job": {}} for reg in live_registry()}
        for state_path in glob.glob(os.path.join(JOBS_DIR, "*", "state.json")):
            job = read_json(state_path)
            if job and job.get("sessionId"):
                found.setdefault(job["sessionId"], {"reg": {}, "job": {}})["job"] = {**job, "_id": os.path.basename(os.path.dirname(state_path))}
        return found

    def snapshot(self):
        now = int(time.time() * 1000)
        found = self.sources()
        for cache in (self.heads, self.tails):  # forget sessions that are gone
            for sid in cache.keys() - found.keys():
                cache.pop(sid, None)
        return [row for sid, src in found.items() if (row := self.make_row(sid, src["reg"], src["job"], now))]

    def make_row(self, sid, reg, job, now):
        if reg.get("spare"):
            return None
        st, t, path = self.transcript_info(sid, job.get("linkScanPath"))
        head = self.heads[sid][1] if sid in self.heads else read_head("")
        t = t or parse_tail([])
        own = lambda n: n if n and n not in (sid, sid[:8], job.get("_id"), reg.get("jobId")) else ""  # noqa: E731 (an id is not a name)
        # his rename, then Claude Code's own name (what its footer and agent view say), then the first auto title (G6)
        name = one_line(t["customTitle"] or own(job.get("name")) or own(reg.get("name")), 80) or (display_name(head, path) if path else "")
        name = name or " ".join(GREETING.sub("", one_line(job.get("intent") or t["lastPrompt"], 200)).split()[:5])
        if not name:
            return None  # nothing typed yet: a warm spare or an empty chat

        alive = bool(reg)
        status = reg.get("status")
        busy = status == "busy"
        job_state = job.get("state")
        last_change = max(int(st.st_mtime * 1000) if st else 0, iso_ms(job.get("updatedAt")) or 0, reg.get("statusUpdatedAt") or 0)
        finished = finished_at(reg, job, t)
        ask = t["pendingAsk"]

        state, question = "idle", ""
        if alive and (status == "waiting" or (job.get("tempo") == "blocked" and not busy) or ask):
            # stopped on a question or a permission prompt right now
            state, question = "needs", (ask or {}).get("question") or one_line(job.get("detail", ""), 300)
        elif alive and job_state == "blocked" and not busy:
            # the supervisor says it ended its turn on a question: the soft state
            state, question = "asks", one_line(job.get("detail", ""), 300)
        elif (t["error"] and not busy) or job_state in ("failed", "error", "crashed"):
            state = "failed"
        elif alive and (busy or job_state == "working"):
            state = "quiet" if now - last_change >= QUIET_AFTER_S * 1000 else "working"
        elif job_state in ("stopped", "working"):
            state = "stopped"  # stopped, or its process exited mid-turn
        elif finished:
            if t["asked"] and now - finished <= ASKS_FOR_S * 1000:
                state, question = "asks", t["asked"]
            elif now - finished <= DONE_FOR_S * 1000:
                state = "done"

        if state == "needs" and not question:
            question = waiting_for(t)
        cwd = reg.get("cwd") or job.get("cwd") or ""
        return {
            "sid": sid,
            "jobId": job.get("_id") or reg.get("jobId"),
            "kind": "bg" if reg.get("kind") == "bg" or not reg else "interactive",
            "alive": alive,
            "state": state,
            "name": name,
            "cwd": cwd,
            "where": short_cwd(cwd),
            "startedAt": reg.get("startedAt") or iso_ms(job.get("createdAt")),
            "turnStart": (t["lastTurnAt"] or reg.get("statusUpdatedAt")) if busy else t["lastPromptAt"],
            "finishedAt": finished,
            "lastChange": last_change,
            "question": question,
            "options": (ask or {}).get("options", []),
            "detail": one_line(job.get("detail", ""), 200),
            "lastPrompt": t["lastPrompt"] or one_line(job.get("intent", ""), 300),
            "itSaid": t["itSaid"],
            "away": t["awaySummary"] if (t["awaySummaryAt"] or 0) >= (t["lastTextAt"] or 0) else "",
            "error": t["error"],
            "steps": t["steps"],
            "mode": t["mode"] or head["mode"],
            "tmux": reg.get("tmux"),
            "desktop": reg.get("entrypoint") == "claude-desktop",  # a chat in the Claude app (G3)
            "path": path,
        }


REPLY_BYTES = 262_144  # the last reply is always within this on his transcripts (the v4.1 design critic: 147 KB at most)


def last_reply(path):
    """The last thing it said, in full, for the peek: the newest assistant text in the transcript's last 256 KB."""
    try:
        size = os.path.getsize(path)
    except (OSError, TypeError):
        return ""
    text = ""
    for rec in read_jsonl_bytes(path, max(0, size - REPLY_BYTES), size):
        if rec.get("type") == "assistant" and not rec.get("isSidechain") and message_text(rec).strip():
            text = message_text(rec)
    return text


def waiting_for(t):
    """What a session waiting with no question wants: the tool call it's asking permission for, else the question it ended on (G2)."""
    if t["pendingTool"]:
        tool, what = t["pendingTool"]
        verb = f"wants to {PERMIT[tool]}" if tool in PERMIT else f"wants to use {tool}"
        return f"{verb}: {what}" if what else verb
    return t["endsOn"] or t["itSaid"]


def live_registry():
    """Registry entries whose process is still running."""
    regs = (read_json(p) for p in glob.glob(os.path.join(SESSIONS_DIR, "*.json")))
    return [r for r in regs if r and r.get("sessionId") and pid_alive(r.get("pid"))]


def finished_at(reg, job, t):
    if job.get("state") in ("done", "blocked", "stopped"):
        return iso_ms(job.get("updatedAt"))
    if reg and reg.get("status") != "busy":
        return max(reg.get("statusUpdatedAt") or 0, t["lastTextAt"] or 0) or None
    return None


def registry_warning(rows):
    """A guard against Claude Code changing its files: it lists live sessions we can't see."""
    if any(r["alive"] for r in rows):
        return ""  # we see live sessions, so the files still read right; skip the 0.1 s CLI call
    try:
        listed = json.loads(subprocess.run(["claude", "agents", "--json"], capture_output=True, text=True, timeout=10).stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    return "files changed? update the pane" if any(a.get("pid") and pid_alive(a["pid"]) for a in listed) else ""


# ---------------------------------------------------------------- search


def snippet(text, needle, width=110):
    """The match near the start, so a narrow pane that cuts the end still shows it."""
    flat = one_line(text, 100_000)
    i = flat.lower().find(needle)
    start = max(0, i - 14) if i >= 0 else 0
    end = min(len(flat), start + width)
    return ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")


def busy_days(days):
    """His local days in the last N with messages in two or more sessions (`u` compares them
    with the local days the cockpit was opened). Timestamps are UTC, so each hour is turned into a local day."""
    since = time.time() - days * 86400
    recent = [p for p in transcripts() if os.path.getmtime(p) >= since]
    if not recent:
        return []
    out = subprocess.run(["rg", "-o", "--no-line-number", "--with-filename", "-r", "$1", r'"timestamp":"(\d{4}-\d{2}-\d{2}T\d{2})', *recent],
                         capture_output=True, text=True, timeout=60).stdout
    first = time.strftime("%Y-%m-%d", time.localtime(since))
    sessions_on = {}
    for line in set(out.splitlines()):
        path, _, hour = line.rpartition(":")
        day = local_day(hour)
        if day >= first:
            sessions_on.setdefault(day, set()).add(path)
    return sorted(day for day, paths in sessions_on.items() if len(paths) >= 2)


def local_day(utc_hour):
    """'2026-10-07T03' (UTC) -> '2026-10-06' at -0500."""
    return datetime.strptime(utc_hour, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d")


# ---------------------------------------------------------------- main


def main(argv):
    parser = argparse.ArgumentParser(prog="python -m cockpit.sessions", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("snapshot")
    commands.add_parser("busydays").add_argument("days", type=int, nargs="?", default=14)
    args = parser.parse_args(argv)

    if args.command == "snapshot":
        print(json.dumps(Watcher().snapshot()))
    else:
        print(json.dumps(busy_days(args.days)))


if __name__ == "__main__":
    main(sys.argv[1:])
