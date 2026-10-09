# agents-pane spec (the cockpit; v2 2026-10-06, v3 2026-10-08)

The single source of truth for the build.
Every review and the drift audit check against this file.
v1 was a docked side pane inside one chat; Pepe rejected it on 2026-10-06 ("no color", "not bold", "just a side pane", "wrap Claude Code").
On the plan page he picked: shape A (full-screen cockpit), the Neon look, and all twelve features.

## v3 (in progress, started 2026-10-08)

On 2026-10-08 Pepe said v2 felt unintuitive, a bit too technical and a bit too loud, that the bold key chips and borders sat wrong around the Claude Code window, and that he wanted a darker gray instead of black.
He picked direction A on the plan page: match his terminal, a quiet frame, color only for state.
`docs/problems.md` holds each complaint and bug as a problem with the check that closes it; v3 is done when every check passes.
The sections below describe the v3 branch; each milestone rewrites the ones it changes in the same commit range.

**Appetite.** Same features, made calmer and clearer; no new features.
Milestones, revised after the devil's advocate on 2026-10-08 (the look comes sooner, a code-only milestone is gone):
- M0 safety net, tagged v2.0.0: the tmux test rig, unit and Pilot tests, `make check`, git hooks, the changelog, a version number. Nothing on screen changes.
- M1 bug fixes, tagged v2.0.1: B1-B4, each with a test that failed first.
- M2 look and words: direction A plus the plain-word labels in one pass, with code reorganized only where this work touches it. Real-window screenshots go to Pepe with one question: too quiet, right, or still loud?
- M3 his test and release, tagged v3.0.0: picture tests lock in the look he approved, his 10-minute test, the fixes it turns up, the release and the vault log.

**Kill rule.** v3 polishes a tool he is using; the two-week count that ends 2026-10-20 still decides, and if it fails the tool is deleted, with no v4.

**Breadboard (in words).**
- The window is one surface: the terminal's own background everywhere, the list's cards one step lighter.
- The list's first row is its own header: `agents` plus the counts, so there are no tmux title lines.
- One single-line divider in a quiet gray between the list and Claude Code, and one plain line across both over the key bar; nothing else frames Claude.
- The bottom bar shows the keys for the focused side as quiet text: list keys while in the list, only the way back while typing to Claude (plus "N waiting for you" when anything waits).
- While Claude has focus the list dims; the card shown on the right says "showing".
- `?` lists every key, grouped, and fits a zoomed pane; the bar's last item says so.

**Rabbit holes.**
- Textual can't blend colors with the terminal's default background: paint "default" but keep a hex copy of #282c34 for blending.
- Two panes always share one divider color in tmux, so focus is shown by the bar and the dimming, not by border color.
- Ghostty stops redrawing a covered window: real-window screenshots are taken with the cockpit in front; the picture tests don't use Ghostty.

**Not doing.**
- No new features.
- No rewrite and no code-only milestone: code moves only where the look and word changes need it.
- Card content stays: the second line of each card (what the session is doing or said) is the detail he likes; only labels, the key bar and dialogs lose jargon.
- Nothing inside Claude Code's own screen changes.
- The three themes stay; in v3 they change accent colors only, and the background always follows the terminal.

## Theme and contract

The cockpit holds Pepe's open loops so he can leave them open, and it wraps Claude Code instead of sitting beside it.
He runs 2-6 sessions at once, checks on them from other chats, and searches old ones by what they were about.
He leaves loops open on purpose, so it never asks him to close, clear or confirm anything.

Contract: the glyph is what a file proves, the order is who needs you first, the right side is the real session.

## Rules

1. True with zero upkeep: every card comes from files Claude Code already writes.
2. Never claim a state the data can't back; show the real last line and its age.
3. Color for meaning (rewritten for v3, 2026-10-08): the frame is quiet and matches his terminal, color stays on every state and project, and the one loud thing is a session waiting for him, whose text pulses orange (2026-10-09: no more solid card). Never gray it out: v1 was rejected for "no color", v2 for being "the tiniest bit too loud".
4. Nothing destructive on one key: stopping takes `s` twice, removing takes `x` twice, both within 2 s.
5. Nothing to clear: finished cards fade by age, with no seen/unseen ritual.
6. Built to delete: a thin layer over files, tmux and the `claude` CLI, with one small state file.
7. Never re-create a tmux pane while it runs (see "Learned by running it").
8. His kill rule: if it isn't opened on at least half his busy days for two weeks, delete it, don't redesign it.

