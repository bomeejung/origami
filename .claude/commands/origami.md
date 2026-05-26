# Origami Self-Assessment

Generate an origami plot self-assessment for an engineer, write it to markdown, then walk them through calibrating each domain interactively.

**Arguments:** `$ARGUMENTS` — GitHub username or name (e.g., `janedoe`, `Jane`). If blank, detect from `git config user.name`.

## Context: The Origami Framework

### Six Domains of Engineering Judgment

1. **Engineering Craft** — Taking product requirements to shipped, secure, well-structured code. Architecture decisions, security, design patterns, edge cases, defensive coding. "Does this person build things that are correct, maintainable, and safe?"

2. **Infrastructure & Quality Systems** — Deployment pipelines, monitoring, DR, scaling, test strategy, CI policy, release workflows, bug prevention mechanisms. Keeping the platform running and preventing classes of problems.

3. **Domain Knowledge** — Understanding the business domain, not just the code. Why the data model is shaped a certain way, how the business rules actually work, what edge cases matter to users. Separates "correct code" from "the right code."

4. **Decomposition** — Turning ambiguity into structured, sequenced action. Scoping vague requirements, diagnosing production issues, filing structured tickets, identifying dependencies, routing work. The arc from "we need X" to "here's what we'll build, in what order, and why."

5. **Team Systems** — Designing how the team works. Workflow design, bottleneck removal, measurement, automation, tooling strategy, CI policy. The meta-layer: not doing the work, but designing how work gets done.

6. **Peer Development** — Making individual people better through direct interaction. PR review quality/depth, post-merge review, teaching through code feedback, pairing, knowledge transfer, unblocking others.

### 4-Point Scoring Rubric

| Score | Label | Relationship to work |
|-------|-------|---------------------|
| **1** | Following | Completes assigned work within established patterns. Works tickets that exist. |
| **2** | Owning | Self-directs without tickets. Finds and fixes problems without being asked, authors tickets from own observations. |
| **3** | Driving | Generates work for others, sets standards. Creates reusable mechanisms that prevent problem classes. |
| **4** | Shaping | Defines the team's approach. Writes the frameworks others use, makes strategic decisions about direction. |

### Key Distinctions

- **1 vs 2:** Ticket authorship. Does this person file issues in this domain, or only close them?
- **2 vs 3:** Team multiplication. A 2 fixes the instance. A 3 prevents the class.
- **3 vs 4:** Scope of influence. A 3 sets standards within their domain. A 4 defines how the team approaches the domain itself.

### Tier Thresholds

- **F:** No domain above 1
- **E:** At least one domain at 2
- **D:** At least two domains at 3
- **C:** At least three domains at 3+, with 2+ in Team Systems

## Steps

### 1. Ensure the database is up to date

The assessment pulls data from the SQLite database at `db/origami.sqlite`. If the DB doesn't exist or is stale, run the extraction first:

```bash
source .venv/bin/activate 2>/dev/null || true
bash scripts/extract_all.sh
```

If the venv doesn't exist, create it first:
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

### 2. Identify the engineer and all aliases

Read `config/identity-map.yaml` to find the canonical name and ALL aliases for this person.

If `$ARGUMENTS` is a GitHub handle (from the `github_handles` section), map it to the canonical name. If it's a name/alias (from the `aliases` section), resolve to the canonical name. If it matches neither, try `git config user.name`.

Also check the `bots` list — if the person is listed as a bot, something is wrong.

Set the assessment period to the **most recent completed quarter**:
- If today is in Q1 (Jan-Mar): assess Q4 of previous year (Oct 1 – Dec 31)
- If today is in Q2 (Apr-Jun): assess Q1 (Jan 1 – Mar 31)
- If today is in Q3 (Jul-Sep): assess Q2 (Apr 1 – Jun 30)
- If today is in Q4 (Oct-Dec): assess Q3 (Jul 1 – Sep 30)

Use the quarter label (e.g., "2026-Q1") for the output filename and headings.

### 3. Query the SQLite database

All data comes from `db/origami.sqlite`. The `author_canonical` column in commits resolves aliases automatically. Issues and PRs use `author` which stores the GitHub login.

