#!/usr/bin/env python3
"""
Extract GitHub issues to SQLite database.
Supports full and incremental syncs across all configured repos.
"""

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent.parent
DB_PATH = ROOT_DIR / "db" / "origami.sqlite"
REPOS_PATH = ROOT_DIR / "config" / "repos.yaml"

GRAPHQL_QUERY = """
query($owner: String!, $name: String!, $since: DateTime, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issues(
      first: 50,
      after: $cursor,
      states: [OPEN, CLOSED],
      filterBy: {since: $since},
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        body
        state
        createdAt
        updatedAt
        closedAt
        author { login }
        assignees(first: 10) { nodes { login } }
        labels(first: 50) { nodes { name } }
        milestone { title }
        issueType { name }
        timelineItems(itemTypes: [CONNECTED_EVENT, CROSS_REFERENCED_EVENT], first: 20) {
          nodes {
            __typename
            ... on ConnectedEvent { subject { ... on PullRequest { number state } } }
            ... on CrossReferencedEvent { source { ... on PullRequest { number state } } }
          }
        }
      }
    }
  }
}
"""


def load_repos() -> dict:
    with open(REPOS_PATH) as f:
        return yaml.safe_load(f).get("repositories", {})


def gh_graphql(variables: dict) -> dict | None:
    cmd = ["gh", "api", "graphql", "-f", f"query={GRAPHQL_QUERY}"]
    for k, v in variables.items():
        if v is None:
            continue
        cmd += ["-f", f"{k}={v}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"GraphQL error: {result.stderr}", file=sys.stderr)
        return None
    data = json.loads(result.stdout)
    if "errors" in data:
        print(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}", file=sys.stderr)
        return None
    return data


def fetch_issues(github_repo: str, since: str | None = None) -> list[dict]:
    owner, name = github_repo.split("/", 1)
    all_issues: list[dict] = []
    cursor = None
    since_iso = f"{since}T00:00:00Z" if since else None

    while True:
        variables = {"owner": owner, "name": name, "since": since_iso, "cursor": cursor}
        data = gh_graphql(variables)
        if not data:
            break
        conn = data["data"]["repository"]["issues"]
        all_issues.extend(conn["nodes"])
        if not conn["pageInfo"]["hasNextPage"]:
            break
        cursor = conn["pageInfo"]["endCursor"]
        print(f"  ...{len(all_issues)} fetched")
        time.sleep(0.2)
    return all_issues


def parse_issue(issue: dict) -> dict:
    issue_type = (issue.get("issueType") or {}).get("name")
    labels = [n["name"] for n in (issue.get("labels") or {}).get("nodes", [])]
    assignee_logins = [n["login"] for n in (issue.get("assignees") or {}).get("nodes", [])]
    milestone = (issue.get("milestone") or {}).get("title")
    author = (issue.get("author") or {}).get("login")

    prs = []
    seen = set()
    for t in (issue.get("timelineItems") or {}).get("nodes", []):
        pr = t.get("subject") or t.get("source") or {}
        num = pr.get("number")
        if num is None or num in seen:
            continue
        seen.add(num)
        prs.append({"number": num, "state": pr.get("state")})

    return {
        "number": issue["number"],
        "title": issue.get("title", ""),
        "body": issue.get("body", ""),
        "issue_type": issue_type,
        "state": (issue.get("state") or "").lower(),
        "created_at": issue.get("createdAt"),
        "updated_at": issue.get("updatedAt"),
        "closed_at": issue.get("closedAt"),
        "author": author,
        "assignee": assignee_logins[0] if assignee_logins else None,
        "assignees": json.dumps(assignee_logins),
        "labels": json.dumps(labels),
        "linked_prs": json.dumps(prs),
        "milestone": milestone,
    }


UPSERT_SQL = """
INSERT INTO issues
  (repo, number, title, body, issue_type, state, created_at, updated_at, closed_at,
   author, assignee, assignees, labels, linked_prs, milestone, last_synced)
VALUES
  (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
ON CONFLICT(repo, number) DO UPDATE SET
  title=excluded.title,
  body=excluded.body,
  issue_type=excluded.issue_type,
  state=excluded.state,
  updated_at=excluded.updated_at,
  closed_at=excluded.closed_at,
  author=excluded.author,
  assignee=excluded.assignee,
  assignees=excluded.assignees,
  labels=excluded.labels,
  linked_prs=excluded.linked_prs,
  milestone=excluded.milestone,
  last_synced=datetime('now')
"""


def insert_issues(conn: sqlite3.Connection, repo: str, issues: list[dict]):
    conn.executemany(
        UPSERT_SQL,
        [(repo, i["number"], i["title"], i["body"], i["issue_type"], i["state"],
          i["created_at"], i["updated_at"], i["closed_at"], i["author"],
          i["assignee"], i["assignees"], i["labels"], i["linked_prs"], i["milestone"])
         for i in issues],
    )
    conn.commit()


def get_last_sync_date(conn: sqlite3.Connection, repo: str) -> str | None:
    row = conn.execute(
        """SELECT completed_at FROM sync_log
           WHERE sync_type='issues' AND repo=? AND completed_at IS NOT NULL
           ORDER BY completed_at DESC LIMIT 1""",
        (repo,),
    ).fetchone()
    return row[0][:10] if row and row[0] else None


def extract_repo(conn, repo_name, github_repo, since):
    print(f"\n{'='*60}")
    print(f"Extracting issues: {repo_name} ({github_repo})")
    if since:
        print(f"  Since: {since}")

    log_id = conn.execute(
        "INSERT INTO sync_log (sync_type, repo) VALUES ('issues', ?)", (repo_name,)
    ).lastrowid
    conn.commit()

    raw_issues = fetch_issues(github_repo, since=since)
    print(f"  Found {len(raw_issues)} issues")

    if raw_issues:
        parsed = [parse_issue(i) for i in raw_issues]
        insert_issues(conn, repo_name, parsed)

    conn.execute(
        "UPDATE sync_log SET completed_at = datetime('now'), rows_synced = ? WHERE id = ?",
        (len(raw_issues), log_id),
    )
    conn.commit()


def init_db(conn):
    with open(SCRIPT_DIR / "schema.sql") as f:
        conn.executescript(f.read())


def main():
    parser = argparse.ArgumentParser(description="Extract GitHub issues to SQLite")
    parser.add_argument("--repo", help="Specific repo to extract (default: all)")
    parser.add_argument("--since", help="Only fetch issues updated since YYYY-MM-DD")
    parser.add_argument("--full", action="store_true", help="Full re-fetch (ignore last_sync)")
    parser.add_argument("--incremental", action="store_true", help="Resume from last sync_log entry")
    args = parser.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    repos = load_repos()

    print("Origami - GitHub Issues Extractor")
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
            print(f"Skipping {repo_name}: no github config")
            continue

        since = args.since
        if args.incremental and not since and not args.full:
            since = get_last_sync_date(conn, repo_name)
            if since:
                print(f"  Resuming from last sync: {since}")

        extract_repo(conn, repo_name, github, since=since)

    cursor = conn.execute(
        """SELECT repo, COUNT(*), SUM(state='open'), SUM(state='closed')
           FROM issues GROUP BY repo ORDER BY repo"""
    )
    print(f"\n{'='*60}")
    print("Database totals:")
    for repo, total, open_c, closed_c in cursor:
        print(f"  {repo}: {total} ({open_c} open, {closed_c} closed)")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
