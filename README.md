# GitHub PR Review Compliance Report

Fetches merged pull requests from a GitHub repository and reports, per PR, whether it was approved by a reviewer and whether its status checks passed before merge.

Built for the Scytale Junior Data Engineer home assignment, against repositories under [home-assistant](https://github.com/home-assistant).

## How it works

1. **Extract** — authenticates with the GitHub REST API using a personal access token, lists closed pull requests for the configured repo, filters them down to merged PRs, then fetches each one's reviews, commit status, and check runs.
2. **Transform** — for each merged PR, decides whether it was approved by at least one reviewer (`CR_Passed`) and whether its reported checks all passed (`CHECKS_PASSED`), then builds the final report rows.
3. **Load** — `main.py` orchestrates both steps and writes the raw extract to `data/extracts/` and the final report to `data/reports/`.

Each merged PR needs three extra API calls (reviews, commit status, check runs) on top of the initial listing - roughly 800 requests for a repo with 270 merged PRs. Those are fetched concurrently across a bounded thread pool (`MAX_WORKERS = 15`), since the work is I/O-bound: almost all the time is spent waiting on GitHub rather than doing computation.

## Project structure

```
.
├── .claude/skills/           # Claude Code skills — see "Claude Code skills" below
│   ├── setup/SKILL.md
│   └── explain-repo/SKILL.md
├── ai_utils/
│   ├── README.md             # notes on how AI tooling was used during development
│   └── CLAUDE.md             # architecture reference (kept here rather than the repo
│                              # root, so it isn't auto-loaded by Claude Code sessions)
├── data/
│   ├── extracts/             # raw JSON pulled from GitHub (git-ignored, regenerated each run)
│   └── reports/              # final CSV report
├── extract.py                # GitHub API access — fetching only, no interpretation
├── transform.py              # CR_Passed / CHECKS_PASSED logic + CSV report writer
├── main.py                   # entry point — wires extract + transform together
├── .env.example               # template for required environment variables
├── requirements.txt
└── README.md
```

There's no separate `utils.py` — the project is small enough that the only thing that would live there (loading `.env` values) is three lines, duplicated in exactly one place (`main.py`), so a shared module wasn't worth the extra indirection.

## Setup

> **Using Claude Code?** Open a session at the repo root and type `/setup` — it creates the venv, installs dependencies, prepares `.env`, and checks you've got a token in place, then hands you the exact command to run. See [Claude Code skills](#claude-code-skills) below for what else is available. Otherwise, follow the manual steps below.

1. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   venv\Scripts\activate         # Windows (cmd.exe / PowerShell)
   source venv/Scripts/activate  # Windows (Git Bash)
   source venv/bin/activate      # macOS/Linux
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a [GitHub personal access token](https://github.com/settings/tokens) — no special scopes are needed to read public repositories, an unscoped classic token is enough to get the higher 5,000 requests/hour rate limit. Then configure it:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set `GITHUB_PAT` (and `GITHUB_OWNER`/`GITHUB_REPO` if you want a different repo than the default).

## Usage

```bash
python main.py
```

Configuration is read entirely from `.env` — there are no CLI flags in this version. To point the script at a different repository, edit `GITHUB_OWNER`/`GITHUB_REPO` in `.env`.

## Claude Code skills

This repo includes two custom [Claude Code skills](https://code.claude.com/docs/en/skills) (`.claude/skills/`) — reusable procedures Claude follows when invoked, rather than instructions repeated by hand each session. Open a Claude Code session at the repo root and try:

| Command | What it does |
|---|---|
| `/setup` | Prepares the environment (venv, dependencies, `.env`) and hands you the run command — it doesn't run the pipeline for you. |
| `/explain-repo` | A fast orientation to the codebase, published as an Artifact page: how the pieces fit together, plus diagrams of the actual extract → transform → report data flow and the CHECKS_PASSED decision logic. |

`ai_utils/README.md` has more on how AI tooling was used throughout this project's development.

## Output

Each run produces four files, named after the configured owner/repo — one for every stage of the pipeline, not just the final result, so a problem in an early stage (e.g. the merge filter) leaves a trail to inspect instead of only the finished output:

- `data/extracts/{owner}_{repo}_closed_prs.json` — every closed PR exactly as `get_closed_pull_requests()` returned it, before any filtering.
- `data/extracts/{owner}_{repo}_merged_prs.json` — the subset with `merged_at is not None`. Diffing this against the file above is the quickest way to check the merge filter is doing what it should.
- `data/extracts/{owner}_{repo}_raw_pr_dataset.json` — each merged PR enriched with its reviews, commit status, and check runs. This is the only one of the three transform.py actually reads; the other two exist purely as a debugging trail. Can run several MB for an active repo.
- `data/reports/{owner}_{repo}_pr_review_report.csv` — the final report, one row per merged PR, sorted by PR number:

| Column | Description |
|---|---|
| `pr_number` | Pull request number |
| `pr_title` | Pull request title |
| `author` | GitHub username of the PR author (`None` if the account was deleted) |
| `merge_date` | Timestamp the PR was merged, UTC (`YYYY-MM-DD HH:MM:SS` — written as a real date, not ISO 8601 text, so it's usable directly in Excel) |
| `CR_Passed` | `True` if approved by at least one reviewer |
| `CHECKS_PASSED` | `True` if every reported check/status passed — see below |

Both output folders are git-ignored (kept via `.gitkeep`) since their contents are regenerated by each run; the raw JSON in particular can run several MB for an active repo.

## Design decisions & known limitations

- **Review approval (`CR_Passed`)**: `True` if *any* review on the PR has state `APPROVED`, matching the assignment's literal wording. Doesn't attempt to resolve a case where a later "changes requested" review might supersede an earlier approval.
- **"Required" status checks (`CHECKS_PASSED`)**: which checks are formally required is defined by a repository's branch protection rules, which need admin access to read — access a read-only personal access token against a third-party org (`home-assistant`) doesn't have. As a substitute, every check/status actually reported against the merge commit (both the legacy Statuses API and the newer Checks API) is treated as if it were required.
- **A PR with *no* checks/statuses reported at all is treated as `CHECKS_PASSED = False`, not `True`.** This was a deliberate choice: for a compliance/audit report, a silent "pass" that actually means "nothing was ever verified" is worse than a "fail" that costs a human a few seconds to look at and dismiss (e.g. "oh, that one's just a docs change"). It means some small, uncontroversial PRs will show up as `False` even though nothing was ever actually wrong — that's intentional, not a bug.
- **PR ordering**: the GitHub API has no "sort by merge date" option, so the initial PR listing is fetched sorted by most-recently-*updated*. This closely tracks merge recency but isn't exact (an old PR can get superseded/closed recently, moving it up the list). The final report is explicitly re-sorted by `pr_number` before writing, so this ordering quirk doesn't leak into the output.
- **Rate limiting**: not handled beyond GitHub's normal per-token quota (5,000 requests/hour). The worker cap (`MAX_WORKERS = 15`) is deliberately conservative to stay clear of GitHub's separate secondary/abuse rate limit, but there's no retry-on-429 logic.
- **Failed requests**: if a PR's requests fail (network error, rate limit), that PR is logged, skipped, and reported in a warning at the end rather than aborting the whole run — a single failure shouldn't discard several minutes of already-fetched work. The affected PRs are simply absent from that run's report.


## A note from me

Beyond what the assignment asked for, I added two custom Claude Code skills to this repo: `/setup` and `/explain-repo`. If you're reviewing this in Claude Code, open a new terminal at the repo root and just type one of those straight into the chat to try it out.

Enjoy!
