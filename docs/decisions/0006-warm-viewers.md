# 6. Warm viewers, swapped into the right side

Status: accepted, 2026-10-14 (replaces the live.py supervisor from 0001; 0001's rule against respawn-pane stands)

## Context

Pepe called v3 "very slow" and "hard to click on chats" (docs/problems.md, F1).
The latency profiler measured the list at 6-40 ms but every switch at ~0.56 s with a blank flash: a 0.3 s wait, then live.py killed the old `claude attach`, reset the pane and started a new one.
Claude Code also stops a finished or waiting session's process after about an hour unattached, so the next attach boots it again ("A session is slow to respond after attaching", code.claude.com/docs/en/agent-view).
The reference scout found that every fast tool (Agent of Empires, Claude Squad, Agent Deck) keeps each session's viewer running and switches the screen to it; none restarts the viewer per pick.

## Decision

- Each session he looks at gets a viewer: a pane running `python -m cockpit.viewer <job>`, which runs `claude attach <job>`.
  Hidden viewers live in a separate detached tmux session, `<session>-viewers`, so `next-window` and the status bar's wheel bindings can't land on one.
- Showing a session swaps its viewer into the cockpit's right side with `swap-pane -Z -d` (`-Z` keeps a dialog's zoom).
  A probe did 400 swaps on tmux 3.7c in 1.6 s (4 ms each) with no crash; a swapped-in viewer repaints cleanly in about 80 ms.
- The right side is the viewer in the cockpit window, read from tmux each time (`list-panes -a`), never a cached pane id (the id there changes with every swap) and never `{right}`: while a dialog zooms the list, tmux counts only the zoomed pane, so `{right}` is the list itself and a swap hid it (found by the stress test).
  Every viewer carries `@ap_role=live` and `@ap_job=<job>`; the right side's `@ap_job` is the one record of what is showing.
- Inside an attach, `←`, `/exit` and Ctrl+C twice don't exit: the same process turns into `claude agents`, Claude's own session list (checked on Claude Code 2.1.300 with a throwaway session); only Ctrl+Z exits.
  So each viewer reads its attach's command line every 0.3 s (sysctl, ~0.03 ms) and closes it once it says `claude agents`; the list on the left is his session list. It matches only that title, so a Claude update that names its processes differently stops the watch instead of killing healthy attaches.
- A viewer's loop reattaches after the attach ends only when he left it (it ran over 1.5 s) and the job's `state.json` still exists and isn't stopped; otherwise it parks with a short message and waits to be closed.
  It moves the keys back to the list only when it is the cockpit's active pane.
  It catches every error and parks instead of ending, because a closed right side leaves the list alone in the window.
  It leaves SIGHUP alone, so it dies with its pane.
- Moving the cursor shows a viewer only for a session whose process runs: an attach starts a stopped or sleeping session, so passing over one shows a note instead, and Enter or a click starts it on purpose.
- First built, a viewer he typed into was closed when swapped out, so one drifted through Claude's own list could never come back under the wrong card; the command-line watch makes drift impossible, and the stress test showed the rule cost a fresh attach for 12 of 20 clicks, so it was dropped.
- At most 4 hidden viewers stay warm; one he hasn't seen for 15 minutes (stamped when it's swapped in and out) is closed, and all hidden ones close when he closes the dashboard (`client-detached`).
  One idle attach measured 144 MB and no CPU.
- The welcome screen is the viewer `welcome`; when it starts a session it retags itself with the new job and attaches in place.
  `bin/agents-pane "prompt"` uses the same create-or-swap helper.
- A pane is closed only when it isn't in the cockpit window (`if-shell -F '#{!=:#{window_name},cockpit}'`), so a race can't close the right side.
- A cockpit from before 4.0.0 (its right side has no `@ap_job`) is rebuilt by the launcher, so upgrading is running `yolo` again.

## Alternatives considered

- Keep restarting `claude attach` with no wait: ~0.27 s and still a blank flash, and old sessions still boot from scratch.
- `switch-client` to a per-session tmux session (Agent of Empires): instant, but the list disappears while he's in a session.
- Rewrite in Rust: the profiler found nothing a language change would fix except ~85 ms of cold start.

## Consequences

- Viewers are separate processes the list must keep tidy: one per job, found from tmux (never from the list's memory), capped and timed out.
- Two tmux clients at different sizes on one Claude session garble it; after `r` (which types through a hidden window) the right side is nudged to repaint.
- 0001's rule that the right side's process must never exit now applies to every viewer.
