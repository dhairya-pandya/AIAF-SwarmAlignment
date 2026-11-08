# HiveGuard

**Which swarm algorithm makes LLM swarms safest?** A safety benchmark of bio-inspired coordination
strategies for LLM agent swarms with compromised agents. Built for the Apart × AIAF Swarm Alignment
Hackathon (Nov 6–8, 2026).

- [DESIGN.md](DESIGN.md): pre-registration (hypotheses, metrics, analysis plan). Committed alone in the first commit, before any code.
- [RESEARCH.md](RESEARCH.md): literature notes.
- [DEVIATIONS.md](DEVIATIONS.md): every change made to the pre-registered plan during the sprint.
- [paper/paper.md](paper/paper.md): the report draft.

**Status: work in progress.** No results have been produced yet.

## Setup

```bash
uv venv -p 3.12 && uv pip install -e '.[dev]'
pytest
```

## Pre-existing work declaration

Pre-sprint materials (written 2026-11-01 to 2026-11-05): `RESEARCH.md` (literature notes) and
`DESIGN.md` (the pre-registration). No experiment code, data or results existed before the sprint
began on 2026-11-06. All code under `hiveguard/`, `analysis/` and `tests/` was written during the sprint.

SHA-256 of the pre-registration files at the first commit:

```
0d8805c20d4e3973e1b076ce944b5de9abf806bda7b4d0714c26bd83b08cd5c8  DESIGN.md
af96a648ac2a2bbecfa39a43cf36deb54f8f91747a50bf88d34c39644b4e8b60  RESEARCH.md
```
