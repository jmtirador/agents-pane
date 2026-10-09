# make check      lint + unit + app tests (seconds; the pre-commit hook runs it)
# make check-all  also the tmux tests on a private server (before every release tag)
PY := .venv/bin/python

.PHONY: check check-all fix

check:
	$(PY) -m ruff check cockpit tests bin/find-session
	$(PY) -m pytest -m "not tmux"

check-all: check
	$(PY) -m pytest -m tmux

fix:
	$(PY) -m ruff check --fix cockpit tests bin/find-session
