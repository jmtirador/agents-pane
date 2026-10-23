"""Find on a small index of only the searchable text (problems G8: 5-14 s and 3-6 GB per search on his 6.4 GB)."""

import fcntl
import json
import os

import pytest

from cockpit import search, sessions


def rec(kind, text="", at="2026-10-20T15:00:00.000Z", **extra):
    if kind == "prompt":
        return {"type": "user", "timestamp": at, "cwd": "/Users/x/Projects/finch", "message": {"content": text}}
    if kind == "reply":
        return {"type": "assistant", "timestamp": at, "message": {"content": [{"type": "text", "text": text}]}}
    if kind == "tool":
        return {"type": "user", "timestamp": at, "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": text}]}}
    if kind == "recap":
        return {"type": "system", "subtype": "away_summary", "timestamp": at, "content": text}
    if kind == "title":
        return {"type": "ai-title", "aiTitle": text}
    if kind == "name":
        return {"type": "custom-title", "customTitle": text}
    return {"type": kind, **extra}


@pytest.fixture
def box(tmp_path, monkeypatch):
    projects = tmp_path / "projects" / "-x"
    projects.mkdir(parents=True)
    monkeypatch.setattr(sessions, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(search, "DIR", str(tmp_path / "index"))

    def write(sid, *recs, mode="w"):
        path = projects / f"{sid}.jsonl"
        with open(path, mode) as f:
            f.writelines(json.dumps(r) + "\n" for r in recs)
        return path

    return write


def test_it_finds_prompts_replies_recaps_and_titles_but_never_tool_output(box):
    box("s1", rec("name", "invoice work"), rec("prompt", "fix the invoice export"), rec("tool", "secret invoice dump"),
        rec("reply", "The CSV export is fixed.", at="2026-10-20T16:00:00.000Z"), rec("recap", "Shipped the export fix."))
    hits = search.find("export")
    assert [(h["sid"], h["name"], h["cwd"]) for h in hits] == [("s1", "invoice work", "/Users/x/Projects/finch")]
    assert "export" in hits[0]["snippet"] and not hits[0]["partial"]
    assert search.find("secret") == []  # tool output never counts


def test_an_update_reads_only_new_whole_lines(box):
    path = box("s1", rec("prompt", "first question"))
    search.update()
    first = search.read_meta("s1")["offset"]
    with open(path, "a") as f:
        f.write(json.dumps(rec("reply", "a later answer about pelicans")) + "\n" + '{"type":"assistant","message":{"content":[{"type":"text","text":"half wri')
    search.update()
    meta = search.read_meta("s1")
    assert first < meta["offset"] < os.path.getsize(path)  # the half-written line waits for its newline
    assert [h["sid"] for h in search.find("pelicans")] == ["s1"]
    assert open(search.paths("s1")[0]).read().count("first question") == 1  # nothing read twice


def test_a_rewritten_transcript_is_indexed_again(box):
    box("s1", rec("prompt", "old words about llamas"), rec("reply", "a long reply " * 20))
    search.update()
    box("s1", rec("prompt", "new words"))  # shorter than what was indexed: rewritten
    assert search.find("llamas") == [] and [h["sid"] for h in search.find("new words")] == ["s1"]


def test_a_deleted_transcript_leaves_the_index(box):
    path = box("s1", rec("prompt", "about otters"))
    search.update()
    os.remove(path)
    search.update()
    assert search.find("otters") == [] and not os.path.exists(search.paths("s1")[0])


def test_newest_first_and_a_title_match_takes_the_file_date(box):
    box("old", rec("prompt", "kiwi plan", at="2026-10-01T15:00:00.000Z"))
    box("new", rec("prompt", "kiwi tasting", at="2026-10-21T15:00:00.000Z"))
    box("titled", rec("title", "Kiwi pricing"))
    hits = search.find("kiwi")
    assert [h["sid"] for h in hits][:2] in (["titled", "new"], ["new", "titled"]) and hits[-1]["sid"] == "old"
    assert next(h for h in hits if h["sid"] == "titled")["at"] > 0


def test_a_search_during_another_update_says_it_is_partial(box):
    box("s1", rec("prompt", "about herons"))
    search.update()
    os.makedirs(search.DIR, exist_ok=True)
    held = os.open(os.path.join(search.DIR, ".lock"), os.O_CREAT | os.O_RDWR)
    fcntl.flock(held, fcntl.LOCK_EX)
    try:
        assert search.update(block=False) is False
        hits = search.find("herons", refresh=lambda: search.update(block=False))
        assert [h["sid"] for h in hits] == ["s1"] and hits[0]["partial"]
    finally:
        os.close(held)


def test_one_bad_record_never_stops_the_index(box):  # review 3: a cut emoji (a lone surrogate) stopped every update
    box("a1", rec("prompt", "broken \ud83d emoji about zebras"))
    box("b2", rec("prompt", "fine words about zebras"))
    search.update()
    assert {h["sid"] for h in search.find("zebras")} == {"a1", "b2"}


def test_a_nul_character_does_not_hide_a_session(box):  # review 4: rg skipped the file as binary
    box("s1", rec("prompt", "a \u0000 in here"), rec("prompt", "about giraffes"))
    search.update()
    assert [h["sid"] for h in search.find("giraffes")] == ["s1"]


def test_a_record_with_no_title_text_is_skipped(box):  # second pass: the NUL fix choked on {"aiTitle": null}
    box("s1", {"type": "ai-title", "aiTitle": None}, rec("prompt", "about okapis"))
    search.update()
    assert [h["sid"] for h in search.find("okapis")] == ["s1"]
