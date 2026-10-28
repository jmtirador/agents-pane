# agents-pane spec (the cockpit; v2 2026-10-06, v3 2026-10-08, v4 2026-10-14, v4.1 2026-10-22)

The single source of truth for the build.
Every review and the drift audit check against this file.
v1 was a docked side pane inside one chat; Pepe rejected it on 2026-10-06 ("no color", "not bold", "just a side pane", "wrap Claude Code").
On the plan page he picked: shape A (full-screen cockpit), the Neon look, and all twelve features.

## v4.1 (2026-10-22)

A week after v4 Pepe said it "doesnt seem to be taht good" and asked for more bugs, slowdowns and improvements.
Three read-only agents worked on his real data: a bug hunter rendered every card against his files, a profiler measured his live dashboard and his 6.4 GB of transcripts, and a UX adversary walked his day against Claude Code's agent view and three other tools.
The finding that mattered: 17 of his 20 sessions weren't running, and for those the right side showed only the logo; v4's speed work served the other 3.
`docs/problems.md` (G1-G13) holds each problem and its check; a design critic attacked the plan before the build.

- The right side peeks at any session it can't attach: what he asked, its last reply, its recap, the keys that work (decision 0007).
- Find runs on a small index of only the searchable text: 15-300 ms instead of 5-14 s, and the list stays small (decision 0008).
- Cards say what his real sessions are doing: what a permission prompt wants, tools in words, Claude Code's own names, two lines for a working card.
- One arrow press switches at once; nothing pulses while nobody is looking.

**Not doing without his say.** A "Left open" band for sessions that ended on a question at any age, number keys that answer a question's choices from the list, and a pin that keeps a session attached.

## v4 (2026-10-14)

