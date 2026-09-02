# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A script that fetches merged pull requests from a GitHub repository and reports, per PR, whether it was approved by a reviewer (`CR_Passed`) and whether its status checks passed before merge (`CHECKS_PASSED`). Built for the Scytale Junior Data Engineer home assignment. Full context, output schema, and design rationale are in `README.md` — read it before making non-trivial changes, especially the "Design decisions & known limitations" section.

## Commands

```bash
# Setup
python -m venv venv
source venv/Scripts/activate   # Git Bash on Windows; see README.md for other shells
pip install -r requirements.txt
cp .env.example .env           # then set GITHUB_PAT

# Run the full pipeline
python main.py
```

There is no test suite, linter, or build step configured in this repo — don't assume `pytest`/`flake8`/etc. are set up; check `requirements.txt` before assuming a dependency is available. Config is read entirely from `.env` (`GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_PAT`) via `python-dotenv`; there are no CLI flags.

## Architecture

Three-stage pipeline, wired together by `main.py`:

```
extract.py (GitHub API) -> transform.py (CR_Passed/CHECKS_PASSED logic) -> CSV report
```

- **`extract.py`** only fetches data — it never interprets pass/fail. `get_closed_pull_requests()` returns *all* closed PRs (merged and unmerged); `main.py` filters to merged ones before passing them on. `build_raw_pr_dataset()` then fetches each merged PR's reviews, commit status, and check runs **concurrently** via a `ThreadPoolExecutor` (`MAX_WORKERS = 15`, capped to avoid GitHub's secondary rate limit) — this is I/O-bound work, so threads help despite the GIL. Results come back in completion order, not PR order.
- **`transform.py`** is pure logic, no network calls — this is intentional, so it can be tested/reasoned about independently of the API. `transform_dataset()` re-sorts by `pr_number` before writing, which is what erases the completion-order shuffling from the extract step.
- **`main.py`** passes the raw dataset from extract straight into transform in memory; it does *not* round-trip through the saved JSON in the same run. `load_raw_dataset()` in `transform.py` exists for re-running the transform step later against an already-saved extract, without hitting the API again.

**The raw record contract** between the two stages (produced by `extract.py`, consumed by `transform.py`) is a dict per PR with keys: `pr_number`, `title`, `author`, `merged_at`, `reviews`, `commit_status`, `check_runs`. The last three are kept as full, untrimmed GitHub API response objects — deciding what fields within them matter is `transform.py`'s job, not `extract.py`'s. If you need a new field in the final report, check whether it's already present in one of these raw objects before adding a new API call.

**Two judgment calls baked into `compute_checks_passed()`** (the trickiest logic in the codebase — read its docstring before touching it):
1. Branch-protection rules (which checks are formally "required") aren't readable without admin access, which the PAT doesn't have — so every check/status reported on the commit is treated as required.
2. A PR with *no* checks/statuses reported at all returns `False`, not `True` — a deliberate choice for a compliance-report context (surfacing "nothing was verified" beats silently passing it).

**Output file naming**: both the raw extract and the CSV report are named `{owner}_{repo}_...` and written under `data/extracts/`/`data/reports/` (git-ignored except a committed sample CSV) — see `main.py` for the exact paths.
