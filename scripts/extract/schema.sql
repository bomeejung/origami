-- Origami SQLite Schema
-- Run: sqlite3 db/origami.sqlite < scripts/extract/schema.sql

CREATE TABLE IF NOT EXISTS commits (
    sha TEXT NOT NULL,
    repo TEXT NOT NULL,
    author_raw TEXT NOT NULL,
    author_canonical TEXT NOT NULL,
    date DATE NOT NULL,
    message TEXT,
    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,
    is_merge BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (sha, repo)
);

CREATE TABLE IF NOT EXISTS issues (
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    title TEXT,
    body TEXT,
    issue_type TEXT,
    state TEXT,
    created_at DATE,
    updated_at TIMESTAMP,
    closed_at DATE,
    author TEXT,
    assignee TEXT,
    assignees TEXT,        -- JSON array
    labels TEXT,           -- JSON array
    linked_prs TEXT,       -- JSON array of {number, state}
    milestone TEXT,
    priority TEXT,
    effort TEXT,
    last_synced TIMESTAMP,
    PRIMARY KEY (repo, number)
);

CREATE TABLE IF NOT EXISTS pull_requests (
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    title TEXT,
    state TEXT,
    author TEXT,
    created_at DATE,
    merged_at DATE,
    closed_at DATE,
    additions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    changed_files INTEGER DEFAULT 0,
    updated_at TIMESTAMP,
    PRIMARY KEY (repo, number)
);

CREATE TABLE IF NOT EXISTS identity_map (
    alias TEXT PRIMARY KEY,
    canonical TEXT NOT NULL,
    is_bot BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS project_items (
    repo TEXT NOT NULL,
    issue_number INTEGER NOT NULL,
    project_item_id TEXT,
    project_status TEXT,
    priority TEXT,
    sprint TEXT,
    release_no TEXT,
    status_updated_at DATE,
    last_synced TIMESTAMP,
    PRIMARY KEY (repo, issue_number)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_type TEXT NOT NULL,
    repo TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    rows_synced INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_commits_date ON commits(date);
CREATE INDEX IF NOT EXISTS idx_commits_author ON commits(author_canonical);
CREATE INDEX IF NOT EXISTS idx_commits_repo_date ON commits(repo, date);
CREATE INDEX IF NOT EXISTS idx_issues_type ON issues(issue_type);
CREATE INDEX IF NOT EXISTS idx_issues_created ON issues(created_at);
CREATE INDEX IF NOT EXISTS idx_issues_repo_type ON issues(repo, issue_type);
CREATE INDEX IF NOT EXISTS idx_prs_merged ON pull_requests(merged_at);
CREATE INDEX IF NOT EXISTS idx_prs_repo_merged ON pull_requests(repo, merged_at);
CREATE INDEX IF NOT EXISTS idx_project_items_status ON project_items(project_status);
