#!/usr/bin/env python3
"""
Extract GitHub pull requests to SQLite database.
Default mode is incremental — stops when it reaches PRs older than the last sync.
"""

import argparse
import json
import sqlite3
import subprocess
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent.parent
DB_PATH = ROOT_DIR / "db" / "origami.sqlite"
REPOS_PATH = ROOT_DIR / "config" / "repos.yaml"

PER_PAGE = 100


def load_repos() -> dict:
    with open(REPOS_PATH) as f:
        return yaml.safe_load(f).get("repositories", {})


def fetch_pr_page(github_repo: str, page: int) -> list[dict]:
    cmd = [
        "gh", "api",
        f"repos/{github_repo}/pulls?state=all&sort=updated&direction=desc"
        f"&per_page={PER_PAGE}&page={page}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error fetching PRs page {page}: {result.stderr}")
        return []
    try:
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def fetch_prs_full(github_repo: str) -> list[dict]:
    cmd = [
        "gh", "api",
        f"repos/{github_repo}/pulls?state=all&per_page={PER_PAGE}",
        "--paginate",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error fetching PRs: {result.stderr}")
        return []
    prs = []
    try:
        data = json.loads(result.stdout)
        if isinstance(data, list):
            prs.extend(data)
    except json.JSONDecodeError:
        for line in result.stdout.strip().split("\n"):
            if line:
                try:
                    item = json.loads(line)
                    if isinstance(item, list):
                        prs.extend(item)
                    else:
                        prs.append(item)
                except json.JSONDecodeError:
                    continue
    return prs


def fetch_prs_incremental(github_repo: str, since: str | None) -> list[dict]:
    if not since:
        return fetch_prs_full(github_repo)
    collected: list[dict] = []
    page = 1
    while True:
        batch = fetch_pr_page(github_repo, page)
        if not batch:
            break
        collected.extend(batch)
        oldest_updated = min((p.get("updated_at") or "") for p in batch)
        if oldest_updated and oldest_updated < since:
            break
        if len(batch) < PER_PAGE:
            break
        page += 1
    return collected


def parse_pr(pr: dict) -> dict:
    return {
        "number": pr["number"],
        "title": pr.get("title", ""),
        "state": pr.get("state", ""),
        "author": pr.get("user", {}).get("login"),
        "created_at": pr.get("created_at", "")[:10] if pr.get("created_at") else None,
        "merged_at": pr.get("merged_at", "")[:10] if pr.get("merged_at") else None,
        "closed_at": pr.get("closed_at", "")[:10] if pr.get("closed_at") else None,
        "updated_at": pr.get("updated_at"),
        "additions": pr.get("additions", 0),
        "deletions": pr.get("deletions", 0),
        "changed_files": pr.get("changed_files", 0),
    }


def insert_prs(conn: sqlite3.Connection, repo: str, prs: list[dict]):
    conn.executemany(
        """INSERT OR REPLACE INTO pull_requests
        (repo, number, title, state, author, created_at, merged_at, closed_at,
         additions, deletions, changed_files, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(repo, p["number"], p["title"], p["state"], p["author"],
          p["created_at"], p["merged_at"], p["closed_at"],
          p["additions"], p["deletions"], p["changed_files"], p["updated_at"])
         for p in prs],
    )
    conn.commit()


def get_last_updated(conn: sqlite3.Connection, repo: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(updated_at) FROM pull_requests WHERE repo = ?", (repo,)
    ).fetchone()
    return row[0] if row and row[0] else None


def extract_repo(conn, repo_name, github_repo, full):
    print(f"\n{'='*60}")
    print(f"Extracting PRs: {repo_name} ({github_repo})")

    if full:
        print("  Mode: full")
        raw_prs = fetch_prs_full(github_repo)
    else:
        since = get_last_updated(conn, repo_name)
        if since:
            print(f"  Mode: incremental since {since}")
        else:
            print("  Mode: incremental (no prior sync — full pull)")
        raw_prs = fetch_prs_incremental(github_repo, since)

    print(f"  Fetched {len(raw_prs)} PRs")
    if not raw_prs:
        return

    parsed = [parse_pr(p) for p in raw_prs]
    insert_prs(conn, repo_name, parsed)

    merged = len([p for p in parsed if p["merged_at"]])
    print(f"  {merged} merged, {len(parsed) - merged} not merged")


def init_db(conn):
    with open(SCRIPT_DIR / "schema.sql") as f:
        conn.executescript(f.read())
    cols = {row[1] for row in conn.execute("PRAGMA table_info(pull_requests)")}
    if "updated_at" not in cols:
        conn.execute("ALTER TABLE pull_requests ADD COLUMN updated_at TIMESTAMP")
        conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Extract GitHub PRs to SQLite")
    parser.add_argument("--repo", help="Specific repo to extract (default: all)")
    parser.add_argument("--full", action="store_true", help="Refetch all PRs")
    args = parser.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    repos = load_repos()

    print("Origami - GitHub PRs Extractor")
    print(f"Database: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    init_db(conn)

    for repo_name, repo_config in repos.items():
        if args.repo and repo_name != args.repo:
            continue
        github = repo_config.get("github")
        if not github:
            continue
        extract_repo(conn, repo_name, github, args.full)

    cursor = conn.execute("""
        SELECT repo, COUNT(*), SUM(CASE WHEN merged_at IS NOT NULL THEN 1 ELSE 0 END)
        FROM pull_requests GROUP BY repo
    """)
    print(f"\n{'='*60}")
    print("Database totals:")
    for row in cursor:
        print(f"  {row[0]}: {row[1]} PRs ({row[2]} merged)")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
