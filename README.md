# Origami

**A data-driven engineering self-assessment framework.**

Origami scores engineers across six domains of engineering judgment using real data from your GitHub repos and git history, then calibrates through an interactive conversation. The result is a radar-like "origami plot" that shows where someone contributes — and where they're growing.

The intent behind the framework is that people should have the data to advocate for their own contributions and to plot their growth paths.

See a [real example assessment](sample/bomee-jung_2026-Q1.md) to get a feel for what the output looks like.

## The Six Domains
 
| Domain | What it measures |
|--------|-----------------|
| **Engineering Craft** | Shipped, secure, well-structured code. Architecture, security, design patterns, edge cases. |
| **Infrastructure & Quality** | Pipelines, monitoring, test strategy, CI policy, release workflows, bug prevention. |
| **Domain Knowledge** | Understanding the business domain — not just the code, but *why* the code is shaped that way. |
| **Decomposition** | Turning ambiguity into structured action. Scoping, diagnosis, ticket authorship, dependency mapping. |
| **Team Systems** | Designing how the team works. Workflow design, measurement, automation, tooling strategy. |
| **Peer Development** | Making others better. PR review depth, teaching through feedback, knowledge transfer. |

## Scoring Rubric

| Score | Label | What it looks like |
|-------|-------|--------------------|
| **1** | Following | Completes assigned work within established patterns. Works tickets that exist. |
| **2** | Owning | Self-directs without tickets. Finds and fixes problems without being asked. |
| **3** | Driving | Generates work for others, sets standards. Prevents problem classes, not just instances. |
| **4** | Shaping | Defines the team's approach. Writes the frameworks others use. |

**Key distinctions:**
- **1 vs 2:** Does this person *file* issues in this domain, or only *close* them?
- **2 vs 3:** A 2 fixes the instance. A 3 prevents the class.
- **3 vs 4:** A 3 sets standards within their domain. A 4 defines how the team approaches the domain itself.

## Tier Thresholds

| Tier | Criteria |
|------|----------|
| **F** | No domain above 1 |
| **E** | At least one domain at 2 |
| **D** | At least two domains at 3 |
| **C** | At least three domains at 3+, with 2+ in Team Systems |

  _These tiers are just what we happen to use at Cadence OneFive. There's nothing special about F-C._

## Philosophy

- **The goal is an accurate shape, not a high score.** A healthy team has diverse shapes — someone who's a 4 in Craft and a 1 in Team Systems is contributing differently than someone who's a 3 across the board. Both are valuable.
- **Scores describe what levels look like, not what to target.** Don't game the rubric.
- **One-off behaviors don't count.** Score on sustained patterns (3+ instances) over the assessment quarter.
- **Domain Knowledge is hardest to score from data.** Be honest about what the code shows vs. what you actually know about the business.
- **This is a conversation starter, not a performance review.** The assessment is a draft to spark a conversation about where to invest in growth.

## Quick Start

### Prerequisites

