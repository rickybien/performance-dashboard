# PROJECT_SPEC.md — Engineering Metrics Dashboard

## 1. Config Schema (config.yaml)

This is the most important file. It defines all mappings.

```yaml
# config.yaml

# Jira connection
jira:
  base_url: "https://your-company.atlassian.net"
  # credentials come from environment variables: JIRA_EMAIL, JIRA_TOKEN

# GitHub connection
github:
  org: "your-org-name"
  # token comes from env: GITHUB_TOKEN

# Jenkins connection (optional, Phase 3)
jenkins:
  base_url: "https://jenkins.your-company.com"
  # credentials from env: JENKINS_USER, JENKINS_TOKEN

# ============================================================
# Status → Phase Mapping
# ============================================================
# Each team/project may have different Jira status names.
# We define a default mapping, then allow per-project overrides.
#
# Phases (in order):
#   backlog    - Not yet being worked on
#   planning   - SA/SD/Analysis/Design
#   dev        - Active development (coding)
#   review     - PR review / code review
#   dev_test   - Developer testing (RD-side testing)
#   qa         - QA team testing
#   staging    - On staging / regression
#   done       - Released / closed

status_mapping:
  default:
    backlog:
      - "To Do"
      - "Backlog"
      - "Pending"
      - "Open"
      - "待處理"
    planning:
      - "Analysis"
      - "SA/SD"
      - "In Analysis"
      - "Design"
      - "Planning"
      - "規劃中"
      - "需求分析"
    dev:
      - "In Progress"
      - "In Development"
      - "Developing"
      - "開發中"
    review:
      - "In Review"
      - "Code Review"
      - "PR Review"
      - "審查中"
    dev_test:
      - "Dev Testing"
      - "RD Testing"
      - "開發測試"
      - "RD 測試中"
    qa:
      - "QA"
      - "QA Testing"
      - "In QA"
      - "QA 測試中"
    staging:
      - "Staging"
      - "Regression"
      - "UAT"
      - "Stage 環境"
    done:
      - "Done"
      - "Released"
      - "Closed"
      - "已完成"
      - "已上線"

  # Per-project overrides (only need to specify differences)
  overrides:
    PROJ-A:
      planning:
        - "Requirement Review"
        - "System Design"
    PROJ-B:
      review:
        - "Awaiting Review"

# ============================================================
# Team → Project → Repo Mapping
# ============================================================
teams:
  - name: "Team Alpha"
    id: "team-alpha"
    jira_projects:
      - "PROJ-A"
      - "PROJ-B"
    github_repos:
      - "service-auth"
      - "service-user"
      - "lib-common"
    jenkins_jobs: []  # Phase 3

  - name: "Team Beta"
    id: "team-beta"
    jira_projects:
      - "PROJ-C"
    github_repos:
      - "service-payment"
      - "service-billing"
    jenkins_jobs: []

  # ... repeat for all 18 teams

# ============================================================
# Collection Settings
# ============================================================
collection:
  # How many days of history to collect on each run
  lookback_days: 90
  # How many days for "recent" metrics (shown on dashboard)
  recent_days: 30
  # Jira JQL base filter (optional, e.g., exclude certain issue types)
  jira_jql_filter: "issuetype in (Story, Bug, Task, Sub-task)"
  # PR → Jira linking pattern (regex to extract issue key from branch/PR title)
  pr_issue_pattern: "([A-Z][A-Z0-9]+-\\d+)"
```

## 2. Data Pipeline Output Schema (dashboard.json)