On 2026-10-14 Pepe said v3 was slow, unintuitive and hard to click, had no way to close, and that Ctrl+C "just closes the claude window".
`docs/problems.md` (F1-F9) holds each complaint with the check that closes it.
Before the build, a latency profiler, an interaction auditor, a reference scout (Agent of Empires, Claude Code's agent view, Claude Squad, Agent Deck) and a design critic pinned each one to its cause.

- Speed: each session he looks at keeps a warm viewer, so going back to it is a 4 ms tmux swap instead of a fresh `claude attach` (decision 0006).
- One "current" session: the cursor's card is always what the right side shows, or a note saying where that session is.
- One click on a card opens it; `q` or Ctrl+C in the list closes the dashboard; leaving Claude from inside it brings the same session back and the keys back to the list.
- Stopping and deleting take a capital letter pressed twice (`S S`, `X X`), so a reply typed into the list by mistake can't stop a session.
- Cards say what he needs: how long a session has waited, its whole question and its choices, what a working one is doing in words.

**Not doing.**
- No rewrite in another language: the profiler found nothing it would fix beyond ~85 ms of cold start.
- Nothing inside Claude Code's own screen changes, and v3's look stays.

v3 (2026-10-08) made the frame quiet and matched his terminal; its problems (P1-P7, B1-B4) are all closed.

## Theme and contract

The cockpit holds Pepe's open loops so he can leave them open, and it wraps Claude Code instead of sitting beside it.
He runs 2-6 sessions at once, checks on them from other chats, and searches old ones by what they were about.
He leaves loops open on purpose, so it never asks him to close, clear or confirm anything.

Contract: the glyph is what a file proves, the order is who needs you first, the right side is the real session.

## Rules

1. True with zero upkeep: every card comes from files Claude Code already writes.
2. Never claim a state the data can't back; show the real last line and its age.
3. Color for meaning (rewritten for v3, 2026-10-08): the frame is quiet and matches his terminal, color stays on every state and project, and the one loud thing is a session waiting for him, whose text pulses orange (2026-10-09: no more solid card). Never gray it out: v1 was rejected for "no color", v2 for being "the tiniest bit too loud".
4. Nothing destructive on one key: stopping takes `S` twice, removing takes `X` twice, both within 2 s, so no lowercase letter typed into the list by mistake can stop or delete a session.
5. Nothing to clear: finished cards fade by age, with no seen/unseen ritual.
6. Built to delete: a thin layer over files, tmux and the `claude` CLI, with one small state file.
7. Never re-create a tmux pane while it runs (see "Learned by running it"); panes move with `swap-pane` instead (decisions 0001 and 0006).

## Where it lives

- `~/Projects/agents-pane`, a Python package `cockpit` run from the project's own `.venv` (Textual is the one dependency).
- `yolo` runs `bin/agents-pane`, which opens (or reattaches) the tmux session `agents`, window `cockpit`.
- `yolo "prompt"` also starts a background session in the current folder with that prompt and shows it live.
- `yolo --flag …` still runs a plain `claude --dangerously-skip-permissions` chat, the old way.
- Closing the dashboard (`q` or Ctrl+C in the list, or detaching tmux) keeps every session running, so the next `yolo` is instant; opened from inside another tmux session, it goes back to that one.

## Layout

- Two panes tagged by the pane option `@ap_role`: `list` (42 columns, kept by a `window-resized` hook) and `live`, the right side, whichever viewer is swapped in (see "The right side").
- The terminal paints the background everywhere (decision 0002); the window and the bar ask for `bg=default`, and the list's empty space is Textual's `ansi_default`.
- tmux draws one single-line divider in the frame gray (`line`), the same color whichever side has focus, plus one plain line across both sides over the key bar (`pane-border-status bottom` with an empty format), and nothing else: no pane titles, no indicators (decision 0003 and its amendment).
- The list's first box is its own header: a thin rounded box named `agents` (bold while the list has focus) saying `N waiting` in bold orange, `N working` in the work color and `N done` in the done color, in words, or `nothing running`.
- Each band is a thin rounded box in the frame gray with its name in the top line in the band's color (`╭─ Working ───╮`), like the dialogs; its cards sit inside.
- Boxes mean "a group": single cards, the idle line, the find line and the Claude side are never boxed.
- The bottom bar is quiet text, never chips: each key in the theme's key color and what it does in gray, three spaces apart, and the clock on the right; the only bold is `N waiting for you` on the Claude side.
- In the list the bar says `↑↓ pick   enter open   n new   / find   t theme   ? all keys   q close`; on the Claude side it says `ctrl+] back to your sessions   close`, plus `N waiting for you` on the right when anything waits.
- A double or triple click in the cockpit goes straight to the app (tmux's own selects the pane first, which took the keys back from the session a click had just opened); elsewhere they do what tmux does.
- Every key in the bar is clickable; a click presses that key in the list (`ctrl+]` sends F12, because a `]` can't be in a click range name, and the Claude side's `close` sends `q`).
- The list's first row, under the header, is ` + new chat` with `n` on the right: the cursor can rest on it like a card, and then the right side shows the new chat (see below).
- The list's last row is ` / find an old session`, which opens find when clicked.
- While Claude has the keys the list dims: the header and band titles go gray, nothing is bold except the waiting card and the header's waiting count, project colors fade halfway to the background; a waiting card keeps pulsing, and the cursor's card keeps its lighter background, since it is the session on the right.
- While a dialog is open the list pane zooms to the whole window, the bar shows that dialog's own keys (`enter send`, `esc cancel` and so on), and the space goes back after.
- Dialogs and their inputs are rounded lines in the frame gray with no fill, like Claude Code's prompt box, on the terminal's own background; the focused input's line is in the key color.
- While any dialog is open the list sets `@ap_dialog` on its session (with the dialog's keys in the bar), and Ctrl+] waits for it to close, zoomed or not.
- Toasts sit at the top of the list and go away after 3 s (at the bottom they covered the last cards and ate clicks); they span the list's width so they don't wrap (a title line, then the message), in the same thin rounded line (the warning and error ones in their state color).

## The right side (decision 0006)

- Each session he looks at gets a viewer: a pane running `python -m cockpit.viewer <job>`, which runs `claude attach <job>` and carries `@ap_role=live` and `@ap_job=<job>`.
- Showing a session swaps its viewer into the right side with `swap-pane -Z -d`; a session with no viewer yet gets one first.
  Hidden viewers wait in a detached tmux session, `<session>-viewers`, out of reach of `next-window` and the status bar.
- The right side is the viewer in the cockpit window, read from tmux each time (never `{right}`, which is the list itself while a dialog zooms it), and its `@ap_job` is the one record of what it shows; the list reads it on the same thread that sends its own swaps, and a change it didn't ask for makes the list follow.
- The cursor's card is always what the right side shows: at once for a single move, 0.12 s after a run of moves settles (or when it would start a new viewer), also from the first screen and when the cursor moves because a card went away.
- A session it can't attach (a background session whose process isn't running, a chat in another tmux window, terminal tab or the Claude app, an ended chat) gets a peek instead (decision 0007): its name in its project's color, its state and age ("finished 2h ago", "waiting 44h"), its folder, the question and choices it waits on, what it's doing now, "You asked" (the last prompt), "It said" (the last reply as rendered Markdown, cut to fit), its recap, where it is, and only the keys that work for it (`enter start it again here`, `r reply`, `enter switch there`, none for the Claude app). Nothing starts or attaches.
- When he leaves a session from inside Claude (Ctrl+C twice, `←` or `/exit` turn the attach into Claude's own session list, `claude agents`; Ctrl+Z ends it), the viewer closes what's left, attaches the same session again and gives the keys back to the list; a session that was stopped or removed, or an attach that keeps failing, leaves the viewer parked with a short message instead.
- A viewer never ends on its own: any error parks it with a message, because a closed right side would leave the list alone in the window.
- The right side takes the keys only while no dialog is open (tmux checks the zoom and `@ap_dialog` itself), so a session that starts under a dialog shows without un-zooming it.
- At most 4 hidden viewers stay warm, one he hasn't seen for 15 minutes is closed, and closing the dashboard closes them all (`client-detached`).
- A cockpit from before 4.0.0 is rebuilt the next time `yolo` runs.
- A pane is closed only when it isn't in the cockpit window, so a race can't close the right side.
- The peek is drawn by the viewer `welcome` from a file the list writes (`store.write_peek`), checked with a stat 20 times a second; it has no input: typing shows a hint and does nothing, Enter or `r` pressed on their own act on the card through the list, and Esc, Tab or an arrow give the keys back. Swapping a running session in blanks the peek behind it.
- If the right side ever dies, the next switch builds a new one beside the list (`split-window`; nothing is re-created in place).
- The new chat (problems H1-H3, after OpenCode's home screen) is the same viewer, shown while the cursor is on `+ new chat` and when there are no sessions: the AGENTS wordmark fading from the theme's own color to the key color (kept on purpose: he called it "awesome"), then one chat box at most 72 columns wide.
  The box is OpenCode's: a heavy bar in the mode's color on the terminal's background, a raised panel one step lighter (the cursor card's color) holding the text and a line `Mode · model · effort` on the left with the folder and its git branch on the right, and a half-height bottom edge (`╹▀▀▀`).
  Under it one quiet line names the keys that work right now (`tab mode   ctrl+l model   ctrl+t effort   ctrl+f folder`, or the picker's keys while it is open), and a failed start says why there, keeping the text; so does a folder that's gone (the old form refused it too; `claude` would have started in `~`).
  On a short pane the wordmark goes first, then the hints; the box always stays.
- Enter starts `claude --bg` in that folder with the mode's flags (`--dangerously-skip-permissions` for Yolo, `--permission-mode auto|plan|acceptEdits|manual` for the rest) and `--model`/`--effort` only when picked; the viewer then attaches the new session in place, with the keys.
  The mode, model and effort are saved to `~/.claude/agents-pane/new-chat.json` once a session really starts, and the next new chat begins with them; a session brought back keeps its own mode from its transcript.

## Data (measured 2026-10-06)

| Source | What | Cost |
|---|---|---|
| `~/.claude/sessions/<pid>.json` | registry: sessionId, cwd, startedAt, kind, status (idle, busy, waiting, shell), statusUpdatedAt, tmux pane, spare | cached by mtime |
| `~/.claude/jobs/<id>/state.json` | background jobs: state, tempo, the live `detail` line, intent, updatedAt | cached by mtime |
| the last 64 KB of each transcript | permission mode, last prompt, its own title, recap, last reply, steps, pending AskUserQuestion, API errors | read only when the file changed |
| find's index, `~/.claude/agents-pane/search/` (decision 0008) | one line per typed prompt, title (his own too), recap and reply, per session, and the byte offset read so far | first build ~5 s, then new bytes only; a search 15-300 ms |
| `claude agents --json` | a guard against Claude Code changing its files, run every 30 s only while no live session is visible | 0.1 s |

The list takes a snapshot every second in a worker thread.
A name set with `/rename` or `-n` is re-written into the transcript, so the tail picks up the newest one.

## States

| State | Proof | Look | Band |
|---|---|---|---|
| needs you | alive, and registry `status=="waiting"`, or job `tempo=="blocked"` while not busy, or an AskUserQuestion with no answer in the tail | `?`, the name and the question in orange, pulsing each spinner frame; no fill | 1 |
| asks | alive and job `state=="blocked"` while not busy, or finished within 24 h and rule A holds | `?` in the loud color | 1 |
| failed | the newest assistant record is an API error (a later record clears it), or a job failed state | `✗` and the error line in the fail color | 1 |
| working | alive, and registry `busy` or job `state=="working"`; its age counts from the message that started the turn | `●` in the work color, pulsing between bright and dim | 2 |
| quiet | working with no file change for 10 minutes | `●` in the quiet color | 2 |
| done | finished within 30 minutes | `✓` in the done color | 3 |
| stopped | job `state=="stopped"`, or a job whose process exited mid-turn | `○` gray | 4 |
| idle | everything else | `∙` gray | 4 |
| hidden | spare workers and chats with nothing typed yet | none | none |

Band labels, in words: `Waiting for you` (1), `Working` (2), `Done` (3), `Idle` (4).

Rule A: after stripping code, quotes and the "Shortcut hack" paragraph, the last sentence of the last paragraph ends in `?` and doesn't open with an offer phrase.
Ordering: band 1 oldest ask first (failed after asks), band 2 by start time, band 3 newest finish first, band 4 newest activity first.
The selected card keeps its place while others re-sort, and it never folds away.
A redraw never scrolls the list on its own: a cursor card he can see stays in view when cards move, one he scrolled away from stays away, and moving the cursor (even onto the card it's on) brings it into view.
When the selected session disappears, the card that slid into its place is selected.

## Cards

- Waiting, asking, failed and working sessions get a card on a background one step lighter than the terminal (#2c313c on #282c34), with a blank row between cards where the terminal shows through; a click on that row opens the card below it.
- Done and idle sessions get one line each with no fill and no gaps (design B, his pick on 2026-10-09): stripe, mark, name, a few words of the recap if they fit (never a lone `…`), the watch mark `◉` and `↗` like a card, and the age.
- The first line: a stripe in the project's color, the glyph, the name, the watch mark `◉`, `↗` for a chat in some other window, and on the right how long: `waiting 4m` (needs you), `asked 4m ago`, `failed 4m ago`, or the plain age.
- Under it: the whole question on up to 3 lines and its numbered choices on one more (needs you, asks), the error on up to 2 lines (failed), `no output for 12m` (quiet), up to two lines of what it's doing in words (working: "editing app.py", "messaging another session"; a bare file path shows its file name), else the recap, the reply's first sentence (two when the first is under three words) or the last prompt.
- A session waiting on a permission prompt says what it wants ("wants to run: read the deploy log"), from the last tool call with no result; one waiting with no tool call shows the question it ended on.
- A waiting card stops pulsing after two hours and stays orange; nothing pulses while no client is attached.
- The name is his rename, else Claude Code's own (the job's or registry's, what its footer and agent view say), else the first auto title.
- No folder, no `showing` mark and no context warning (v4, F8): the cursor's highlight already marks what's on the right, and the folder's color is the stripe.
- Bold is only for the cursor card's name and the waiting card; the cursor card (or line) sits on a lighter background (#3a4150) instead of a different color, also while the list is dimmed.
- A session waiting for him has no fill (he asked for "something more minimal" than the solid pink card): its `?`, name and question are orange #ff7b00 in every theme and pulse each spinner frame. Orange appears nowhere else on the list except the `Waiting for you` title, the header's count, and the `?` of a session that asked something.
- Bands are boxes named in the band's color (see Layout); band 4 folds into ` N idle sessions hidden` with `e to show` on the right (`e to hide idle` when shown), under the last box, and a click on that line toggles it.
- A long name is cut with `…` a space before its age; a long question is cut with `…` at the end of its third line.
- Project colors come from the folder, decided once and never the waiting orange: finch orange #ff9e64 (lighter than the waiting #ff7b00), brain and ai-wiki purple #bb9af7, san-jose-foods amber #e0af68, agents-pane teal #94e2d5, home gray, anything else a fixed spare color by name.

## Keys

- `↑↓` or `j k` move, `g G` jump to the ends; the right side shows the cursor's session at once, or 0.12 s after a run of moves settles.
- One click on a card opens it: on the right, with the keys (a chat it can't show gets the note); a click on the idle line toggles it, the find line opens find, and every key in the bar presses that key in the list.
- Enter opens: a background session goes on the right and gets the keys (a stopped one comes back through `claude attach`); a chat in another tmux pane is switched to; an ended session is resumed in the background and shown.
- Tab in the list always moves the keys to the Claude side; Ctrl+] anywhere in the cockpit switches sides once per press, and does nothing while a dialog is open.
- `n` puts the cursor on `+ new chat` and gives the chat box the keys. In the box:
  - Enter starts it; ctrl+j, or a `\` just before the cursor, adds a line (his tmux sends shift+Enter as a plain Enter).
  - `n`, Enter or a click on `+ new chat` always puts a box up, even in the second before the list sees that the last box became a session.
  - Tab and shift+Tab cycle the mode: Yolo (runs everything without asking), Auto (runs everything, with Claude's safety checks), Plan (reads and plans, edits nothing), Accept edits, Manual. A second Tab within 0.4 s of the keys arriving is the double-tap that brought them, and changes nothing.
  - ctrl+l cycles the model (his default, Opus, Sonnet, Haiku, Fable); ctrl+t the effort (his default from settings.json, low, medium, high, xhigh, max).
  - ctrl+f lists the folders it can start in (where `yolo` ran, his sessions' folders that still exist, `~/Projects/*`) where the wordmark was; ↑↓ and Enter pick, Esc or Tab keeps the one it had, and the list keeps the keys if they leave and come back.
  - Esc gives the keys back to the list and keeps the draft.
- `r` reply: shows the question or the last thing it said, then types the answer into the session through a hidden tmux window; a question with choices opens the session instead.
- `R` rename (types `/rename` the same way); `w` a Mac notification when it goes from working to anything else, then the mark clears; `S` twice stops; `X` twice removes; `e` shows or hides idle sessions; `t` opens the theme menu; `u` how often he's used it; `?` all keys, grouped as Moving around, Doing things and Managing, in plain words, with the version at the bottom.
- `q` or Ctrl+C in the list closes the dashboard (Ctrl+C closes an open dialog first); every session keeps running.
- Esc closes a dialog in under 0.1 s: Textual waits `ESCDELAY` ms (20, set by the launcher) to tell Esc from an arrow key, and its input loop wakes every 20 ms instead of 100 ms (`cockpit/quick_esc.py`).

## Search

`/` searches as you type (from two characters, 0.2 s after the last key), on an index the list brings up to date in its own process when it starts and before each search (decision 0008); while the first build runs, results say they may be partial.
↓ moves into the results and Enter opens one.
Results list the date, the name, the folder and the matching line, newest first, up to 30 sessions.
A running session is opened, never resumed a second time; anything else is resumed in the background and shown live.
The same search ships as `bin/find-session` (top 20, with the `claude --resume` line for each).

## Looks (`t` opens the theme menu, the choice is saved)

Every theme shares the frame: the terminal's own background, cards #2c313c, the cursor card #3a4150, text #dcdfe4, #abb2bf and #7f848e, lines #5c6370 (One Dark grays, matching his terminal).
A theme changes its own color (the wordmark), the state colors and the key color; waiting is orange in every theme.
`t` opens a small menu low in the list (no zoom, so the list and Claude stay in view): each theme's name and its own, working, done and key colors as dots.
Moving to a theme shows it live everywhere; Enter keeps it (saved, and the welcome screen redraws in it); Esc puts back the one he had; `?` says which theme is on.
The key color is never the waiting orange, so a key never reads as "waiting for you" (a test checks every theme).

| Theme | Its own color | Working | Done | Failed | Quiet | Keys |
|---|---|---|---|---|---|---|
| Neon (his pick) | #ff4fd8 pink | #5fd7ff cyan | #7cffb2 mint | #ff5f87 rose | #e5c07b khaki | #5fd7ff cyan |
| Mission control | #ffb000 amber | #2dd4bf teal | #a3e635 lime | #ff5555 red | #d19a66 orange | #2dd4bf teal |
| Tokyo night | #ff007c hot pink | #7aa2f7 blue | #9ece6a green | #f7768e rose | #e0af68 amber | #7dcfff sky |

## Outside the cockpit

- `agents: N waiting for you` in bold orange text (no chip) shows in the global tmux status bar, so he sees it in his other tmux sessions; it lives on the cockpit's session (`#{S:#{@ap_alert}}`), so it disappears with it.
- Ctrl+] and clicks on the bar are global tmux bindings that act only in a session marked `@ap_cockpit` and otherwise do what tmux did before; the launcher and the list itself both set the mark, so a cockpit made by an older launcher still works.
- Session options are set with the exact target `=agents:`, because `set-option -t` reads a bare name as a pane and could match a window named `agents…` in another session.
- `AGENTS_PANE_SESSION=agents-preview bin/agents-pane` runs a second cockpit from a branch beside the real one, for previews; it keeps its own state file (`state-agents-preview.json`), so it never counts toward his usage days or changes the real one's theme or watches.

## State file

`~/.claude/agents-pane/state.json`: the look, the watched sessions and the days the cockpit was opened.

## How often he uses it

`u` shows the days in the last two weeks with messages in two or more sessions and how many of them he opened the cockpit on, both as his local dates, counted from the first logged open (2026-10-06).

## Learned by running it (2026-10-06)

- tmux 3.7c: when `respawn-pane` fails ("fork failed: Device not configured") and the same pane is respawned again, the server segfaults in `input_free` and every tmux session dies; this happened once in testing, so nothing re-creates a pane.
- `send-keys -F` expands formats only for copy-mode commands; a click binding has to go through `run-shell`, whose command is expanded with the mouse in context.
- A `]` inside `#[range=user|…]` closes the style early, so range names avoid it.
- `client-resized` doesn't fire when a client attaches at a new size; `window-resized` does.
- With two panes, tmux colors only half the divider for the focused pane unless `pane-border-indicators` is `off`.
- A Textual app gets later resizes on its screens and widgets, not on the app object.
- Theme variables used in Textual CSS need defaults from `get_theme_variable_defaults`, because the CSS is parsed before themes are registered.
- A Textual app killed by a signal leaves the terminal raw, so the launcher's restart loop runs `stty sane` before it waits for Enter.
- `claude --bg` refuses folders that were never trusted ("Workspace not trusted"); the cockpit shows that message instead of trusting the folder for him.
- `claude attach` brings a stopped background session back; Ctrl+C twice inside it opens agent view rather than exiting.
- Typing into a session from a hidden window works while the same session is attached elsewhere; the hidden window waits for an empty `❯` prompt line.
- tmux ends a command at any argument ending in `;`, so every argument is escaped in one place (`tmuxctl.tmux`), and `send-keys -l --` keeps a reply that starts with `-` as text.
- A tmux call costs about 4.5 ms, so writes go out batched (`tmuxctl.batch`) and pane ids are looked up once (tmux never reuses one).
- A job viewer imports nothing from Textual (only the welcome screen does), so it starts fast and can't be broken by a bad Textual install.
- tmux 3.7c swaps panes in about 4 ms (400 swaps in a probe, no crash); a pane's id moves with it, so the right side is whichever viewer sits in the cockpit window, read fresh each time.
- Claude Code stops a finished or waiting session's process after about an hour with nothing attached, and the next attach boots it again; a warm viewer keeps it attached.
- One idle `claude attach` takes about 144 MB and no CPU.
- A tmux client started from inside tmux needs `env -u TMUX`, or it nests in the current session.
- A Textual app gives focus back to the first focusable widget, even a hidden one, so a view without input needs a focusable container of its own.
- His transcripts: 2115 files, 6.4 GB on 2026-10-22, most of it tool output; the last typed prompt sits a median 240 KB from the end, Claude's own `last-prompt` record always in the last 64 KB.
- Textual 8.2.8 notices a lone Esc only when its input loop wakes, every 0.1 s, so `ESCDELAY` alone changed nothing (163 ms either way).
- While a window is zoomed, tmux's `{right}` is the zoomed pane itself.
- `claude attach`: `←`, `/exit` and Ctrl+C twice turn the process into `claude agents` in place; only Ctrl+Z exits.