- Python 3.10+
- [GitHub CLI](https://cli.github.com/) (`gh`) — authenticated
- Local git clones of the repos you want to assess

### Setup

```bash
# Clone
git clone https://github.com/YOUR_ORG/origami.git
cd origami

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure your repos
cp config/repos.example.yaml config/repos.yaml
# Edit config/repos.yaml — add your repos with local paths and GitHub owner/repo

# Configure your team's identity map
cp config/identity-map.example.yaml config/identity-map.yaml
# Edit config/identity-map.yaml — map git aliases to canonical names
```

### Sync Data

```bash
# Full sync (first time — pulls all history)
bash scripts/extract_all.sh --full

# Incremental sync (subsequent runs — only fetches new data)
bash scripts/extract_all.sh
```

This populates `db/origami.sqlite` with commits, issues, and PRs from all configured repos.

### Run an Assessment

The interactive assessment runs through [Claude Code](https://claude.ai/code) (Anthropic's CLI tool). Install it, then run it from the repo root — the `/origami` command is bundled in `.claude/commands/` and picked up automatically:

```bash
# In the origami directory
claude
# Then type: /origami janedoe
```

Claude scores each domain from your data, then walks you through a calibration conversation where you agree or push back on each score. The output is a markdown report with origami plot SVGs.

### Generate a Plot Manually

```bash
# Single assessment
python3 scripts/origami_plot.py --name "Jane Doe" --scores 2,3,4,4,4,2 -o out.svg

# With calibration overlay (data-driven in blue, calibrated in red)
python3 scripts/origami_plot.py --name "Jane Doe" --scores 2,3,4,4,4,3 --calibrated 2,3,4,4,4,2 -o out.svg
```

Score order: Craft, Infra, Domain, Decomposition, Systems, PeerDev.

### Query the Database Directly

```bash
sqlite3 db/origami.sqlite

-- Who authored the most issues last quarter?
SELECT author, COUNT(*) as n
FROM issues WHERE created_at >= '2026-01-01'
GROUP BY author ORDER BY n DESC LIMIT 10;

-- Commits by person
SELECT author_canonical, COUNT(*), SUM(lines_added), SUM(lines_removed)
FROM commits WHERE date >= '2026-01-01' AND is_merge = 0
GROUP BY author_canonical ORDER BY COUNT(*) DESC;

-- Ticket authorship ratio (key origami signal)
SELECT
    i.author,
    COUNT(*) as authored,
    (SELECT COUNT(*) FROM issues i2
     WHERE i2.assignee = i.author AND i2.created_at >= '2026-01-01') as assigned
FROM issues i
WHERE i.created_at >= '2026-01-01'
GROUP BY i.author ORDER BY authored DESC;
```

## How It Works

### Data Pipeline

```
Git repos ──→ git_commits.py ──→ ┐
GitHub API ──→ github_issues.py ─→ ├──→ origami.sqlite
GitHub API ──→ github_prs.py ────→ ┘
```

Each extractor supports incremental sync — after the first full pull, subsequent runs only fetch new/updated data.

### Identity Resolution

Engineers appear under different names across git commits (`git config user.name`), GitHub PRs (login), and issues (login). The identity map in `config/identity-map.yaml` resolves all aliases to a canonical name, which is stored in the `author_canonical` column of the commits table.

### Assessment Flow

1. **Data collection** — Query SQLite for commits, issues, PRs, and reviews within the assessment quarter
2. **Classification** — Categorize the 15-20 most significant PRs and all self-authored issues into the 6 domains
3. **Scoring** — Apply the rubric based on sustained patterns (3+ instances), not one-offs
4. **Calibration** — Interactive conversation where you agree/disagree with each score
5. **Output** — Markdown report with data-driven and calibrated scores, origami plot SVGs, and growth targets

### The Origami Plot

Unlike a standard radar chart, the origami plot uses auxiliary axes between each main axis. This makes the enclosed area **invariant to axis ordering** — the shape means the same thing no matter how the domains are arranged. The auxiliary points sit at a fixed small radius, creating the star/origami pattern that gives the chart its name.

Based on: [Cañadas-Gómez et al. (2023) "Origami plot: a novel multivariate data visualization tool that improves radar chart"](https://www.sciencedirect.com/science/article/pii/S0957417423005079)
## Configuration Reference

### `config/repos.yaml`

```yaml
repositories:
  my-app:
    path: /home/you/code/my-app    # local git clone
    github: your-org/my-app         # GitHub owner/repo
```

### `config/identity-map.yaml`

```yaml
aliases:
  jdoe: "Jane Doe"              # git author name → canonical
  "jane doe": "Jane Doe"

github_handles:
  "Jane Doe": janedoe            # canonical → GitHub login

team_roles:
  "Jane Doe": "Senior Developer"  # context for AI scoring

exclude_paths:                    # excluded from line counts
  - "*.md"
  - "package-lock.json"

bots:                             # filtered from human metrics
  - "dependabot[bot]"
```

## Notes

References and takeaways that shaped the framework:

- [Duan et al. (2023) "Origami plot"](https://doi.org/10.1016/j.jclinepi.2023.02.020) — Radar charts distort area based on axis order. The origami plot fixes this by adding auxiliary axes, making the enclosed area invariant to how domains are arranged.
- [Scott Logic: A Critique of Radar Charts](https://blog.scottlogic.com/2011/09/23/a-critique-of-radar-charts.html) — Radar charts invite area comparisons that are mathematically meaningless. If you're going to visualize multivariate profiles, fix the geometry first.
- [Sullivan (2022), PLOS ONE: Information Loss in Likert Scales](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0271949) — 1-5 scales compress to 2-4 in practice because raters avoid extremes. A 4-point scale forces every score to be a real choice.
- [Greguras & Robie (1998): Interrater Reliability](https://link.springer.com/article/10.1007/BF02249609) — Rater disagreements are systematic, not random. Calibration needs to be anchored to shared evidence, not individual perception. This is why scores are data-driven first.
- [Jellyfish: Goodhart's Law in Software Engineering](https://jellyfish.co/blog/goodharts-law-in-software-engineering-and-how-to-avoid-gaming-your-metrics/) — The moment people know the rubric, they optimize for it. Scores describe what a level looks like, not what to do to get there.
- [Peña (2010), Medical Education Online: Dreyfus Model Critique](https://pmc.ncbi.nlm.nih.gov/articles/PMC2887319/) — No empirical evidence for discrete skill stages. Progression may be continuous, not stepped. Keep the levels as conversation anchors, not as truth.
- [PostHog: The Magic of Small Engineering Teams](https://posthog.com/newsletter/small-teams) — Small teams may not need formal leveling. This framework is a growth conversation tool, not a performance system.
- [Redd: Titles for Software Engineers](https://medium.com/@lindseyredd/titles-for-software-engineers-fe926318ef4a) — Judgment-based frameworks can entrench visibility bias. Data-driven scoring reduces dependence on who happened to notice the work.
- [NASA-TLX](https://en.wikipedia.org/wiki/NASA-TLX) — One of the most validated multidimensional assessments uses six dimensions. More axes means rater fatigue and domain overlap. We consolidated from ten to six.

## License

MIT