```jsonc
{
  "generated_at": "2026-02-27T02:00:00Z",
  "period": {
    "start": "2026-01-28",
    "end": "2026-02-27"
  },
  "summary": {
    // Org-wide summary
    "total_completed_issues": 612,
    "avg_cycle_time_days": 8.3,
    "avg_cycle_time_prev_period": 9.1,  // For trend comparison
    "total_prs_merged": 489,
    "avg_pr_pickup_hours": 6.2
  },
  "teams": {
    "team-alpha": {
      "name": "Team Alpha",
      "projects": {
        "PROJ-A": {
          "cycle_time": {
            // All values in days (decimal)
            "planning":  { "p50": 2.5, "p85": 5.0, "count": 45 },
            "dev":       { "p50": 3.0, "p85": 6.0, "count": 42 },
            "review":    { "p50": 1.0, "p85": 2.5, "count": 40 },
            "dev_test":  { "p50": 0.5, "p85": 1.0, "count": 38 },
            "qa":        { "p50": 1.5, "p85": 3.0, "count": 35 },
            "staging":   { "p50": 0.5, "p85": 1.0, "count": 34 },
            "total":     { "p50": 9.0, "p85": 18.5, "count": 45 }
          },
          "throughput": {
            "completed_issues": 34,
            "story_points": 89,
            "weekly_trend": [8, 7, 10, 9]  // Last 4 weeks
          },
          "pr_metrics": {
            "total_prs": 52,
            "avg_pickup_hours": 8.2,
            "avg_review_hours": 14.5,
            "avg_review_rounds": 2.1,
            "avg_additions": 145,
            "avg_deletions": 62,
            "large_pr_count": 5,       // PRs with >400 lines changed
            "merge_rate": 0.92
          }
        }
        // ... more projects
      },
      // Team-level aggregated metrics (across all projects)
      "aggregated": {
        "cycle_time": { /* same structure */ },
        "throughput": { /* same structure */ },
        "pr_metrics": { /* same structure */ }
      }
    }
    // ... more teams
  },
  // Historical data for trend charts (weekly snapshots)
  "trends": {
    "team-alpha": {
      "weeks": ["2026-W04", "2026-W05", "2026-W06", "2026-W07"],
      "cycle_time_p50": [9.5, 9.0, 8.5, 9.0],
      "throughput": [8, 7, 10, 9],
      "pr_pickup_hours": [10.1, 8.5, 7.8, 8.2]
    }
    // ... more teams
  }
}
```

## 3. Python Pipeline Details

### 3.1 collect_jira.py

Core logic:

1. For each team's Jira projects, run JQL: `project = {key} AND status changed DURING (-{lookback_days}d, now()) AND {jql_filter}`
2. For each issue, fetch changelog via `/rest/api/3/issue/{key}?expand=changelog`
3. Parse changelog to find status transitions with timestamps
4. Calculate time spent in each status (in hours)
5. Map statuses to phases using config.yaml mapping (with fallback to default)
6. Return structured data per issue:

```python
@dataclass
class IssueMetrics:
    key: str               # e.g., "PROJ-A-123"
    project: str           # e.g., "PROJ-A"
    issue_type: str        # e.g., "Story"
    created: datetime
    resolved: Optional[datetime]
    phase_durations: dict[str, float]  # phase_name → hours
    # e.g., {"planning": 48.5, "dev": 72.0, "review": 24.0, ...}
    current_status: str
    assignee: Optional[str]
```

**Important edge cases:**
- Issues that move backward (e.g., QA → Dev) — count time in each phase visit, sum them up
- Issues with statuses not in the mapping — log a warning, categorize as "unmapped"
- Issues still in progress (no resolution) — still calculate time in completed phases
- Pagination: Jira returns max 100 results per page, must paginate
- Rate limiting: add 0.5s delay between API calls

### 3.2 collect_github.py

Core logic:

1. For each team's repos, fetch merged PRs in the lookback period via GitHub API
2. For each PR, fetch review timeline
3. Extract Jira issue key from branch name or PR title using regex
4. Calculate metrics:

```python
@dataclass
class PrMetrics:
    pr_number: int
    repo: str
    author: str
    jira_key: Optional[str]       # Linked Jira issue
    created_at: datetime
    first_review_at: Optional[datetime]
    merged_at: Optional[datetime]
    pickup_hours: Optional[float]  # created → first review
    review_hours: Optional[float]  # first review → merged
    review_rounds: int             # Number of review iterations
    additions: int
    deletions: int
```

**Important:**
- Use `pulls.list()` with `state=closed` and filter by `merged_at` date
- For review timeline, use `/pulls/{number}/reviews` endpoint
- Handle repos with no PRs in the period gracefully
- Batch requests per repo, not per PR where possible

### 3.3 aggregate.py

Takes raw IssueMetrics and PrMetrics, groups by team × project, computes:
- Percentiles (p50, p85) for each phase's duration
- Throughput counts
- PR metric averages
- Weekly trend data (group by ISO week)

Output: the dashboard.json structure defined above.

### 3.4 main.py

```python
def main():
    config = load_config("config.yaml")

    # Phase 1
    jira_data = collect_jira(config)
    
    # Phase 2
    github_data = collect_github(config)
    
    # Phase 3 (skip if jenkins not configured)
    jenkins_data = collect_jenkins(config) if config.get("jenkins") else None
    
    # Aggregate
    dashboard = aggregate(config, jira_data, github_data, jenkins_data)
    
    # Write output
    write_json("data/latest/dashboard.json", dashboard)
    
    # Archive monthly
    archive_path = f"data/archive/{datetime.now().strftime('%Y-%m')}/dashboard.json"
    write_json(archive_path, dashboard)
```

