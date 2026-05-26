#!/bin/bash
# Origami - Full Data Extraction
# Syncs git commits, GitHub issues, and GitHub PRs into SQLite.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$ROOT_DIR/.venv/bin/activate" ]; then
    source "$ROOT_DIR/.venv/bin/activate"
fi

echo "Origami - Full Data Extraction"
echo "=================================="
echo ""

if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required"
    exit 1
fi

if ! command -v gh &> /dev/null; then
    echo "Error: gh CLI is required (brew install gh)"
    exit 1
fi

if [ ! -f "$ROOT_DIR/config/repos.yaml" ]; then
    echo "Error: config/repos.yaml not found"
    echo "Copy config/repos.example.yaml to config/repos.yaml and configure your repos."
    exit 1
fi

if [ ! -f "$ROOT_DIR/config/identity-map.yaml" ]; then
    echo "Error: config/identity-map.yaml not found"
    echo "Copy config/identity-map.example.yaml to config/identity-map.yaml and configure your team."
    exit 1
fi

FULL_FLAG=""
SEQUENTIAL=0
for arg in "$@"; do
    case "$arg" in
        --full) FULL_FLAG="--full" ;;
        --sequential) SEQUENTIAL=1 ;;
    esac
done

if [[ -n "$FULL_FLAG" ]]; then
    echo "Mode: Full extraction (all history)"
else
    echo "Mode: Incremental update"
fi
echo ""

mkdir -p "$ROOT_DIR/db"
LOG_DIR="$ROOT_DIR/db/extract-logs"
mkdir -p "$LOG_DIR"

python3 -c "
import sqlite3, pathlib
p = pathlib.Path('$ROOT_DIR/db/origami.sqlite')
conn = sqlite3.connect(p)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA busy_timeout=60000')
schema = pathlib.Path('$SCRIPT_DIR/extract/schema.sql').read_text()
conn.executescript(schema)
conn.close()
"

ISSUES_FLAG="--incremental"
if [[ "$FULL_FLAG" == "--full" ]]; then
    ISSUES_FLAG="--full"
fi

run_step() {
    local name="$1"; shift
    local log="$LOG_DIR/$name.log"
    if [[ "$SEQUENTIAL" == "1" ]]; then
        echo "→ $name"
        "$@" 2>&1 | tee "$log"
    else
        echo "→ $name (background, log: $log)"
        ( "$@" >"$log" 2>&1 ) &
    fi
}

start=$SECONDS

run_step "git_commits"   python3 "$SCRIPT_DIR/extract/git_commits.py"   $FULL_FLAG
run_step "github_issues" python3 "$SCRIPT_DIR/extract/github_issues.py" $ISSUES_FLAG
run_step "github_prs"    python3 "$SCRIPT_DIR/extract/github_prs.py"    $FULL_FLAG

if [[ "$SEQUENTIAL" != "1" ]]; then
    fail=0
    for pid in $(jobs -p); do
        if ! wait "$pid"; then
            fail=1
        fi
    done
    echo ""
    echo "--- per-step tails ---"
    for f in "$LOG_DIR"/*.log; do
        echo ""
        echo "### $(basename "$f" .log)"
        tail -n 8 "$f"
    done
    if [[ "$fail" == "1" ]]; then
        echo ""
        echo "One or more extractors failed — see logs in $LOG_DIR"
        exit 1
    fi
fi

elapsed=$((SECONDS - start))
echo ""
echo "=================================="
echo "Extraction complete in ${elapsed}s"
echo "Database: $ROOT_DIR/db/origami.sqlite"
