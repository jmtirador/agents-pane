# 8. Find runs on an index of only the searchable text

Status: accepted, 2026-10-22

## Context

Find ran `rg` over every transcript and parsed each matching line as JSON.
On his 6.4 GB of transcripts that took 5-14 s per search and pushed the list to 3-6 GB of memory, holding ~1.4 GB after (the v4.1 profiler); almost every matching byte was tool output.

## Decision

- `cockpit/search.py` keeps, per session, one line per searchable record (typed prompts, replies, recaps, titles: never tool output) in `~/.claude/agents-pane/search/<sid>.txt`, and the byte offset it has read up to in `<sid>.json`.
- Transcripts only grow, so an update reads only the bytes past the offset, whole lines only; a transcript shorter than its offset is indexed again from the start, and one that's gone leaves the index.
- Updates take a file lock; the list runs them in their own process (`python -m cockpit.search --update`), at startup and before each search, so parsing never holds the list's memory or threads; a search during the first build says its results may be partial.
- A search is `rg -i -F` over the index, read a line at a time.

## Consequences

- On his data: the first build takes ~5 s and 125 MB in its own process and leaves a 12 MB index; a search takes 15-300 ms; `bin/find-session` answers in 0.05 s warm.
- Lines over 4 MB (a file a tool wrote or read) are skipped.
