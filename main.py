"""
main.py — entry point. Runs the full pipeline end to end:

    GitHub API -> raw JSON extract -> CR/checks analysis -> CSV report

Configuration comes from .env (see .env.example). Run with: python main.py
"""

import os

from dotenv import load_dotenv

from extract import build_raw_pr_dataset, get_closed_pull_requests, save_json
from transform import save_report, transform_dataset

# Output paths are anchored to this file's location, so the script writes to
# the same place regardless of which directory it's run from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config() -> tuple[str, str, str]:
    """
    Read GitHub config from .env, exiting with a clear message if any is missing.

    Without this check, unset values would surface much later as a
    confusing 404 from api.github.com/repos/None/None.
    """
    load_dotenv()
    config = {name: os.getenv(name) for name in ("GITHUB_OWNER", "GITHUB_REPO", "GITHUB_PAT")}

    missing = [name for name, value in config.items() if not value]
    if missing:
        raise SystemExit(
            f"Missing required value(s) in .env: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill them in."
        )

    return config["GITHUB_OWNER"], config["GITHUB_REPO"], config["GITHUB_PAT"]


def main() -> None:
    """Fetch merged PRs, analyse them, and write the raw extract and report."""
    owner, repo, token = load_config()

    # --- Extract ---
    # Each stage's output is saved as it's produced, not just the final
    # result — so a problem in filtering or enrichment leaves a trail to
    # inspect instead of only ever existing in memory.
    extracts_dir = os.path.join(BASE_DIR, "data", "extracts")

    print(f"Fetching closed PRs for {owner}/{repo}...")
    closed_prs = get_closed_pull_requests(owner, repo, token)
    closed_path = os.path.join(extracts_dir, f"{owner}_{repo}_closed_prs.json")
    save_json(closed_prs, closed_path)
    print(f"{len(closed_prs)} closed PRs saved to {closed_path}")

    merged_prs = [pr for pr in closed_prs if pr["merged_at"] is not None]
    merged_path = os.path.join(extracts_dir, f"{owner}_{repo}_merged_prs.json")
    save_json(merged_prs, merged_path)
    print(f"{len(merged_prs)} merged PRs saved to {merged_path}\n")

    raw_dataset = build_raw_pr_dataset(owner, repo, token, merged_prs)

    raw_path = os.path.join(extracts_dir, f"{owner}_{repo}_raw_pr_dataset.json")
    save_json(raw_dataset, raw_path)
    print(f"\nRaw dataset saved to {raw_path}")

    # --- Transform ---
    report_rows = transform_dataset(raw_dataset)

    report_path = os.path.join(BASE_DIR, "data", "reports", f"{owner}_{repo}_pr_review_report.csv")
    save_report(report_rows, report_path)
    print(f"Report saved to {report_path}")

    # --- Summary ---
    passed_cr = sum(row["CR_Passed"] for row in report_rows)
    passed_checks = sum(row["CHECKS_PASSED"] for row in report_rows)
    print(f"\n{len(report_rows)} merged PRs analysed")
    print(f"CR_Passed=True: {passed_cr}/{len(report_rows)}")
    print(f"CHECKS_PASSED=True: {passed_checks}/{len(report_rows)}")


if __name__ == "__main__":
    main()