## 4. Frontend Specification

### 4.1 Overview Dashboard (main page)

**Heatmap table** — Rows: teams (18). Columns: phases (planning, dev, review, dev_test, qa, staging). Cell color: green (fast, below org p50) → yellow → red (slow, above org p85). Cell text: p50 value in days.

This is the most important view. At a glance, you can see which team is stuck in which phase.

**Org-level summary cards** at the top:
- Total completed issues (with trend arrow vs prev period)
- Avg cycle time (with trend arrow)
- Avg PR pickup time (with trend arrow)
- Total PRs merged

### 4.2 Team Drill-down

Select a team (and optionally a project) from dropdown.

**Cycle time stacked bar chart** — X axis: weeks. Y axis: days. Stacked bars showing time in each phase. This shows how the cycle time composition changes over time.

**PR Metrics cards:**
- Avg pickup time
- Avg review time
- Avg PR size (with warning if >400 lines)
- Review rounds

**Throughput line chart** — Weekly completed issues trend.

**Bottleneck indicator** — Highlight the phase with the highest p85. Show a text like: "Biggest bottleneck: QA (p85 = 3.0 days, 33% of total cycle time)"

### 4.3 Comparison View

Select 2-4 teams from multi-select dropdown.

**Side-by-side cycle time bars** — Compare phases across teams.

**Radar chart** — Axes: planning speed, dev speed, review speed, QA speed, throughput, PR health. Each team is a polygon. Good for finding each team's relative strengths/weaknesses.

### 4.4 UI/UX Notes

- Dark mode preferred (engineering dashboard aesthetic)
- Responsive but desktop-first (this will mainly be used on large screens)
- Use consistent color palette for phases across all charts
- Loading state: show skeleton while fetching JSON
- Error state: show clear message if dashboard.json fails to load
- No authentication needed (rely on GitHub Pages / repo access control)
- Language: English for UI labels (the audience is mixed, some teams may not read Chinese)

## 5. GitHub Actions Workflows

### 5.1 collect-metrics.yml

```yaml
name: Collect Engineering Metrics
on:
  schedule:
    - cron: '0 18 * * *'  # 每天 UTC 18:00 = 台灣凌晨 2:00
  workflow_dispatch:

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install -r scripts/requirements.txt
      - name: Run metrics collection
        run: python scripts/main.py
        env:
          JIRA_BASE_URL: ${{ secrets.JIRA_BASE_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
          GITHUB_TOKEN: ${{ secrets.METRICS_GITHUB_TOKEN }}
          JENKINS_BASE_URL: ${{ secrets.JENKINS_BASE_URL }}
          JENKINS_USER: ${{ secrets.JENKINS_USER }}
          JENKINS_API_TOKEN: ${{ secrets.JENKINS_API_TOKEN }}
      - name: Commit updated data
        uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: 'chore: update metrics data [skip ci]'
          file_pattern: 'data/**'
```

### 5.2 deploy-frontend.yml

```yaml
name: Deploy Frontend
on:
  push:
    branches: [main]
    paths: ['frontend/**', 'data/latest/**']

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - run: cd frontend && npm ci && npm run build
      - name: Copy data to dist
        run: cp -r data/latest frontend/dist/data
      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./frontend/dist
```

## 6. Development Order

**Start with Phase 1 only. Do not build everything at once.**

### Phase 1: Jira Cycle Time (Week 1-2)
1. Create config.yaml with status mapping + 2-3 sample teams
2. Write collect_jira.py with tests
3. Write aggregate.py (Jira-only aggregation)
4. Write main.py orchestrator
5. Create dashboard.json output
6. Build frontend Overview (heatmap) + Team Drill-down (cycle time only)
7. Set up GitHub Actions for data collection
8. Set up GitHub Pages deployment

### Phase 2: GitHub PR Metrics (Week 3)
1. Write collect_github.py
2. Extend aggregate.py to include PR metrics
3. Add PR metrics cards to Team Drill-down view
4. Add pickup_hours to trends data

### Phase 3: Jenkins (Week 4, if needed)
1. Write collect_jenkins.py
2. Add build metrics to dashboard.json
3. Add build health indicator to frontend

### Phase 4: Polish (Week 5)
1. Add Comparison view
2. Add radar chart
3. Add anomaly highlighting (tickets stuck > N days)
4. Responsive refinements
