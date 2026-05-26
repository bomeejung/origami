#!/usr/bin/env python3
"""
Extract git commits to SQLite database.
Handles identity resolution and incremental updates.
"""

import argparse
import fnmatch
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent.parent
DB_PATH = ROOT_DIR / "db" / "origami.sqlite"
CONFIG_DIR = ROOT_DIR / "config"
IDENTITY_MAP_PATH = CONFIG_DIR / "identity-map.yaml"
REPOS_PATH = CONFIG_DIR / "repos.yaml"


def load_identity_map() -> tuple[dict[str, str], set[str], list[str]]:
    with open(IDENTITY_MAP_PATH) as f:
        config = yaml.safe_load(f)
    aliases = config.get("aliases", {})
    bots = set(config.get("bots", []))
    exclude_paths = config.get("exclude_paths", [])
    return aliases, bots, exclude_paths


def load_repos() -> dict:
    with open(REPOS_PATH) as f:
        config = yaml.safe_load(f)
    return config.get("repositories", {})


def resolve_author(author: str, aliases: dict[str, str]) -> str:
    return aliases.get(author, author)


def get_commits(repo_path: str, since: str = None) -> list[dict]:
    cmd = [
        "git", "-C", repo_path, "log",
        "--pretty=format:%H|%an|%aI|%s",
        "--no-merges"
    ]
    if since:
        cmd.append(f"--since={since}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error getting commits: {result.stderr}")
        return []

    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        sha, author, date, message = parts
        commits.append({
            "sha": sha,
            "author_raw": author,
            "date": date[:10],
            "message": message,
            "lines_added": 0,
            "lines_removed": 0,
            "is_merge": False,
        })
    return commits


def should_exclude_file(filepath: str, exclude_patterns: list[str]) -> bool:
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(filepath, pattern):
            return True
        if fnmatch.fnmatch(os.path.basename(filepath), pattern):
            return True
    return False


def get_commit_stats(repo_path: str, sha: str, exclude_patterns: list[str] = None) -> tuple[int, int]:
    cmd = ["git", "-C", repo_path, "show", "--numstat", "--format=", sha]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if exclude_patterns is None:
        exclude_patterns = []

    added = removed = 0
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            filepath = parts[2]
            if " => " in filepath:
                filepath = filepath.split(" => ")[-1].rstrip("}")
                if "{" in filepath:
                    filepath = filepath.replace("{", "")
            if should_exclude_file(filepath, exclude_patterns):
                continue
            try:
                a = int(parts[0]) if parts[0] != "-" else 0
                r = int(parts[1]) if parts[1] != "-" else 0
                added += a
                removed += r
            except ValueError:
                pass
    return added, removed


def get_merge_commits(repo_path: str, since: str = None) -> set[str]:
    cmd = ["git", "-C", repo_path, "log", "--merges", "--pretty=format:%H"]
    if since:
        cmd.append(f"--since={since}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return set(result.stdout.strip().split("\n")) if result.stdout else set()


def get_last_commit_date(conn: sqlite3.Connection, repo: str) -> str | None:
    row = conn.execute("SELECT MAX(date) FROM commits WHERE repo = ?", (repo,)).fetchone()
    return row[0] if row and row[0] else None


def insert_commits(conn: sqlite3.Connection, repo: str, commits: list[dict]):
    conn.executemany(
        """INSERT OR REPLACE INTO commits
        (sha, repo, author_raw, author_canonical, date, message, lines_added, lines_removed, is_merge)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(c["sha"], repo, c["author_raw"], c["author_canonical"],
          c["date"], c["message"], c["lines_added"], c["lines_removed"], c["is_merge"])
         for c in commits],
    )
    conn.commit()


def extract_repo(conn, repo_name, repo_path, aliases, bots, exclude_patterns=None, full=False):
    print(f"\n{'='*60}")
    print(f"Extracting: {repo_name}")
    print(f"Path: {repo_path}")

    if not os.path.isdir(os.path.join(repo_path, ".git")):
        print(f"  ERROR: Not a git repository")
        return

    since = None
    if not full:
        last_date = get_last_commit_date(conn, repo_name)
        if last_date:
            since = last_date
            print(f"  Incremental update from: {since}")

    if not since:
        print(f"  Full extraction (all history)")

    print(f"  Fetching commits...")
    commits = get_commits(repo_path, since)
    print(f"  Found {len(commits)} commits")

    if not commits:
        print(f"  No new commits to process")
        return

    merge_shas = get_merge_commits(repo_path, since)

    print(f"  Processing commits (getting stats)...")
    for i, commit in enumerate(commits):
        commit["author_canonical"] = resolve_author(commit["author_raw"], aliases)
        commit["is_merge"] = commit["sha"] in merge_shas
        added, removed = get_commit_stats(repo_path, commit["sha"], exclude_patterns or [])
        commit["lines_added"] = added
        commit["lines_removed"] = removed
        if (i + 1) % 100 == 0:
            print(f"    Processed {i + 1}/{len(commits)} commits...")

    print(f"  Inserting into database...")
    insert_commits(conn, repo_name, commits)

    non_bot = [c for c in commits if c["author_canonical"] not in bots]
    print(f"  Done: {len(non_bot)} human commits, {len(commits) - len(non_bot)} bot commits")


def init_db(conn):
    with open(SCRIPT_DIR / "schema.sql") as f:
        conn.executescript(f.read())


def main():
    parser = argparse.ArgumentParser(description="Extract git commits to SQLite")
    parser.add_argument("--full", action="store_true", help="Full extraction (ignore existing data)")
    parser.add_argument("--repo", help="Specific repo to extract (default: all)")
    args = parser.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    aliases, bots, exclude_patterns = load_identity_map()
    repos = load_repos()

    print("Origami - Git Commit Extractor")
    print(f"Database: {DB_PATH}")
    print(f"Identity aliases: {len(aliases)}")

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    init_db(conn)

    for alias, canonical in aliases.items():
        conn.execute(
            "INSERT OR REPLACE INTO identity_map (alias, canonical, is_bot) VALUES (?, ?, ?)",
            (alias, canonical, False),
        )
    for bot in bots:
        conn.execute(
            "INSERT OR REPLACE INTO identity_map (alias, canonical, is_bot) VALUES (?, ?, ?)",
            (bot, bot, True),
        )
    conn.commit()

    for repo_name, repo_config in repos.items():
        if args.repo and repo_name != args.repo:
            continue
        extract_repo(conn, repo_name, repo_config["path"], aliases, bots, exclude_patterns, args.full)

    cursor = conn.execute("SELECT repo, COUNT(*) FROM commits GROUP BY repo")
    print(f"\n{'='*60}")
    print("Database totals:")
    for row in cursor:
        print(f"  {row[0]}: {row[1]:,} commits")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