```python
import sqlite3
conn = sqlite3.connect('db/origami.sqlite')

CANONICAL = "Jane Doe"          # from identity map
GITHUB_HANDLES = ["janedoe"]    # from github_handles + any aliases that are GitHub logins
START = "2026-01-01"            # quarter start
END = "2026-03-31"              # quarter end

# Commits
commits = conn.execute("""
    SELECT repo, COUNT(*) as n, SUM(lines_added) as added, SUM(lines_removed) as removed
    FROM commits WHERE author_canonical = ? AND date >= ? AND date <= ? AND is_merge = 0
    GROUP BY repo
""", [CANONICAL, START, END]).fetchall()

# Commit messages for classification (most recent 50)
messages = conn.execute("""
    SELECT date, repo, message, lines_added, lines_removed
    FROM commits WHERE author_canonical = ? AND date >= ? AND date <= ? AND is_merge = 0
    ORDER BY date DESC LIMIT 50
""", [CANONICAL, START, END]).fetchall()

# Issues authored (uses GitHub login)
issues_authored = conn.execute("""
    SELECT repo, COUNT(*) FROM issues
    WHERE author IN ({handles}) AND created_at >= ?
    GROUP BY repo
""".format(handles=','.join(f'"{h}"' for h in GITHUB_HANDLES)), [START]).fetchall()

# Issues assigned
issues_assigned = conn.execute("""
    SELECT repo, COUNT(*) FROM issues
    WHERE assignee IN ({handles}) AND created_at >= ?
    GROUP BY repo
""".format(handles=','.join(f'"{h}"' for h in GITHUB_HANDLES)), [START]).fetchall()

# Issue titles for classification
issue_titles = conn.execute("""
    SELECT number, created_at, title, issue_type, author
    FROM issues WHERE author IN ({handles}) AND created_at >= ?
    ORDER BY created_at DESC
""".format(handles=','.join(f'"{h}"' for h in GITHUB_HANDLES)), [START]).fetchall()

# PRs merged
prs = conn.execute("""
    SELECT repo, COUNT(*), SUM(additions), SUM(deletions)
    FROM pull_requests WHERE author IN ({handles}) AND merged_at >= ? AND merged_at <= ?
    GROUP BY repo
""".format(handles=','.join(f'"{h}"' for h in GITHUB_HANDLES)), [START, END]).fetchall()

# PR titles for classification (most significant by size)
pr_titles = conn.execute("""
    SELECT number, merged_at, title, additions, deletions, changed_files
    FROM pull_requests WHERE author IN ({handles}) AND merged_at >= ? AND merged_at <= ?
    ORDER BY (additions + deletions) DESC LIMIT 30
""".format(handles=','.join(f'"{h}"' for h in GITHUB_HANDLES)), [START, END]).fetchall()
```

Also check the identity_map table: `SELECT alias, canonical FROM identity_map WHERE canonical = ?`

For PR review counts (not in SQLite), use one `gh` call per repo:
```bash
gh api "search/issues?q=repo:OWNER/REPO+type:pr+reviewed-by:GITHUB_HANDLE+created:>START_DATE&per_page=1" --jq '.total_count'
```

### 4. Classify, calculate metrics, and score

**Classify** the 15-20 most significant PRs and all self-authored issues into the 6 domains. For each item ask:
- Assigned or generated? (ticket existed before, or they created it)
- Reactive or proactive?
- Individual or team impact?
- Domain knowledge signal?

**Calculate:**
- Ticket authorship ratio = self-authored / (self-authored + assigned)
- PR review volume
- Domain distribution of self-authored work

**Score** each domain using the decision tree:
1. Completes assigned work reliably? → at least 1
2. Finds/fixes problems without tickets? → at least 2
3. Work multiplies the team? → at least 3
4. Defines team's approach? → 4

Score on **sustained patterns** (3+ instances), not one-offs.

### 5. Write the initial assessment to markdown

Create the file at `origami-assessments/[firstname-lastname_YYYY-QN].md` (e.g., `jane-doe_2026-Q1.md`). Create the directory if needed.

The file MUST include a reference to generate the SVG chart:

````markdown
# Origami Self-Assessment: [Name]