## Where it lives

- `~/Projects/agents-pane`, a Python package `cockpit` run from the project's own `.venv` (Textual is the one dependency).
- `yolo` runs `bin/agents-pane`, which opens (or reattaches) the tmux session `agents`, window `cockpit`.
- `yolo "prompt"` also starts a background session in the current folder with that prompt and shows it live.
- `yolo --flag …` still runs a plain `claude --dangerously-skip-permissions` chat, the old way.
- Leaving the cockpit (`q`, or detaching tmux) keeps everything running, so the next `yolo` is instant.

## Layout

- Two panes tagged by the pane option `@ap_role`: `list` (42 columns, kept by a `window-resized` hook) and `live` (the rest).
- The terminal paints the background everywhere (decision 0002); the window and the bar ask for `bg=default`, and the list's empty space is Textual's `ansi_default`.
- tmux draws one single-line divider in the frame gray (`line`), the same color whichever side has focus, plus one plain line across both sides over the key bar (`pane-border-status bottom` with an empty format), and nothing else: no pane titles, no indicators (decision 0003 and its amendment).
- The list's first box is its own header: a thin rounded box named `agents` (bold while the list has focus) saying `N waiting` in bold orange, `N working` in the work color and `N done` in the done color, in words, or `nothing running`.
- Each band is a thin rounded box in the frame gray with its name in the top line in the band's color (`╭─ Working ───╮`), like the welcome screen's box; its cards sit inside.
- Boxes mean "a group": single cards, the idle line, the find line and the Claude side are never boxed.
- The bottom bar is quiet text, never chips: each key in the theme's key color and what it does in gray, three spaces apart, and the clock on the right; the only bold is `N waiting for you` on the Claude side.
- In the list the bar says `↑↓ pick   enter open   tab go to Claude   n new   / find   t theme   ? all keys`; on the Claude side it says only `ctrl+] back to your sessions`, plus `N waiting for you` on the right when anything waits.
- Every key in the bar is clickable; a click presses that key in the list (`ctrl+]` sends F12, because a `]` can't be in a click range name).
- The list's last row is ` / find an old session`, which opens find when clicked.
- While Claude has the keys the list dims: the header and band titles go gray, nothing is bold except the waiting card and the header's waiting count, project colors fade halfway to the background; a waiting card keeps pulsing.
- While a dialog is open the list pane zooms to the whole window, the bar shows that dialog's own keys (`enter start it`, `esc cancel` and so on), and the space goes back after.
- Dialogs, their inputs and the welcome box are rounded lines in the frame gray with no fill, like Claude Code's prompt box, on the terminal's own background; the focused input's line is in the key color, and the welcome box's one input is a filled bar with no line of its own.
- While any dialog is open the list sets `@ap_dialog` on its session (with the dialog's keys in the bar), and Ctrl+] waits for it to close, zoomed or not.
- Toasts span the list's width so they don't wrap (a title line, then the message), in the same thin rounded line (the warning and error ones in their state color).

## The live pane

- One long-running process, `cockpit/live.py`, owns the pane for its whole life.
- It runs a child: `claude attach <job>` when the pane option `@ap_want` names a job, else the welcome screen.
- To switch, the list sets `@ap_want` and sends it SIGUSR1; it sends the child SIGHUP, resets the terminal (`ESC c`) and starts the next one.
- `@ap_want` is the one record of what the live pane shows: the list, the welcome box, `yolo "prompt"` and live.py itself (when he leaves a session) all write it.
- The list reads it every second on the same thread that sends its own switches, so it never reads an answer older than its last switch; a change it didn't ask for makes the list follow.
- Ctrl+Z in Claude Code leaves the session (it keeps running) and brings the welcome screen back.
- Ctrl+C twice opens Claude Code's own agent list inside the pane; Esc leaves it.
- The welcome screen: the AGENTS wordmark fading from the theme's own color to the key color (kept on purpose: he called it "awesome"), a line saying "Pick a session on the left, or start a new one here.", a box titled `new session` that starts one in the folder `yolo` was run from, the two keys that matter in words, and one tip a day.

## Data (measured 2026-10-06)

| Source | What | Cost |
|---|---|---|
| `~/.claude/sessions/<pid>.json` | registry: sessionId, cwd, startedAt, kind, status (idle, busy, waiting, shell), statusUpdatedAt, tmux pane, spare | cached by mtime |
| `~/.claude/jobs/<id>/state.json` | background jobs: state, tempo, the live `detail` line, intent, updatedAt | cached by mtime |
| the last 64 KB of each transcript (256 KB when no usage record) | permission mode, last prompt, its own title, recap, last reply, usage, steps, pending AskUserQuestion, API errors | read only when the file changed |
| `rg -i -F` over `~/.claude/projects` | search, kept to typed prompts, titles (his own too), recaps and replies | 0.2-0.4 s |
| `claude agents --json` | a guard against Claude Code changing its files, run every 30 s only while no live session is visible | 0.1 s |

Context size = the last assistant `usage.input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.
The limit is 970K "until auto-compact"; a card says `context N% full` at 80% or more.
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

- Waiting, failed and working sessions get two lines on a card background one step lighter than the terminal (#2c313c on #282c34), with a blank row between cards where the terminal shows through.
- Done and idle sessions get one line each with no fill and no gaps (design B, his pick on 2026-10-09): stripe, mark, name, a few words of the recap if they fit (never a lone `…`), the watch mark `◉` and `↗` like a card, `showing ▸` if it's on the right, and the age.
- The first line: a stripe in the project's color, the glyph, the name, the folder in the project's color (whole or left out, never cut), the watch mark `◉`, `↗` for a chat in some other window, and the age on the right.
- The second line: the question (needs you, asks), the error (failed), the live detail or last step (working; a bare file path shows its file name), else the recap, the reply's first sentence or the last prompt.
- On the right of the second line, after a two-space gap: `showing ▸` in the key color on the card shown on the right, else `context N% full` in the quiet color at 80% or more.
- Bold is only for the cursor card's name and the waiting card; the cursor card (or line) sits on a lighter background (#3a4150) instead of a different color.
- A session waiting for him has no fill (he asked for "something more minimal" than the solid pink card): its `?`, name and question are orange #ff7b00 in every theme and pulse each spinner frame. Orange appears nowhere else on the list except the `Waiting for you` title, the header's count, and the `?` of a session that asked something.
- Bands are boxes named in the band's color (see Layout); band 4 folds into ` N idle sessions hidden` with `e to show` on the right (`e to hide idle` when shown), under the last box, and a click on that line toggles it.
- A long name is cut with `…` a space before its age, and the folder is left out first.
- Project colors come from the folder, decided once and never the waiting orange: finch orange #ff9e64 (lighter than the waiting #ff7b00), brain and ai-wiki purple #bb9af7, san-jose-foods amber #e0af68, agents-pane teal #94e2d5, home gray, anything else a fixed spare color by name.

## Keys

- `↑↓` or `j k` move, `g G` jump to the ends; the live side follows to any running background session 0.3 s after the selection settles.
- Enter opens: a background session goes live and gets the focus (a stopped one comes back through `claude attach`); a chat in another tmux pane is switched to; an ended session is resumed in the background and shown live.
- Tab in the list always moves the keys to the live session; Ctrl+] anywhere in the cockpit switches sides once per press, and does nothing while a dialog is open.
- `n` new session: what it should do, the folder (defaults to where `yolo` ran, with suggestions), an optional name.
- `r` reply: shows the question or the last thing it said, then types the answer into the session through a hidden tmux window; a question with choices opens the session live instead.
- `R` rename (types `/rename` the same way); `w` a Mac notification when it goes from working to anything else, then the mark clears; `s` twice stops; `x` twice removes; `e` shows or hides idle sessions; `t` opens the theme menu; `u` how often he's used it; `?` all keys, grouped as Moving around, Doing things and Managing, in plain words, with the version at the bottom; `q` leave.
- Clicks: a card selects it, a double click opens it, the idle line toggles, the find line opens find, and every key in the bar presses that key in the list.

## Search

`/` searches as you type (from two characters, 0.35 s after the last key); ↓ moves into the results and Enter opens one.
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
- `AGENTS_PANE_SESSION=agents-preview bin/agents-pane` runs a second cockpit from a branch beside the real one, for previews; it keeps its own state file (`state-agents-preview.json`), so it never counts toward the kill rule or changes the real one's theme or watches.

## State file

`~/.claude/agents-pane/state.json`: the look, the watched sessions and the days the cockpit was opened.

## Measuring it (for the kill rule)

`u` compares the days the cockpit was opened with the days that had messages in two or more sessions, both as his local dates, counted from the first logged open (2026-10-06).
Before two weeks have passed it says so instead of judging; the two weeks end Tue 10/20.

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
- The live pane's process imports nothing from Textual, so it starts fast and can't be broken by a bad Textual install.
