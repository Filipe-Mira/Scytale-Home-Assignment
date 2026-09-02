"""
transform.py — turns the raw PR dataset from extract.py into the final report.

No network calls happen here: everything operates on data already fetched,
which keeps this logic easy to test independently of the GitHub API.
"""

import json
import os

import pandas as pd

# Check-run conclusions that don't count as failures. "skipped" (a job that
# only runs on certain branches) and "neutral" shouldn't sink a PR the way
# "failure" or "cancelled" should.
NON_BLOCKING_CONCLUSIONS = {"success", "neutral", "skipped"}

# Report columns, in the order the assignment specifies. Passed to pandas
# explicitly so the CSV header order never depends on dict key order.
REPORT_COLUMNS = ["pr_number", "pr_title", "author", "merge_date", "CR_Passed", "CHECKS_PASSED"]


def load_raw_dataset(filename: str) -> list[dict]:
    """Load a raw dataset previously written by extract.py."""
    with open(filename, encoding="utf-8") as f:
        return json.load(f)


def compute_cr_passed(reviews: list[dict]) -> bool:
    """
    True if at least one reviewer approved the PR.

    A dismissed approval has state "DISMISSED" rather than "APPROVED", so
    it correctly doesn't count here.
    """
    return any(review["state"] == "APPROVED" for review in reviews)


def compute_checks_passed(commit_status: dict, check_runs: list[dict]) -> bool:
    """
    True if every check reported against the PR's head commit passed.

    Two caveats worth knowing:

    1. Which checks are formally "required" is set by branch protection
       rules, which need admin access to read — a read-only PAT against
       someone else's org can't. So every reported check is treated as
       required.
    2. A PR with no checks at all reports False, not True. For a compliance
       report, "nothing was ever verified" is worth surfacing rather than
       silently passing.

    GitHub has two check systems (the legacy Statuses API and the newer
    Checks API), so both are consulted and either one failing fails the PR.
    """
    has_legacy_statuses = commit_status.get("total_count", 0) > 0
    has_check_runs = len(check_runs) > 0

    if not has_legacy_statuses and not has_check_runs:
        return False

    status_ok = commit_status["state"] == "success" if has_legacy_statuses else True
    check_runs_ok = all(
        run["status"] == "completed" and run["conclusion"] in NON_BLOCKING_CONCLUSIONS
        for run in check_runs
    )

    return status_ok and check_runs_ok


def build_report_row(raw_record: dict) -> dict:
    """Flatten one raw PR record into a single report row."""
    return {
        "pr_number": raw_record["pr_number"],
        "pr_title": raw_record["title"],
        "author": raw_record["author"],
        "merge_date": raw_record["merged_at"],
        "CR_Passed": compute_cr_passed(raw_record["reviews"]),
        "CHECKS_PASSED": compute_checks_passed(
            raw_record["commit_status"], raw_record["check_runs"]
        ),
    }


def transform_dataset(raw_dataset: list[dict]) -> list[dict]:
    """
    Build a report row for every PR, sorted by PR number.

    Sorting here rather than in save_report() means every caller gets a
    deterministic order — extract.py returns PRs in completion order.
    """
    rows = [build_report_row(record) for record in raw_dataset]
    return sorted(rows, key=lambda row: row["pr_number"])


def save_report(rows: list[dict], filename: str) -> None:
    """
    Write the report rows to CSV, creating the folder if needed.

    utf-8-sig (UTF-8 with a BOM) is used so Excel on Windows renders
    non-ASCII PR titles correctly instead of mangling them.
    """
    directory = os.path.dirname(filename)
    if directory:
        os.makedirs(directory, exist_ok=True)

    df = pd.DataFrame(rows, columns=REPORT_COLUMNS)

    # GitHub's timestamps ("2026-08-30T06:40:21Z") aren't a format Excel
    # auto-detects as a date — it just treats them as text. Converting to
    # a real datetime column makes pandas write "2026-08-30 06:40:21"
    # instead, which Excel does recognize. Still UTC, just without the "Z".
    df["merge_date"] = pd.to_datetime(df["merge_date"]).dt.tz_localize(None)

    df.to_csv(filename, index=False, encoding="utf-8-sig")