**Assessment period:** [start] to [end]
**GitHub account(s):** [login(s)]
**Generated:** [today's date]

## Origami Plot

![Name — Data-Driven](firstname-lastname_YYYY-QN_initial.svg)

*(Scores: 1=Following, 2=Owning, 3=Driving, 4=Shaping. Max=4.)*

Generate this SVG by running:
```bash
python3 scripts/origami_plot.py --name "[Name]" --scores C,I,D,De,T,P -o origami-assessments/[firstname-lastname_YYYY-QN]_initial.svg
```

## Summary

**Data:** [X] commits, [Y] PRs merged, [Z] issues authored, [W] issues assigned, [V] PR reviews
**Ticket authorship ratio:** [X]%
**Total score:** [sum]/24
**Tier:** [F/E/D/C] — [one sentence rationale]

## Data-Driven Scores

### 1. Engineering Craft — [score] ([label])

**Evidence:** [2-3 sentences with specific PR/issue numbers]

### 2. Infrastructure & Quality Systems — [score] ([label])

**Evidence:** [2-3 sentences]

### 3. Domain Knowledge — [score] ([label])

**Evidence:** [2-3 sentences]

### 4. Decomposition — [score] ([label])

**Evidence:** [2-3 sentences]

### 5. Team Systems — [score] ([label])

**Evidence:** [2-3 sentences]

### 6. Peer Development — [score] ([label])

**Evidence:** [2-3 sentences]

## Origami Shape

[Describe the shape — peaks, valleys, what it says about how this person contributes]

## Growth Signals

[Early behaviors that predict tier transition, with specific PR/issue refs]

---

## Self-Calibration

*Completed interactively on [date].*

*(This section is filled in during the calibration conversation below.)*
````

Write this file immediately. Tell the user where you saved it.

### 6. Walk through each domain — interactive calibration

Now go through each of the 6 domains **one at a time**. For each domain:

1. Show the engineer the score and the evidence summary
2. Ask: **"Do you strongly agree, agree, disagree (too high), or disagree (too low) with this score? Why?"**
3. Wait for their response
4. If they disagree, clarify direction if ambiguous — "You think this should be higher or lower?" Then discuss — push back with evidence if you think the data supports the score, or concede if their reasoning is sound
5. Record their response (including direction if they disagreed) AND any adjusted score

After the engineer responds, **append** to the Self-Calibration section of the markdown file (do NOT overwrite the Data-Driven Scores — those stay as the original automated assessment):

```markdown
### [Domain Name]

**Data-driven score:** [X] | **Self-assessment:** [strongly agree / agree / disagree / strongly disagree]
**Adjusted score:** [X or new score if changed]

> [Engineer's verbatim reasoning, quoted]

*[Any notes from the discussion — where you pushed back, what was resolved]*
```

### 7. Final summary and updated chart

After all 6 domains are calibrated, append a final section to the markdown:

````markdown
---

## Calibrated Results

![Name — Calibrated](firstname-lastname_YYYY-QN_calibrated.svg)

Generate this SVG by running:
```bash
python3 scripts/origami_plot.py --name "[Name]" --scores [original] --calibrated [adjusted] -o origami-assessments/[firstname-lastname_YYYY-QN]_calibrated.svg
```

| Domain | Data-Driven | Self-Assessment | Calibrated | Delta |
|--------|-------------|-----------------|------------|-------|
| Engineering Craft | X | [response] | Y | [+/-/=] |
| Infra & Quality | X | [response] | Y | [+/-/=] |
| Domain Knowledge | X | [response] | Y | [+/-/=] |
| Decomposition | X | [response] | Y | [+/-/=] |
| Team Systems | X | [response] | Y | [+/-/=] |
| Peer Development | X | [response] | Y | [+/-/=] |

**Calibrated total:** [sum]/24
**Calibrated tier:** [F/E/D/C]

## Growth Targets

[1-2 specific, observable goals for next quarter based on the calibration conversation]

## Starfish

For the domain(s) the engineer most wants to grow in:

- **Keep doing:**
- **More of:**
- **Less of:**
- **Stop:**
- **Start:**
````

### 8. Wrap up

Tell the engineer where the final file is saved. Remind them this is a draft to bring to their 1:1 for manager calibration.

## Important Notes

- **The Data-Driven Scores section is NEVER modified after initial write.** It's the automated baseline. Calibration goes in the Self-Calibration section.
- **Scores describe what levels look like, not what to target.** Don't game the rubric.
- **One-off behaviors don't count.** 3+ instances over the assessment period.
- **Domain Knowledge is hardest to score from data.** Be honest about what you know vs. what the code shows.
- **The goal is an accurate shape, not a high score.**
- **Push back respectfully.** If an engineer says "strongly disagree" but the data clearly supports the score, say so. The conversation is where the real calibration happens.
- **This is a draft for their 1:1.** Manager has context the data can't capture.
