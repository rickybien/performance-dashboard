# Engineering Metrics Dashboard — 規格文件（PRD）

> **版本**：v2.0　**更新日期**：2026-03-04
> 一句話描述：靜態 JSON 儀表板，Python pipeline 每日從 Jira/GitHub/Jenkins 收集數據，聚合後寫入 `data/`，Vue.js 前端讀取並呈現，部署於 GitHub Pages，零後端、零即時 API call。

---

## 目錄

1. [架構總覽](#1-架構總覽)
2. [技術堆疊](#2-技術堆疊)
3. [專案結構](#3-專案結構)
4. [config.yaml 規格](#4-configyaml-規格)
5. [資料管線規格](#5-資料管線規格)
6. [dashboard.json 輸出 Schema](#6-dashboardjson-輸出-schema)
7. [前端規格](#7-前端規格)
8. [CI/CD 流程](#8-cicd-流程)
9. [測試策略](#9-測試策略)
10. [環境變數與 Secrets](#10-環境變數與-secrets)
11. [已知限制](#11-已知限制)
12. [未來方向](#12-未來方向)

---

## 1. 架構總覽

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions (cron daily)               │
│                                                             │
│  Jira Cloud ──┐                                             │
│  GitHub   ────┼──→ Python Pipeline ──→ data/latest/         │
│  Jenkins  ────┘    (scripts/)           dashboard.json      │
│                         ↓                    ↓              │
│                    data/cache/         data/archive/         │
│                    (增量 cache)         YYYY-MM/             │
└──────────────────────────┬──────────────────────────────────┘
                           │ git commit + push
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                  GitHub Pages (靜態部署)                      │
│                                                             │
│  Vue.js Frontend ──→ fetch dashboard.json ──→ 呈現圖表       │
│  (frontend/)          (一次讀取，模組級 cache)                 │
└─────────────────────────────────────────────────────────────┘
```

### 核心設計決策

| # | 決策 | 原因 |
|---|------|------|
| 1 | **靜態 JSON，非資料庫** | 前端可部署在任何靜態主機，無需後端服務 |
| 2 | **config.yaml 為唯一真相來源** | 所有 team↔project↔repo 對應與 status mapping 集中管理，易於修改 |
| 3 | **百分位數（p50/p75/p90），非平均值** | 平均值被離群值扭曲，p50 代表典型體驗 |
| 4 | **前端零 API call** | 資料已預聚合，前端只做讀取與渲染 |

---

## 2. 技術堆疊

### Python Pipeline

| 套件 | 版本 | 用途 |
|------|------|------|
| `jira` | 3.8.0 | Jira Cloud REST API v3 |
| `PyGithub` | 2.5.0 | GitHub REST API（PR 收集） |
| `requests` | 2.32.3 | Jenkins HTTP 呼叫 |
| `pyyaml` | 6.0.1 | 解析 config.yaml |
| `python-dateutil` | 2.9.0 | 日期解析（timezone-aware） |
| Python | 3.12+ | 執行環境，使用 `uv` 管理 |

### 前端

| 套件 | 版本 | 用途 |
|------|------|------|
| `vue` | ^3.5.13 | UI framework（Composition API） |
| `vue-router` | ^4.5.0 | SPA 路由（hash history） |
| `chart.js` | ^4.4.7 | 圖表引擎 |
| `vue-chartjs` | ^5.3.2 | Chart.js 的 Vue 封裝 |
| `vite` | ^6.1.0 | 建置工具，base: `/performance-dashboard/` |

### 測試

| 套件 | 用途 |
|------|------|
| `pytest` | Python 測試 |
| `vitest` ^4.0.18 | 前端測試 |
| `@vue/test-utils` ^2.4.6 | Vue 元件測試 |
| `happy-dom` ^20.8.3 | jsdom 替代，vitest 環境 |

---

## 3. 專案結構

```
performance-dashboard/
├── config.yaml                      # 唯一真相來源：teams / status mapping / thresholds
├── PROJECT_SPEC.md                  # 本規格文件
├── CLAUDE.md                        # AI 輔助開發指引
│
├── scripts/                         # Python 資料管線
│   ├── requirements.txt             # 依賴清單
│   ├── main.py                      # 協調器：增量/全量 + 聚合 + 輸出
│   ├── collect_jira.py              # Jira issue 收集 + changelog 解析
│   ├── collect_github.py            # GitHub PR 收集
│   ├── collect_jenkins.py           # Jenkins build 收集
│   ├── aggregate.py                 # 聚合計算（~1000 行）
│   └── tests/
│       ├── test_aggregate.py        # 72 個測試（核心聚合邏輯）
│       ├── test_collect_jira.py     # 16 個測試
│       ├── test_collect_github.py   # 12 個測試
│       └── test_collect_jenkins.py  # 9 個測試
│
├── data/
│   ├── latest/
│   │   └── dashboard.json           # 前端讀取的主要 JSON（每日更新）
│   ├── archive/
│   │   └── YYYY-MM/
│   │       └── dashboard.json       # 每月快照（與 latest 同時寫入）
│   └── cache/
│       ├── issues.json              # 增量 cache（key=Jira issue key）
│       └── prs.json                 # 增量 cache（key=repo#pr_number）
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js               # base: /performance-dashboard/，dev server proxy data/
│   ├── index.html
│   └── src/
│       ├── main.js                  # Vue app 入口
│       ├── App.vue                  # 全域 layout + 導覽
│       ├── assets/main.css          # CSS 變數（暗色主題）
│       ├── router/index.js          # 3 條路由（hash history）
│       ├── composables/
│       │   └── useMetrics.js        # fetch dashboard.json（模組級 cache）
│       ├── views/
│       │   ├── OverviewDashboard.vue  # 首頁：summary cards + heatmap
│       │   ├── TeamDrilldown.vue      # 團隊明細：圖表 + 分析 + 時間區間
│       │   └── Comparison.vue         # 跨團隊比較
│       └── components/
│           ├── HeatmapTable.vue       # 熱力圖表格
│           ├── CycleTimeChart.vue     # 橫向堆疊 bar chart
│           ├── ThroughputChart.vue    # 雙軸折線圖
│           ├── PrMetricsCard.vue      # PR 指標卡片
│           ├── BuildMetricsCard.vue   # Build 指標卡片
│           └── TeamSelector.vue       # 團隊/專案下拉選單
│
└── .github/
    └── workflows/
        ├── collect-metrics.yml        # cron 每日收集 + commit
        └── deploy-frontend.yml        # 建置 + 部署 AWS S3
```

---

## 4. config.yaml 規格

`config.yaml` 位於專案根目錄，是所有設定的唯一來源。修改後需重跑 pipeline 才生效。

### 4.1 連線設定

| Section | 必要欄位 | 環境變數 | 說明 |
|---------|----------|----------|------|
| `jira` | `base_url` | `JIRA_EMAIL`, `JIRA_API_TOKEN` | Atlassian Cloud |
| `github` | `org` | `GITHUB_TOKEN`（本地）或 `METRICS_GITHUB_TOKEN`（CI） | GitHub org 名稱 |
| `jenkins` | `base_url`, `enabled` | `JENKINS_USER`, `JENKINS_API_TOKEN` | `enabled: false` 時完全跳過 |

### 4.2 Phases 定義

共 8 個 phase，`backlog` 和 `done` 不計入 cycle time total，也不出現在 `meta.phases`。

| id | label | color | 計入 total | 出現於 meta |
|----|-------|-------|-----------|------------|
| `backlog` | Backlog | `#94a3b8` | ❌ | ❌ |
| `planning` | SA/SD | `#a78bfa` | ✅ | ✅ |
| `dev` | Development | `#60a5fa` | ✅ | ✅ |
| `review` | PR Review | `#34d399` | ✅ | ✅ |
| `dev_test` | RD Testing | `#fbbf24` | ✅ | ✅ |
| `qa` | QA Testing | `#f97316` | ✅ | ✅ |
| `staging` | Staging | `#f472b6` | ✅ | ✅ |
| `done` | Done | `#22c55e` | ❌ | ❌ |

另有 `unmapped`（程式內部用）：無法對應到任何 phase 的 Jira status，不計入 total。

### 4.3 status_mapping

將 Jira status name 對應到 phase id。分為 `default`（全域）和 `overrides`（per-project）。

**⚠️ Override 語義：完全取代對應 phase 的 default 映射（非疊加）。**
例如 `ROB.dev_test` override 為 `["FEATURE TESTING"]`，則 ROB 專案的 dev_test phase 只認 `FEATURE TESTING`，default 中的所有 dev_test status 全部失效。

**Default mapping：**

| Phase | 包含的 Jira status |
|-------|-------------------|
| `backlog` | To Do, TODO, Backlog, Pending, Pending 項目擱置, Evaluate, Open, 待處理, Awaiting |
| `planning` | Analysis, SA/SD, In Analysis, Design, Planning, System Design, PM/AM Confirmation, PM/AM SURVEY, 規劃中, 需求分析, Requirement Review |
| `dev` | In Progress, In Process, In Development, Developing, Coding, 開發中 |
| `review` | In Review, Code Review, PR Review, PR Merged, Peer Review, 審查中 |
| `dev_test` | Dev Testing, Dev Test, RD Testing, RD Test, 開發測試, RD 測試中 |
| `qa` | QA, QA Testing, In QA, Waiting for QA, FEATURE TESTING, PM/QA REVIEW, Quality Assurance, QA 測試中 |
| `staging` | Staging, Waiting for Stage, Waiting for Release, Wait For Release, Regression, UAT, Stage, Pre-Production, Stage 環境 |
| `done` | Done, Released, Closed, Resolved, OBSERVE, 已完成, 已上線 |

**目前 overrides：**

| Project | Phase | 覆寫 status 清單 |
|---------|-------|-----------------|
| `ROB` | `dev_test` | `["FEATURE TESTING"]` |

### 4.4 sa_sd_rules

SA/SD 獨立票的識別規則。符合條件的票從主 cycle time / throughput / bottleneck 排除，其活躍時間（排除 backlog/done/unmapped 後的小時數）合併入 `planning` phase 數據點。

**識別規則（OR 關係）：**
1. `issue_types`：Jira issue type 精確匹配（大小寫無關）
2. `summary_patterns`：regex 匹配票名（case-insensitive）

**全域規則：**

| 類型 | 值 |
|------|----|
| issue_types | `SA/SD` |
| summary_patterns | `^\[SA\]`、`^\[SD\]`、`(?<![A-Za-z])SA/?SD(?![A-Za-z])` |

**Per-team overrides（完全取代全域規則，語義同 §4.3）：**

| Team | 額外 pattern |
|------|-------------|
| `team-b2b` | 以上全部 + `閱讀文件` |

### 4.5 Teams

目前已配置 3 個團隊（預計 18 個）。

| id | name | Jira projects | GitHub repos 數 | Jenkins jobs 數 |
|----|------|---------------|----------------|----------------|
| `team-product` | Team product | `BE2PROD` | 13 | 10 |
| `team-b2b` | Team b2b | `ROB` | 6 | 8 |
| `team-scm` | Team scm | `SCMWEB` | 4 | 4 |

### 4.6 Collection 設定

| key | 型別 | 值 | 說明 |
|-----|------|----|------|
| `lookback_days` | int | 180 | 收集多少天前的資料 |
| `recent_days` | int | 30 | summary 統計用的近期天數 |
| `trend_weeks` | int | 12 | 趨勢圖總週數（trends 陣列長度） |
| `trend_windows` | list[int] | `[4, 8]` | 前端時間視窗，12W 用全量 aggregated |
| `filter_threshold_hours` | float | 1.0 | pass-through filter 門檻（小時） |
| `jira_jql_filter` | string | `issuetype in (Story, Bug, Task, Sub-task)` | 追加到所有 JQL |
| `pr_issue_pattern` | string | `([A-Z][A-Z0-9]+-\d+)` | 從 PR title/body 提取 Jira key 的 regex |
| `incremental_overlap_hours` | int | 25 | 增量模式覆蓋時窗（> 24h 防漏更新） |
| `api_delay_seconds` | float | 0.5 | Jira search 頁間延遲 |
| `jira_changelog_api_delay_seconds` | float | 0.1 | 每個 issue changelog 呼叫間延遲 |
| `github_api_delay_seconds` | float | 0.1 | GitHub API 呼叫間延遲 |
| `max_concurrent_requests` | int | 5 | 目前未使用（預留） |

### 4.7 Dashboard 設定

| key | 單位 | 值 | 說明 |
|-----|------|----|------|
| `cycle_time_thresholds.good` | 天 | 2.0 | < 此值 → Heatmap 綠色 |
| `cycle_time_thresholds.warning` | 天 | 5.0 | < 此值 → 黃色，≥ 此值 → 紅色 |
| `pr_pickup_thresholds.good` | 小時 | 4.0 | 前端目前未使用 |
| `pr_pickup_thresholds.warning` | 小時 | 12.0 | 前端目前未使用 |
| `large_pr_threshold` | 行數 | 400 | `lines_added + lines_deleted` 超過此值為大型 PR |

---

## 5. 資料管線規格

### 5.1 協調器（main.py）

**執行流程：**

```
Step 1：Jira 收集
  ├─ cache 不存在 OR FORCE_JIRA_REFRESH=true → 全量（lookback_days）
  └─ cache 存在 → 增量（updated >= -incremental_overlap_hours h）
       → 合併 cache（新覆蓋舊）→ 清除超過 lookback_days 的 issue

Step 2：用最新 status_mapping 重算所有 cache issue 的 phase_durations
  （config 修改後立即生效，無需重新收集）→ 回報未對應 status 清單

Step 3：GitHub PR 收集（同 Step 1 邏輯，以 merged_at 清除舊資料）

Step 4：Jenkins Build 收集（無 cache，每次全量）

Step 5：aggregate() → write_dashboard_json()
  → data/latest/dashboard.json
  → data/archive/YYYY-MM/dashboard.json
```

**環境變數控制：**

| 變數 | 效果 |
|------|------|
| `FORCE_FULL_REFRESH=true` | 清空所有 cache，全量重抓 |
| `FORCE_JIRA_REFRESH=true` | 僅清空 issues.json |
| `FORCE_PR_REFRESH=true` | 僅清空 prs.json |

**Cache 路徑：**
- `data/cache/issues.json`：dict，key = Jira issue key
- `data/cache/prs.json`：dict，key = `{repo}#{pr_number}`

序列化透過 `_serialize_issue()` / `_deserialize_issue()` 處理，使用 `.get()` 預設值確保向後相容。

### 5.2 Jira 收集器（collect_jira.py）

#### IssueMetrics Dataclass（17 欄位）

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `key` | str | — | `"PROJ-123"` |
| `project` | str | — | `"PROJ"` |
| `issue_type` | str | — | Story / Bug / Task / Sub-task |
| `created` | datetime | — | timezone-aware UTC |
| `resolved` | Optional[datetime] | None | resolutiondate，None = 未解決 |
| `phase_durations` | dict[str, float] | — | `{phase_id: 小時}`，如 `{"dev": 48.0}` |
| `current_status` | str | — | 當前 Jira status name |
| `assignee` | Optional[str] | None | displayName |
| `sprint_name` | Optional[str] | None | 最後一個 sprint name |
| `summary` | str | `""` | 票名 |
| `parent_key` | Optional[str] | None | parent issue key |
| `parent_summary` | Optional[str] | None | parent 票名 |
| `parent_issue_type` | Optional[str] | None | parent 類型，如 `"Epic"` |
| `status_transitions` | list[dict] | `[]` | `[{"timestamp", "from_status", "to_status"}]` |
| `dev_source` | str | `"jira"` | 被 PR 數據取代後改為 `"github"` |
| `dev_original_hours` | Optional[float] | None | 被取代前的 Jira dev 小時數 |

#### API 細節

| 項目 | 規格 |
|------|------|
| Search API | `POST /rest/api/3/search/jql`，每頁 100 筆，`nextPageToken` 分頁 |
| Changelog API | `GET /rest/api/3/issue/{key}/changelog`，每個 issue 獨立呼叫，`isLast` 判斷結束 |
| Fields | summary, status, issuetype, assignee, created, resolutiondate, customfield_10020, parent |
| JQL 全量 | `project = {key} AND {jql_filter} AND created >= -{lookback_days}d` |
| JQL 增量 | `project = {key} AND {jql_filter} AND updated >= -{overlap_hours}h` |

#### changelog 解析規則（compute_phase_durations）

1. 排序所有 status 變更（timestamp, from_status, to_status）
2. **初始狀態**：`issue_created` → `first_change_time`，phase 由 from_status 決定
3. **逐一累加**：每個 to_status 的停留時間 = 到下一個 change 的時差（最後一個到現在）
4. **回退累加**：QA→Dev→QA，第二次 QA 時間**累加**到同一 phase，不重置
5. **未知 status**：計入 `"unmapped"` key

#### build_status_lookup（override 語義）

以 project_key 為單位建立 `status_name → phase_id` 反向查找表：
- 先以 `default` 建立基礎表
- 若 project 有 override：被 override 的 phase，其 default 中所有 status **全部移除**，改為 override 清單
- 未被 override 的 phase 保留 default

### 5.3 GitHub 收集器（collect_github.py）

#### PRMetrics Dataclass（12 欄位）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `repo` | str | repo name（不含 org） |
| `pr_number` | int | |
| `title` | str | |
| `jira_keys` | list[str] | 從 title+body 提取，regex = `pr_issue_pattern` |
| `created_at` | datetime | |
| `first_review_at` | Optional[datetime] | 第一個非作者 review 時間，None = 無 |
| `merged_at` | Optional[datetime] | None = 未 merge |
| `lines_added` | int | |
| `lines_deleted` | int | |
| `is_large` | bool | `lines_added + lines_deleted > large_pr_threshold` |
| `first_commit_authored_at` | Optional[datetime] | PR 中最早 commit 的 authored 時間 |

**指標定義：**
- **pickup time** = `first_review_at - created_at`（用於 PR 指標）
- **coding time** = `created_at - first_commit_authored_at`（用於補強 dev phase）

**靜默跳過條件：** 無 `GITHUB_TOKEN` / 無 `github.org` / PyGithub 未安裝 → 回傳 `[]`

### 5.4 Jenkins 收集器（collect_jenkins.py）

#### BuildResult Dataclass（5 欄位）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `job_name` | str | |
| `build_number` | int | |
| `result` | Optional[str] | SUCCESS / FAILURE / UNSTABLE / ABORTED / None（進行中） |
| `duration_ms` | int | 毫秒 |
| `timestamp` | datetime | 建置起始時間 |

**行為規格：**
- `jenkins.enabled: false` / 無 base_url / 無認證 → 靜默回傳 `[]`
- **Circuit breaker：** 連續 3 次 job 連線失敗 → 跳過所有剩餘 jobs
- `result=None`（進行中）：計入 `weekly_trend`，不計入 `total_builds`

### 5.5 聚合模組（aggregate.py，~1000 行）

#### 百分位計算

| 函式 | 輸入 | 輸出 | 說明 |
|------|------|------|------|
| `compute_percentile_stats(values)` | float 小時列表 | `{p50, p75, p90, count}` 天 | 純 Python 線性插值，空列表回傳 count=0 |
| `_compute_hour_stats(values)` | float 小時列表 | `{p50, p75, p90, count}` 小時 | 同上但保留小時（PR 指標用） |

#### Dev Phase 數據增強（_enhance_dev_durations_with_prs）

優先順序：

```
1. coding_hours = PR.created_at - PR.first_commit_authored_at
2. pr_dev_hours = PR.merged_at - PR.created_at  （fallback，無 first_commit 時）
3. 取 max(jira_dev_hours, github_dev_hours)（只在 PR 更大時才替換）
4. 替換後設 dev_source="github"，保留 dev_original_hours
```

#### Cycle Time Filtered（Pass-Through 過濾）

- **適用：** 所有 active phase（非 backlog/done/unmapped）
- **邏輯：** issue 在某 phase 停留 < `filter_threshold_hours`（預設 1.0h）視為 pass-through，從統計排除
- **輸出：** 原始 stat + 可選 `filtered` 子物件（見 §6.6）；`filtered_values` 為空時不輸出 filtered 欄位

#### SA/SD 合併流程

**順序很重要（先偵測 bottleneck 再合併，避免 planning 被汙染）：**

```
1. 從每個 project 識別 SA/SD 票，分離 normal_issues 和 sa_sd_entries（(hours, resolved) tuples）
2. 用 normal_issues 計算 cycle_time → 偵測 bottleneck_phase（p50 最高的 active phase）
3. 將 sa_sd_entries 活躍小時合併入 planning phase 統計（原地修改 cycle_time["planning"]）
```

SA/SD 票識別：`issue_type` 精確匹配 OR `summary` regex 匹配（其中一個符合即算），規則見 §4.4。

#### Windowed 聚合（by_window）

依 `trend_windows`（預設 `[4, 8]`）計算不同時間視窗。

- 過濾條件：issue.resolved / PR.merged_at / build.timestamp ≥ `now - w*7 days`
- SA/SD entries 以 resolved 時間過濾；resolved=None 保留在所有視窗
- 12W：直接用 `aggregated`，不另計算

#### 其他核心函式

| 函式 | 說明 |
|------|------|
| `_compute_team_aggregated()` | 統一的 team 聚合入口，全量和 windowed 都呼叫此函式 |
| `_find_bottleneck_issues()` | bottleneck phase 停留最久的 top 10 resolved issues（含 Jira URL、Epic 資訊） |
| `_compute_phase_insights()` | 對 p50 < 1d 的 phase 計算 pass-through（< 1 分鐘）佔比 |
| `compute_weekly_trend()` | 最近 N 週各週完成數（最舊在前） |
| `_compute_weekly_cycle_time_p50()` | 最近 N 週各週 total p50，無資料週回傳 None |

---

## 6. dashboard.json 輸出 Schema

由 `aggregate()` 產生，同時寫入 `data/latest/` 和 `data/archive/YYYY-MM/`。

### 6.1 頂層結構（6 個 key）

| key | 型別 | 說明 |
|-----|------|------|
| `generated_at` | ISO datetime string | UTC 產生時間 |
| `period` | `{start, end}` | ISO date；start = `now - lookback_days` |
| `meta` | object | 前端渲染用 phase 清單與 thresholds |
| `summary` | object | 全組織摘要指標 |
| `teams` | `{team_id: object}` | 各 team 完整資料 |
| `trends` | `{team_id: object}` | 各 team 趨勢時序 |

### 6.2 meta

```jsonc
{
  "phases": [           // 只含 6 個 active phase（排除 backlog, done）
    {"id": "planning", "label": "SA/SD",       "color": "#a78bfa"},
    {"id": "dev",      "label": "Development",  "color": "#60a5fa"},
    {"id": "review",   "label": "PR Review",    "color": "#34d399"},
    {"id": "dev_test", "label": "RD Testing",   "color": "#fbbf24"},
    {"id": "qa",       "label": "QA Testing",   "color": "#f97316"},
    {"id": "staging",  "label": "Staging",      "color": "#f472b6"}
  ],
  "thresholds": {"good": 2.0, "warning": 5.0}  // 單位：天
}
```

### 6.3 summary（5 欄位）

| key | 型別 | 說明 |
|-----|------|------|
| `total_completed_issues` | int | lookback 期間 resolved 總數 |
| `avg_cycle_time_days` | float\|null | 所有 team 的平均 cycle time（天） |
| `avg_cycle_time_prev_period` | null | 未實作，保留欄位 |
| `total_prs_merged` | int\|null | lookback 期間 merged PR 總數 |
| `avg_pr_pickup_hours` | float\|null | 全域 PR pickup p50（小時） |

### 6.4 teams[team_id] 結構

| key | 說明 |
|-----|------|
| `name` | 顯示名稱 |
| `projects` | per-project 資料（見下） |
| `aggregated` | team 層級聚合（見 §6.5） |
| `by_window` | 時間視窗聚合（見 §6.7） |

**projects[project_key]：**

| key | 說明 |
|-----|------|
| `cycle_time` | 各 phase stat（見 §6.6）+ `total` |
| `throughput` | `{completed_issues, story_points, weekly_trend: int[]}` |
| `pr_metrics` | null（project 層級不計算） |

### 6.5 aggregated（8 個 key）

| key | 型別 | 說明 |
|-----|------|------|
| `cycle_time` | object | 各 phase stat（見 §6.6）|
| `throughput` | object | `{completed_issues, story_points, weekly_trend}` |
| `pr_metrics` | object\|null | `{total_prs_merged, pickup_hours, merge_time_hours, large_pr_pct}` |
| `build_metrics` | object\|null | Jenkins 停用時為 null |
| `bottleneck_phase` | string\|null | p50 最高的 active phase id（SA/SD 合併前偵測） |
| `bottleneck_issues` | array | top 10 停留最久的 issue（key, summary, parent_key, parent_summary, phase_duration_days, url） |
| `phase_insights` | array | `{phase_id, pass_through_count, total_in_phase, pass_through_pct}` |
| `dev_source_stats` | object | `{jira_count, github_count, total}` |

**pr_metrics 結構：**

| key | 型別 | 說明 |
|-----|------|------|
| `total_prs_merged` | int | |
| `pickup_hours` | `{p50, p75, p90, count}` | 小時 |
| `merge_time_hours` | `{p50, p75, p90, count}` | 小時，PR created → merged |
| `large_pr_pct` | float | 大型 PR 百分比 |

**build_metrics 結構（Jenkins 啟用時）：**

| key | 型別 | 說明 |
|-----|------|------|
| `success_rate` | float | SUCCESS 數 / completed 數 * 100 |
| `avg_duration_mins` | float | 平均建置時間（分鐘） |
| `total_builds` | int | 排除 result=None 的 in-progress |
| `weekly_trend` | int[] | 最近 N 週建置數（含 in-progress） |

### 6.6 cycle_time phase stat 結構

```jsonc
{
  "planning": {"p50": 5.0, "p75": 32.7, "p90": 52.5, "count": 7},
  "dev": {
    "p50": 0.04, "p75": 2.86, "p90": 47.89, "count": 141,
    "filtered": {          // 只在有 pass-through 被排除時才出現
      "p50": 2.86,
      "p75": 9.43,
      "p90": 80.89,
      "count": 71,               // 過濾後樣本數
      "excluded_count": 70,      // 被排除的 pass-through 數量
      "threshold_hours": 1.0     // 過濾門檻（小時）
    }
  },
  // review, dev_test, qa, staging 同上（均可能有 filtered）
  "total": {"p50": 8.5, "p75": 20.1, "p90": 45.0, "count": 120}
  // backlog, done 也存在但不影響 total
}
```

**前端顯示原則：** `filtered.count > 0` 時優先顯示 `filtered.p50`，否則顯示 `p50`。

### 6.7 by_window 結構

```jsonc
{
  "4": {                       // key = 週數字串（對應 trend_windows）
    // 與 aggregated 相同的 8 個 key
    "cycle_time": {...},
    "throughput": {...},
    "pr_metrics": {...},
    "build_metrics": null,
    "bottleneck_phase": "review",
    "bottleneck_issues": [...],
    "phase_insights": [...],
    "dev_source_stats": {...},
    // 額外多一個 projects（只有 cycle_time，無 throughput）
    "projects": {
      "BE2PROD": {"cycle_time": {...}}
    }
  },
  "8": {...}
  // 12W 不存在：前端選 12W 直接讀 aggregated
}
```

### 6.8 trends[team_id]

| key | 型別 | 說明 |
|-----|------|------|
| `weeks` | string[] | ISO week 標籤，如 `["2026-W01", ...]`，長度 = `trend_weeks` |
| `cycle_time_p50` | (float\|null)[] | 各週 total p50（天），無資料週為 null |
| `throughput` | int[] | 各週完成 issue 數 |
| `pr_pickup_hours` | float\|null | **scalar**（非陣列），team 整體 PR pickup p50（小時） |

---

## 7. 前端規格

### 7.1 技術架構

| 項目 | 規格 |
|------|------|
| Framework | Vue 3，Composition API，`<script setup>` |
| Build | Vite 6.1，`base: "/performance-dashboard/"` |
| Routing | vue-router 4 + **hash history**（GitHub Pages 相容） |
| Charts | Chart.js 4 via vue-chartjs 5 |
| CSS | 自訂暗色主題（CSS variables，Tailwind Slate 色階） |
| 資料取得 | `useMetrics()` composable，模組級 cache，SPA 生命週期只 fetch 一次 |
| Dev server | Vite middleware 攔截 `/performance-dashboard/data/`，從根目錄 `data/` 讀取 |

### 7.2 路由表

| 路徑 | 名稱 | 元件 | Props 來源 |
|------|------|------|-----------|
| `/` | `overview` | `OverviewDashboard` | — |
| `/team/:teamId` | `team` | `TeamDrilldown` | route params 自動注入 |
| `/comparison` | `comparison` | `Comparison` | — |

### 7.3 OverviewDashboard.vue

**Summary Cards（6 張）：**

| 卡片標題 | 資料來源 | 格式 |
|---------|---------|------|
| Completed Issues (90d) | `summary.total_completed_issues` | 數字 |
| Avg Cycle Time | `summary.avg_cycle_time_days` | `Xd` 或 `--` |
| Teams Tracked | `Object.keys(teams).length` | 數字 |
| Data as of | `period.end` | zh-TW 日期 |
| PRs Merged (90d) | `summary.total_prs_merged` | 數字或 `--` |
| PR Pickup p50 | `summary.avg_pr_pickup_hours` | `Xh` 或 `--` |

**HeatmapTable：**
- Rows = teams，Cols = meta.phases（active 6 個）+ Total
- effectiveP50 = `filtered.count > 0 ? filtered.p50 : p50`
- 色階（依 `meta.thresholds`）：`cell-good` < good < `cell-warning` < warning ≤ `cell-bad`
- count = 0 → `cell-empty`
- 點擊 row → `router.push('/team/${teamId}')`
- Legend 文字動態讀取 `thresholds`（非硬碼）

### 7.4 TeamDrilldown.vue

**時間區間切換邏輯：**

```
trendRange < maxWeeks  →  currentAggregated = team.by_window[trendRange]
trendRange = maxWeeks  →  currentAggregated = team.aggregated
displayProjects：4W/8W 時從 by_window[w].projects 覆蓋 cycle_time
Throughput/trend 圖：永遠用 teamTrend 的 array slice（不走 by_window）
```

**功能區塊：**

| 區塊 | 條件 | 說明 |
|------|------|------|
| 時間區間按鈕 `[4W][8W][12W]` | 按鈕靠右 | 只顯示 ≤ `trend_weeks` 的選項 |
| TeamSelector | 永遠顯示 | team + project 下拉 |
| CycleTimeChart | 永遠顯示 | 橫向堆疊 bar，filtered p50 優先 |
| ThroughputChart | 永遠顯示 | 雙軸折線（左 issues，右 cycle time p50 虛線） |
| Bottleneck Card | `bottleneck_phase != null` | p50 最高的 phase badge + p50/p75/p90/count |
| Bottleneck Issues Table | `bottleneck_issues.length > 0` | key+link / summary / Epic link / 停留天數 |
| Dev Source Stats | `dev_source_stats.total > 0` | Jira vs GitHub 來源筆數 |
| Pass-Through 過濾統計表 | 有任何 phase 含 `filtered` | 原始 p50 / 過濾後 p50 / 排除數% / n |
| Phase Insights | 有 phase_insights | pass-through ≥ 50% 時提示自動化穿越 |
| PrMetricsCard | `pr_metrics != null` | 4 個 PR 指標 |
| BuildMetricsCard | `build_metrics != null` | Build 指標（目前全為 null） |

### 7.5 Comparison.vue

- 多選 checkbox（資料載入後預設勾選前 2 個 team）
- **Grouped bar chart**：x 軸 = phases，各 team 一個 dataset，顏色從 10 色 palette 依索引取
- Summary table（8 欄）：Team / Total p50/p75/p90 / Throughput / PRs Merged / PR Pickup p50/p75

### 7.6 元件清單

| 元件 | Props | 核心行為 |
|------|-------|---------|
| `HeatmapTable` | `teams, phases, thresholds` | 色階表格；effectiveP50 優先 filtered；click → drilldown |
| `CycleTimeChart` | `projects, phases` | 橫向堆疊 bar；filtered p50 優先；tooltip 含排除資訊 |
| `ThroughputChart` | `weeks, throughput, cycleTimeP50?` | 雙軸折線；右軸 cycle time 虛線 |
| `PrMetricsCard` | `prMetrics`（nullable） | 4 指標；`large_pr_pct ≥ 30%` 紅色 |
| `BuildMetricsCard` | `buildMetrics`（nullable） | success rate 三色；純 CSS mini bar chart |
| `TeamSelector` | `teams, teamId, projectKey` | 雙 dropdown；v-model 兩欄位；多 project 時才顯示 project 選單 |

### 7.7 CSS 設計系統

| 分類 | 變數 | 值 |
|------|------|-----|
| 背景 | `--bg-primary` | `#0f172a` |
| 背景 | `--bg-card` | `#1e293b` |
| 背景 | `--bg-card-hover` | `#263348` |
| 文字 | `--text-primary` | `#f1f5f9` |
| 文字 | `--text-muted` | `#94a3b8` |
| 邊框 | `--border` | `#334155` |
| 強調 | `--accent` | `#3b82f6` |
| Heatmap 綠 | `--heatmap-good` / `-text` | `#14532d` / `#86efac` |
| Heatmap 黃 | `--heatmap-warning` / `-text` | `#713f12` / `#fde68a` |
| Heatmap 紅 | `--heatmap-bad` / `-text` | `#7f1d1d` / `#fca5a5` |
| Heatmap 空 | `--heatmap-empty` / `-text` | `#1e293b` / `#475569` |

Phase 顏色對應同 §4.2（`--phase-planning: #a78bfa` 等）。

**BuildMetricsCard 成功率三色：**

| 條件 | 顏色 |
|------|------|
| `success_rate ≥ 90%` | `#34d399`（綠） |
| `success_rate ≥ 70%` | `#fbbf24`（黃） |
| `success_rate < 70%` | `#f87171`（紅） |

---

## 8. CI/CD 流程

### 8.1 collect-metrics.yml

| 項目 | 設定 |
|------|------|
| 觸發 | `cron: "0 18 * * *"`（UTC 18:00 = 台灣時間 02:00）+ `workflow_dispatch` |
| Inputs | `force_full_refresh`, `force_jira_refresh`, `force_pr_refresh`（boolean，預設 false） |
| Runner | `ubuntu-latest`，Python 3.12，`uv` |
| Secrets | `JIRA_EMAIL`, `JIRA_API_TOKEN`, `METRICS_GITHUB_TOKEN`, `JENKINS_USER`, `JENKINS_API_TOKEN` |
| Permissions | `contents: write`，`actions: write` |
| Concurrency | group: `collect-metrics`，`cancel-in-progress: false` |

**Commit 流程：**
```bash
git add data/
# 若有變更：
git commit -m "chore: 自動更新 metrics 資料"
git pull --rebase origin master && git push origin master
# DATA_CHANGED=true → gh workflow run deploy-frontend.yml
```

### 8.2 deploy-frontend.yml

| 項目 | 設定 |
|------|------|
| 觸發 | push to `master`（paths: `frontend/**`, `data/latest/**`）+ `workflow_dispatch` |
| Runner | `ubuntu-latest`，Node 20，npm cache |
| Permissions | `contents: read` |
| Concurrency | group: `deploy-frontend`，`cancel-in-progress: true` |
| Secrets | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_S3_BUCKET` |
| Steps | `npm ci` → `npm run build` → `cp data/latest → dist/data/（若目錄存在）` → `aws s3 sync --delete` |
| 部署 | `aws s3 sync frontend/dist/ s3://{AWS_S3_BUCKET}/ --delete` |

---

## 9. 測試策略

### Python（共 109 個測試）

```bash
cd scripts && uv run --with jira --with pyyaml --with python-dateutil --with pytest --with PyGithub pytest tests/ -v
```

| 檔案 | 數量 | 主要涵蓋 |
|------|------|---------|
| `test_aggregate.py` | 72 | percentile、cycle time filtered、SA/SD 識別與合併、windowed(by_window)、bottleneck issues、phase insights、dev source stats、PR dev 補強、整合流程 |
| `test_collect_jira.py` | 16 | `build_status_lookup`（override 語義）、`compute_phase_durations`（回退累加）、`parse_changelog`、remap 向後相容 |
| `test_collect_github.py` | 12 | Jira key 提取、`_get_first_review_time`、PRMetrics、無 token 靜默 |
| `test_collect_jenkins.py` | 9 | circuit breaker、enabled 開關、result=None 處理 |

### 前端（共 15 個測試）

```bash
cd frontend && npm test
```

| 檔案 | 數量 | 主要涵蓋 |
|------|------|---------|
| `HeatmapTable.test.js` | 10 | formatDays（filtered 優先）、cellClass（thresholds）、cellTitle（pass-through 資訊）、null handling |
| `CycleTimeChart.test.js` | 5 | 所有 active phase 的 filtered p50 優先邏輯、fallback |

---

## 10. 環境變數與 Secrets

| 變數名 | 必要性 | 說明 |
|--------|--------|------|
| `JIRA_EMAIL` | Jira 必要 | Atlassian 帳號 email |
| `JIRA_API_TOKEN` | Jira 必要 | Atlassian API token |
| `METRICS_GITHUB_TOKEN` | GitHub（CI） | PAT with repo read；無此值時 PR 收集靜默跳過 |
| `GITHUB_TOKEN` | GitHub（本地） | 本地執行用 |
| `JENKINS_USER` | Jenkins 選用 | Jenkins 帳號 |
| `JENKINS_API_TOKEN` | Jenkins 選用 | Jenkins API token |
| `FORCE_FULL_REFRESH` | 控制用 | `"true"` = 清空所有 cache 全量重抓 |
| `FORCE_JIRA_REFRESH` | 控制用 | `"true"` = 僅 Jira 全量 |
| `FORCE_PR_REFRESH` | 控制用 | `"true"` = 僅 PR 全量 |

---

## 11. 已知限制

| 限制 | 說明 |
|------|------|
| Jenkins 停用 | `enabled: false`；因內網限制無法從 GitHub Actions 存取 |
| `avg_cycle_time_prev_period` 未實作 | `summary` 中固定為 null，無同期比較 |
| `story_points` 未實作 | `throughput.story_points` 固定為 null |
| B2B/ROB 批次拖票 | 大量 issue 在完成後回溯性拖票，約 59.7% 有 ≥3 個 status 在 60 秒內完成；仰賴 pass-through filter 矯正 |
| `trends.pr_pickup_hours` 是 scalar | 團隊整體 PR pickup p50，非 weekly 時序陣列 |
| Comparison 未使用 by_window | 固定讀 aggregated，無時間區間切換 |
| 只配置 3/18 個團隊 | 剩餘 15 個待加入 config.yaml |

---

## 12. 未來方向

| 項目 | 說明 |
|------|------|
| 配齊 18 個團隊 | 在 `config.yaml` 的 `teams` section 補充剩餘 15 個 |
| 啟用 Jenkins 收集 | 需 VPN proxy 或 self-hosted runner 解決內網存取 |
| 同期比較 | 計算上個同等時間段的 cycle time，前端顯示趨勢箭頭 |
| Comparison 時間區間 | 讀取 by_window，與 TeamDrilldown 一致 |
| PR pickup hours 週趨勢 | trends 中改為 weekly 陣列（目前是 scalar） |
| Anomaly highlighting | issue 在某 phase 停滯超過 N 天時標紅或警報 |
| Story points 收集 | 從 Jira customfield 收集，補充 throughput 指標 |
| Archive 跨月比較 | 利用 `data/archive/` 月份快照做長期趨勢分析 |
