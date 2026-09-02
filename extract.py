"""
extract.py — fetches raw pull request data from the GitHub REST API.

Each merged PR needs 3 extra requests (reviews, commit status, check runs)
on top of the initial PR listing, so those are fetched concurrently across
a thread pool.
"""

import concurrent.futures
import json
import os

import requests

GITHUB_API_URL = "https://api.github.com"

# How many PRs to enrich at once. Kept modest: GitHub applies a secondary
# "abuse" rate limit if too many requests arrive at once, which is harder
# to recover from than the normal 5000/hr quota.
MAX_WORKERS = 15

# Shared across every request so TCP/TLS connections to api.github.com are
# reused instead of reopened ~800 times per run. Safe across threads —
# requests.Session is documented as thread-safe for concurrent use.
_session = requests.Session()
_session.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=MAX_WORKERS))


# --- Shared request helpers -------------------------------------------

def _build_headers(token: str) -> dict:
    """Standard GitHub API auth headers, used by every request."""

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def _get(url: str, headers: dict, params: dict | None = None) -> requests.Response:
    """Make one authenticated GET request, raising on any error response."""
    response = _session.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response


def _paginated_get(url: str, headers: dict, params: dict | None = None) -> list[dict]:
    """
    Fetch every page of a list endpoint, following GitHub's Link header.

    Params are sent on the first request only — the "next" URL GitHub
    returns already has the full query string baked in.
    """
    results = []
    next_url = url

    while next_url is not None:
        response = _get(next_url, headers, params if next_url == url else None)
        results.extend(response.json())
        next_link = response.links.get("next")
        next_url = next_link["url"] if next_link else None

    return results


# --- GitHub endpoints ---------------------------------------------------
# Each function below builds a URL and delegates to the helpers above.

def get_closed_pull_requests(owner: str, repo: str, token: str) -> list[dict]:
    """
    Fetch all closed PRs, most recently updated first.

    Includes PRs closed without merging — filtering to merged ones
    (merged_at is not None) is the caller's job.
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls"
    params = {
        "state": "closed",
        "sort": "updated",
        "direction": "desc",
        "per_page": 100,
    }
    return _paginated_get(url, _build_headers(token), params)


def get_pr_reviews(owner: str, repo: str, pr_number: int, token: str) -> list[dict]:
    """Fetch all reviews on a PR. Each has a "state", e.g. "APPROVED"."""
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    return _paginated_get(url, _build_headers(token), params={"per_page": 100})


def get_commit_status(owner: str, repo: str, sha: str, token: str) -> dict:
    """
    Fetch the combined legacy commit status for a SHA (used by external CI).

    Returns a single object with "state" and "total_count".
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits/{sha}/status"
    return _get(url, _build_headers(token)).json()


def get_commit_check_runs(owner: str, repo: str, sha: str, token: str) -> list[dict]:
    """
    Fetch the check runs for a SHA (used by GitHub Actions).

    Only the first 100 are fetched; a single commit realistically never
    has more.
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits/{sha}/check-runs"
    response = _get(url, _build_headers(token), params={"per_page": 100})
    return response.json()["check_runs"]


# --- Building the raw dataset ------------------------------------------

def _fetch_pr_record(owner: str, repo: str, token: str, pr: dict) -> dict:
    """
    Fetch one merged PR's reviews, status, and check runs into a record.

    This is the unit of work run by each thread. The full API objects are
    kept as-is rather than trimmed, so transform.py has everything it needs.
    """
    pr_number = pr["number"]
    head_sha = pr["head"]["sha"]

    return {
        "pr_number": pr_number,
        "title": pr["title"],
        # user is null if the author's GitHub account was deleted
        "author": pr["user"]["login"] if pr.get("user") else None,
        "merged_at": pr["merged_at"],
        "reviews": get_pr_reviews(owner, repo, pr_number, token),
        "commit_status": get_commit_status(owner, repo, head_sha, token),
        "check_runs": get_commit_check_runs(owner, repo, head_sha, token),
    }


def build_raw_pr_dataset(owner: str, repo: str, token: str, merged_prs: list[dict]) -> list[dict]:
    """
    Fetch every merged PR's enrichment data, concurrently.

    Returns records in completion order, not PR order — transform.py sorts
    them before writing the report.
    """
    total = len(merged_prs)
    raw_dataset = []
    failures = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_pr_record, owner, repo, token, pr): pr
            for pr in merged_prs
        }

        # Counting completions here (single-threaded) keeps the progress
        # counter sequential, even though PRs finish in a random order.
        for count, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            pr_number = futures[future]["number"]
            try:
                raw_dataset.append(future.result())
                # \r rewrites this one line in place instead of scrolling
                # 272 lines of output. Safe to do here specifically because
                # this loop runs in the main thread, not a worker thread.
                print(f"\rFetching PRs... [{count}/{total}]", end="", flush=True)
            except requests.RequestException as error:
                # One network failure shouldn't discard the other ~270 PRs
                # already fetched, so record it and keep going. Non-network
                # errors are left to propagate, since those are real bugs.
                # Printed as its own full line (not \r-overwritten) so a
                # failure is never silently erased by later progress.
                failures.append(pr_number)
                print(f"\r[{count}/{total}] FAILED PR #{pr_number}: {error}")

    print()  # move off the in-place progress line before anything else prints

    if failures:
        print(f"\nWARNING: {len(failures)} of {total} PRs failed to fetch and are "
              f"missing from the report: {failures}")

    return raw_dataset


def save_json(data, filename: str) -> None:
    """
    Write data to a JSON file, creating the folder if needed.

    Generic on purpose — used for every extract-stage output (the closed
    PR listing, the merged subset, and the fully enriched dataset), not
    just one specific shape.
    """
    directory = os.path.dirname(filename)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
