# Origami — Claude Code Instructions

**Data-driven engineering self-assessment framework.**

## Data Architecture

All data lives in `db/origami.sqlite`. Extract scripts in `scripts/extract/` sync from GitHub/git into this DB.

### Syncing data

```bash
bash scripts/extract_all.sh              # incremental
bash scripts/extract_all.sh --full       # full re-sync
```

Individual extractors:
```bash
python3 scripts/extract/git_commits.py          # commits from local repos
python3 scripts/extract/github_issues.py         # issues via GitHub API
python3 scripts/extract/github_prs.py            # PRs via GitHub API
```

### Querying

Use SQL against `db/origami.sqlite` for any data questions. Don't hit the GitHub API when the DB already has the data.

Key tables: `issues`, `pull_requests`, `commits`, `identity_map`, `sync_log`.

## Running Assessments

Use `/origami <username>` to run an interactive assessment. The command is defined in `.claude/commands/origami.md`.

## Configuration

- `config/repos.yaml` — repositories to track
- `config/identity-map.yaml` — git author aliases, GitHub handles, team roles, bot list
