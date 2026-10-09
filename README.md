# agents-pane

**An andon board for AI coding agents: one screen where the only loud thing is the agent waiting on you.**
agents-pane is a terminal cockpit for running several Claude Code agents at once (Claude Code is Anthropic's AI coding agent that works in your terminal).
Every session, meaning one agent on one task, sits in a list on the left, and the one you pick runs live on the right as the real Claude Code.
It runs on macOS inside tmux and needs Python 3 and Claude Code ([Install](#install)).

![agents-pane: the session list on the left, a live Claude Code session on the right](docs/images/hero.png)

## The idea

With one AI agent, you wait for the AI.
With five, the AI waits for you.

That's the Theory of Constraints from industrial engineering: a system can't produce more than its bottleneck, and with several agents running, the bottleneck is you noticing that one of them stopped to ask a question.
An agent stuck on a question in a back tab does nothing until you find it.

Lean factories solve the same problem with an andon, a signal light over the line that turns amber when a station needs help, so nobody has to walk the floor checking.
agents-pane is that light for agents.
The frame stays quiet and every state keeps its own color, but only an agent waiting on you pulses orange, and it keeps pulsing until you answer it.

## What it does

- Each session gets a card in the list, sorted by who needs you first: Waiting for you, Working, Done, and Idle (folded away).
- The right side is the real Claude Code, not a copy: your agents run as background sessions that keep going with no window open, and picking a card plugs the right side into one (`claude attach`) so you type straight into it.
- Each card shows what the agent is doing right now, how long it has been at it, and a warning when its context (how much of the conversation it can hold at once) is nearly full.
- From the list you can start a new agent in any folder, reply without opening a session, search old sessions by what they were about, and get a Mac notification when one finishes.
- A theme menu recolors everything live as you move through it.
- It works out each session's state from the files Claude Code already writes, so there's nothing to set up or update by hand.

![The same list in the Neon, Mission control and Tokyo night themes](docs/images/themes.png)

## How it was built

I'm an industrial engineering student, not a software engineer.
I designed agents-pane and directed the work, Claude Code wrote the code, and I ran it the way a small senior team works:

- I kept a spec and a paper trail: [`SPEC.md`](SPEC.md) is the source of truth, [`docs/problems.md`](docs/problems.md) lists the real problems each version had to fix, and [`docs/decisions/`](docs/decisions/) records why the big choices were made.
- There are 107 tests at three levels: unit tests check the logic, app tests run the list with tmux faked (including picture tests that lock in the look I approved), and tmux tests drive the real `bin/agents-pane` on a private tmux server, so none of them touch your own sessions.
- Before every release, separate agents that hadn't written the code reviewed it, the screenshots, and the places where the spec, docs and code had drifted apart.
- Those reviewers caught real problems: a keyboard shortcut the preview build had quietly broken in my real cockpit, a test that could no longer fail and so proved nothing, and a README that still showed the old version.
- From v3 on, every version ran in a preview cockpit beside my real one, and nothing shipped until I had looked at it.

It went from v1 to v3.1 in four days ([`CHANGELOG.md`](CHANGELOG.md)): a side pane I rejected for having no color, a full-screen cockpit that turned out a bit too loud, and the version above, which keeps color everywhere but saves the pulsing orange for the agent waiting on you.

## Install

It needs macOS (the only place I've run it), Python 3, tmux (a tool that splits one terminal window into panes), `rg` (ripgrep) and the `claude` CLI with background sessions (`claude --bg` and `claude attach`).
On a Mac, `brew install tmux ripgrep` covers the middle two.
I build and use it with tmux 3.7c, Python 3.14 and Claude Code 2.1.

**Sessions agents-pane starts or resumes skip Claude Code's permission prompts** (`--dangerously-skip-permissions`), so those agents edit files and run commands without asking first.
That's how I work; it's one line in `cockpit/tmuxctl.py` (`start`) if you'd rather they ask.

```sh
git clone https://github.com/jmtirador/agents-pane
cd agents-pane
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
bin/agents-pane
```

## Use

- `bin/agents-pane` opens the cockpit or comes back to it; `bin/agents-pane "prompt"` also starts a session in the current folder and shows it live.
- `↑↓` or `j k` pick a session, and the right side follows if it's running in the background; Enter opens any other one (an ended session restarts in the background), and the one you leave keeps running.
- Enter, Tab or Ctrl+] puts you in the live session; Ctrl+] again (or a click) brings you back to your sessions.
- `n` starts a session in any folder, `r` replies without opening it, and `/` finds old sessions by what they were about.
- `w` sends a Mac notification when a session finishes, `s` twice stops one (Enter brings it back), `x` twice deletes it for good, `e` shows the idle ones, `t` opens the theme menu, and `?` lists every key.
- In the live session, Ctrl+Z leaves it (it keeps running) and brings back the welcome screen, where you can start a new one.
- `q` leaves the cockpit; everything keeps running.
- `bin/find-session invoice export` searches old sessions for "invoice export" from any terminal.

![The theme menu, trying Mission control](docs/images/menu.png)

## How it works

- `bin/agents-pane` builds a tmux session named `agents` (a tmux session, not a Claude one): the list on the left, the live pane on the right.
- `cockpit/sessions.py` (standard library only) reads the session registry, the background job files and the end of each transcript, and works out each session's state.
- `cockpit/app.py` is the list, built with Textual (a Python library for terminal apps): cards, dialogs, keys and clicks; `cockpit/view.py` draws the cards and `cockpit/model.py` holds the ordering rules, both pure and tested.
- `cockpit/live.py` owns the right pane and swaps `claude attach` and the welcome screen inside it, so tmux never re-creates a pane (tmux 3.7c can crash when it does).
- `cockpit/tmuxctl.py` holds the cockpit's tmux and `claude` commands: the frame, the key bar, typing a reply, starting and stopping sessions.
- `docs/progress.md` is the build log, and `CHANGELOG.md` says what each version changed.

## Develop

```sh
.venv/bin/pip install -r requirements-dev.txt
git config core.hooksPath .githooks   # every commit runs make check and checks the message format
make check       # lint, unit tests, app tests and picture tests (seconds)
make check-all   # also the tmux tests, on a private tmux server with a fake claude (before every release)
```

- `tests/unit` covers the pure parts, `tests/app` runs the list app with tmux faked, and `tests/tmux` runs the real launcher on a private server; none of them touch your own tmux or sessions.
- `tests/app/test_pictures.py` compares each screen with the approved picture in `tests/app/__snapshots__/`; after a wanted look change, look at the failure report, then run `.venv/bin/python -m pytest tests/app/test_pictures.py --snapshot-update` and commit the new pictures.
- Commits follow Conventional Commits (`fix: …`, `feat: …`), and releases get a git tag and a `CHANGELOG.md` entry.

## License

MIT, see [`LICENSE`](LICENSE).
