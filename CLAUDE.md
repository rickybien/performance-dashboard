# CLAUDE.md — Engineering Metrics Dashboard

## Project Overview

A lightweight, self-hosted engineering metrics dashboard for tracking team productivity across 18+ cross-functional teams. Data is collected from Jira Cloud, GitHub, and Jenkins via a Python pipeline running on GitHub Actions, stored as static JSON files, and rendered by a Vue.js frontend deployed on GitHub Pages.

The goal: give an engineering director visibility into **cycle time breakdown by team × project × phase**, so they can identify bottlenecks and drive productivity improvements.

## Architecture

```
GitHub Actions (cron daily)
  → Python scripts pull from Jira / GitHub / Jenkins APIs
  → Compute aggregated metrics
  → Commit JSON files to data/ directory

GitHub Pages (static site)
  → Vue.js frontend reads JSON from data/
  → Renders dashboards with charts
  → Zero backend, zero API calls from browser
```

## Tech Stack

- **Data Pipeline**: Python 3.12+, using `jira`, `PyGithub`, `requests`
- **Frontend**: Vue 3 (Composition API) + Vite + Chart.js (via vue-chartjs)
- **Deployment**: GitHub Pages (from /docs or gh-pages branch)
- **CI/CD**: GitHub Actions for both data collection and frontend build
- **Fallback**: If Vue + Vite deployment on GitHub Pages is too complex, fall back to vanilla HTML/JS with Chart.js via CDN

## Project Structure

```
engineering-metrics-dashboard/
├── CLAUDE.md                    # This file
├── PROJECT_SPEC.md              # Detailed spec (see below)
├── scripts/                     # Python data pipeline
│   ├── requirements.txt
│   ├── config.yaml              # Team/project/repo mapping + status mapping
│   ├── collect_jira.py          # Jira data collection
│   ├── collect_github.py        # GitHub PR data collection
│   ├── collect_jenkins.py       # Jenkins build data collection
│   ├── aggregate.py             # Compute metrics from raw data
│   ├── main.py                  # Orchestrator: run all collectors + aggregate
│   └── tests/
│       └── test_aggregate.py
├── data/                        # Generated JSON (committed by CI)
│   ├── latest/
│   │   └── dashboard.json       # Main file the frontend reads
│   └── archive/
│       └── 2026-02/
│           └── dashboard.json
├── frontend/                    # Vue.js app
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── App.vue
│       ├── main.js
│       ├── views/
│       │   ├── OverviewDashboard.vue
│       │   ├── TeamDrilldown.vue
│       │   └── Comparison.vue
│       ├── components/
│       │   ├── CycleTimeBreakdown.vue
│       │   ├── PrMetricsCard.vue
│       │   ├── ThroughputTrend.vue
│       │   ├── TeamSelector.vue
│       │   └── HeatmapChart.vue
│       └── composables/
│           └── useMetrics.js    # Fetch + parse dashboard.json
├── .github/
│   └── workflows/
│       ├── collect-metrics.yml  # Daily cron to run Python pipeline
│       └── deploy-frontend.yml  # Build + deploy Vue app to GitHub Pages
└── docs/                        # Alternative: if deploying built frontend here
```

## Key Design Decisions

1. **Static JSON, not a database.** All computation happens in the Python pipeline. Frontend only reads pre-computed JSON. This keeps the frontend dead simple and deployable anywhere.

2. **config.yaml is the single source of truth** for team ↔ project ↔ repo mapping and Jira status ↔ phase mapping. This must be easy to edit because teams change.

3. **Percentiles over averages.** Always compute p50 and p85. Averages hide outliers and give misleading cycle time numbers.

4. **Incremental development order:**
   - Phase 1: Jira cycle time breakdown only
   - Phase 2: Add GitHub PR metrics
   - Phase 3: Add Jenkins build metrics
   - Phase 4: Polish UI, add comparison view

## Important Constraints

- 18 teams, ~36 Jira projects, potentially 100+ GitHub repos
- Jira API rate limit: respect it, add delays between requests
- GitHub API: 5000 req/hr with PAT, use conditional requests (If-Modified-Since)
- Jenkins API: basic auth, vary by instance
- GitHub Actions free tier: 2000 minutes/month, keep pipeline efficient
- Dashboard JSON should stay under 1MB total for fast page loads
- All secrets go in GitHub Secrets, never in code
- The user's Jira Cloud has many different workflows across teams — status mapping must be flexible per-board/per-project

## Coding Style

- Python: type hints, docstrings, f-strings, pathlib for file paths
- Vue: Composition API with `<script setup>`, no Options API
- Commit messages: conventional commits (feat:, fix:, chore:)
- Keep files small and focused — one collector per data source
- Always handle API errors gracefully with logging, never crash the pipeline on partial failures
