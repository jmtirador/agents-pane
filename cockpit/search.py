"""Find old sessions by what they were about, from a small index of only the searchable text (problems G8).

Searching every transcript (6.4 GB on his Mac, 2026-10-22) took 5-14 s and 3-6 GB of memory, because almost every
matching line was tool output. Transcripts only grow, so the index keeps, per session, one line per searchable record
(his prompts, its replies, recaps, titles) and the byte offset it has read up to; an update reads only the new bytes.
The first build on his data took 3.8 s and left a 15 MB index. The list runs updates in their own process
(`python -m cockpit.search --update`) under a file lock, so parsing never holds the list's memory or threads.
"""

import fcntl
import json
import os
import subprocess
import sys

from . import sessions

DIR = os.path.join(sessions.CLAUDE_DIR, "agents-pane", "search")
CHUNK = 1 << 20
LONGEST = 4_000_000  # a line this big is a file a tool wrote or read, never a prompt or a reply
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def kind_and_text(rec):
    """What a search may match in one record, and what it is; tool output never counts."""
    kind = rec.get("type")
    if kind == "custom-title":
        return "name", rec.get("customTitle", "")
    if kind == "ai-title":
        return "title", rec.get("aiTitle", "")
    if kind == "system" and rec.get("subtype") == "away_summary":
        return "recap", rec.get("content", "")
    if kind == "user" and sessions.is_typed_prompt(rec):
        return "prompt", sessions.message_text(rec)
    if kind == "assistant" and not rec.get("isSidechain"):
        return "reply", sessions.message_text(rec)
    return "", ""


def paths(sid):
    return os.path.join(DIR, f"{sid}.txt"), os.path.join(DIR, f"{sid}.json")


def read_meta(sid):
    try:
        with open(paths(sid)[1]) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def index_one(path):
    """Bring one transcript's index up to date: only the bytes past what was read, whole lines only."""
    sid = os.path.basename(path)[: -len(".jsonl")]
    txt, meta_path = paths(sid)
    meta = read_meta(sid)
    st = os.stat(path)
    if meta.get("path") != path or st.st_size < meta.get("offset", 0):  # moved, or rewritten shorter: start over
        meta = {"path": path, "offset": 0}
        open(txt, "w").close()
    offset = meta["offset"]
    if st.st_size == offset:
        return
    with open(path, "rb") as f, open(txt, "a", encoding="utf-8", errors="replace") as index:  # a cut emoji is a lone surrogate
        f.seek(offset)
        rest = b""
        while offset + len(rest) < st.st_size:
            block = f.read(min(CHUNK, st.st_size - offset - len(rest)))
            if not block:
                break
            data = rest + block
            cut = data.rfind(b"\n")
            if cut < 0:
                rest = data
                continue
            whole, rest = data[: cut + 1], data[cut + 1 :]
            offset += len(whole)
            out = []
            for line in whole.split(b"\n"):
                if not line or len(line) > LONGEST or b'"type":"tool_result"' in line:  # most of the bytes, never searchable
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not meta.get("cwd"):
                    meta["cwd"] = rec.get("cwd") or ""
                kind, text = kind_and_text(rec)
                text = sessions.one_line((text or "").replace("\x00", " "), 100_000)  # a NUL makes rg skip the file as binary
                if not text:
                    continue
                if kind == "name":
                    meta["name"] = text
                elif kind == "title":
                    meta.setdefault("title", text)
                elif kind == "prompt":
                    meta.setdefault("first", text[:200])
                out.append(f"{sessions.iso_ms(rec.get('timestamp')) or 0}\t{kind}\t{text}\n")
            index.writelines(out)  # a chunk at a time, so a 100 MB transcript never sits in memory
    meta.update(offset=offset, mtime=st.st_mtime)
    with open(meta_path + ".tmp", "w") as f:
        json.dump(meta, f)
    os.replace(meta_path + ".tmp", meta_path)


def update(block=True):
    """Index every transcript's new bytes and drop sessions whose transcript is gone. False when another update
    holds the lock and block is False (the list then searches what's there and says it's still indexing)."""
    os.makedirs(DIR, exist_ok=True)
    lock = os.open(os.path.join(DIR, ".lock"), os.O_CREAT | os.O_RDWR)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | (0 if block else fcntl.LOCK_NB))
        except BlockingIOError:
            return False
        seen = set()
        for path in sessions.transcripts():
            seen.add(os.path.basename(path)[: -len(".jsonl")])
            try:
                index_one(path)
            except Exception:  # noqa: BLE001 (gone mid-read, or something odd in it: one transcript never stops the rest)
                continue
        for name in os.listdir(DIR):
            sid, ext = os.path.splitext(name)
            if ext in (".txt", ".json") and sid not in seen:
                os.remove(os.path.join(DIR, name))
        return True
    finally:
        os.close(lock)


def update_elsewhere(wait=True):
    """The same update in its own process, as the list runs it; True when the index is complete."""
    run = subprocess.run if wait else subprocess.Popen
    done = run([sys.executable, "-m", "cockpit.search", "--update"], cwd=ROOT, stdin=subprocess.DEVNULL,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, "PYTHONPATH": ROOT})
    return wait and done.returncode == 0


def display(meta, sid):
    """His title, else Claude Code's first auto title, else the first words he typed (sessions.display_name's order)."""
    if meta.get("name") or meta.get("title"):
        return meta.get("name") or meta["title"]
    words = " ".join(sessions.GREETING.sub("", meta.get("first", "")).split()[:5])
    return words or sid[:8]


def find(query, limit=20, refresh=update):
    """Sessions whose prompts, titles, recaps or replies mention the query, newest first. refresh brings the index up to
    date first and returns False when it couldn't (another update is running): the results come back marked partial."""
    q = query.strip()
    if not q:
        return []
    complete = refresh() is not False
    needle = q.lower()
    hits = {}
    rg = subprocess.Popen(["rg", "-i", "-F", "--no-heading", "--with-filename", "--glob", "*.txt", "-e", q, DIR],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    for line in rg.stdout:  # a line at a time: "the" matches most of the index, which needn't sit in memory
        path, sep, rest = line.rstrip("\n").partition(".txt:")
        at, _, rest = rest.partition("\t")
        _, _, text = rest.partition("\t")
        if not sep or needle not in text.lower():
            continue
        at = int(at) if at.isdigit() else 0
        hit = hits.setdefault(os.path.basename(path), {"at": -1})
        if at > hit["at"]:
            hit.update(at=at, snippet=sessions.snippet(text, needle))
    rg.wait()
    results = []
    for sid, hit in hits.items():
        meta = read_meta(sid)
        at = hit["at"] if hit["at"] > 0 else int(meta.get("mtime", 0) * 1000)  # a match only in a title takes the file's date
        results.append({"sid": sid, "name": display(meta, sid), "snippet": hit["snippet"], "at": at,
                        "date": sessions.local_time(at, "%-m/%-d"), "cwd": meta.get("cwd", ""), "partial": not complete})
    return sorted(results, key=lambda r: r["at"], reverse=True)[:limit]


if __name__ == "__main__":
    if sys.argv[1:] == ["--update"]:
        sys.exit(0 if update(block=False) else 3)
    sys.exit("usage: python -m cockpit.search --update")
