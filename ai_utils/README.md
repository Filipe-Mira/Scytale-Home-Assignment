# AI Tooling Notes

How AI assistance was used while building this project, per the assignment's request to surface AI tooling resources.

## Tool used

Claude Code (Anthropic), used interactively throughout development.

## How it was used

This was built as a guided, phase-by-phase collaboration rather than AI-generated code reviewed after the fact:

1. **Planning**: Claude parsed the assignment PDF and proposed a build order — scaffolding, an auth smoke test, listing PRs, enriching each PR with reviews/checks, the transform logic, the CSV report, and finally wiring it together in `main.py` — before any code was written.
2. **Implementation**: for most functions, Claude scaffolded the file with docstrings and step-by-step comments describing what each piece needed to do (endpoints to call, pagination handling, etc.), and the actual code was written by hand against that scaffold.
3. **Review**: after each phase, Claude reviewed the code that had been written and caught several real bugs before they shipped — e.g. a function reading a variable off the caller's global scope instead of taking it as a parameter, and a function silently ignoring a `filename` argument it was passed. Both only "worked" by accident (Python's scoping rules, and matching string construction at the one call site that existed at the time) and would have broken the moment the code was reused elsewhere.
4. **Design decisions**: a few judgment calls were made explicitly, not defaulted to whatever Claude suggested first — most notably how `CHECKS_PASSED` should behave for a merged PR with no reported checks at all. Claude's first suggestion was to treat that as a pass ("nothing was configured, so nothing failed"); the decision made instead was to treat it as a fail, on the reasoning that for a compliance/audit report, a silent pass that hides "nothing was ever verified" is worse than a fail that costs a reviewer a few seconds to dismiss.

## What was verified against reality, not just trusted

- Every new GitHub endpoint was smoke-tested with real `curl`/Python calls against the actual repo before being wired into the pipeline, rather than assuming the documented response shape was exactly right.
- The pagination loop, the DRY refactor of shared HTTP-request logic, and the concurrency rewrite were each re-run against the live API afterward to confirm they still returned identical results to the version before the change.
- The final report's numbers (e.g. how many merged PRs had `CR_Passed`/`CHECKS_PASSED` true) were sanity-checked by hand against a sample of the raw JSON, not just assumed correct because the code ran without errors.

See the top-level `README.md`'s "Design decisions & known limitations" section for the specific reasoning behind the CR_Passed/CHECKS_PASSED logic.

## Claude Code skills

This repo also ships two custom Claude Code skills — reusable, repo-specific procedures Claude follows when invoked, rather than one-off chat instructions. `CLAUDE.md` stays here in `ai_utils/` as reference documentation, but a skill only becomes an actual invokable `/command` when its `SKILL.md` lives at `.claude/skills/<name>/`, so that's where the functional files are (`.claude/` isn't shown by default in most file browsers, but it's there).

| Skill | Invoke with | What it does |
|---|---|---|
| **Setup** | `/setup` | Creates the venv, installs dependencies, prepares `.env`, and checks for a token — then hands back the exact run command instead of running the pipeline itself. |
| **Explain repo** | `/explain-repo` | Reads `README.md`/`CLAUDE.md`, then publishes an Artifact page with a fast walkthrough of the architecture and hand-drawn diagrams of the actual extract → transform → report data flow and the CHECKS_PASSED decision logic. |

Try any of them in a Claude Code session opened at the repo root.
