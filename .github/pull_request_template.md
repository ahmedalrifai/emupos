<!--
The pull request title becomes the commit message on main and decides the next version.
Use Conventional Commits, e.g. `feat(scale): add NCI protocol` or `fix(printer): wrap Font B at 64 columns`.
-->

## What and why

<!-- One or two sentences. Link the issue: Closes #123 -->

## Checklist

- [ ] Tests added or updated next to the code (`uv run pytest` passes)
- [ ] `uv run ruff format`, `uv run ruff check` and `uv run pyright` pass
- [ ] New protocol commands cite their manual and section, and have a fixture
- [ ] Documentation updated (`README.md`, `docs/`) if behaviour changed
- [ ] No new runtime dependency, or it is justified in `CONTRIBUTING.md`
