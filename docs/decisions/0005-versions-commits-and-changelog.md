# 5. Versions, commits and the changelog

Status: accepted, 2026-10-08

## Decision

- Semantic versions, shown under `?` and by `python -m cockpit --version`; the version lives in `cockpit/__init__.py`.
- Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`), checked by `.githooks/commit-msg`; the body says why.
- `CHANGELOG.md` in the Keep a Changelog shape, plain words, an Unreleased section; a test checks its top version matches the code.
- A git tag per release (v2.0.0, v2.0.1, v3.0.0; no beta or rc tags at this scale); `.githooks/pre-commit` runs `make check`.
- No remote and no CI: the hooks are the gate.
