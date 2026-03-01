"""test_aggregate.py — aggregate 模組單元測試

所有測試使用合成 IssueMetrics，不依賴任何外部服務。
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from aggregate import (
    _build_jira_pr_index,
    _build_sa_sd_matcher,
    _compute_pr_dev_hours,
    _compute_sa_sd_planning_hours,
    _enhance_dev_durations_with_prs,
    _find_bottleneck_issues,
    _is_sa_sd_issue,
    _merge_sa_sd_into_planning,
    aggregate,
    compute_percentile_stats,
    compute_throughput,
    compute_weekly_trend,
    group_by_team_project,
)
from collect_github import PRMetrics
from collect_jira import IssueMetrics


# ============================================================
# 測試輔助
# ============================================================

BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)
NOW = datetime(2026, 2, 27, tzinfo=timezone.utc)


def make_issue(
    key: str = "PROJ-A-1",
    project: str = "PROJ-A",
    phase_durations: dict | None = None,
    resolved: datetime | None = None,
    created: datetime | None = None,
    summary: str = "",
    parent_key: str | None = None,
    parent_summary: str | None = None,
    parent_issue_type: str | None = None,
    issue_type: str = "Story",
) -> IssueMetrics:
    """建立合成 IssueMetrics。"""
    return IssueMetrics(
        key=key,
        project=project,
        issue_type=issue_type,
        created=created or BASE_TIME,
        resolved=resolved,
        phase_durations=phase_durations or {"dev": 48.0},
        current_status="Done" if resolved else "In Progress",
        assignee=None,
        sprint_name=None,
        summary=summary,
        parent_key=parent_key,
        parent_summary=parent_summary,
        parent_issue_type=parent_issue_type,
    )


SAMPLE_CONFIG = {
    "jira": {
        "base_url": "https://example.atlassian.net",
    },
    "collection": {
        "lookback_days": 90,
        "recent_days": 30,
    },
    "phases": [
        {"id": "backlog", "label": "Backlog"},
        {"id": "planning", "label": "SA/SD"},
        {"id": "dev", "label": "Development"},
        {"id": "review", "label": "PR Review"},
        {"id": "dev_test", "label": "RD Testing"},
        {"id": "qa", "label": "QA Testing"},
        {"id": "staging", "label": "Staging"},
        {"id": "done", "label": "Done"},
    ],
    "teams": [
        {
            "id": "team-alpha",
            "name": "Team Alpha",
            "jira_projects": ["PROJ-A"],
        },
        {
            "id": "team-beta",
            "name": "Team Beta",
            "jira_projects": ["PROJ-B", "PROJ-C"],
        },
    ],
}


# ============================================================
# compute_percentile_stats 測試
# ============================================================


def test_compute_percentile_stats_basic():
    """p50/p75/p90 應正確計算並轉換為天。"""
    # 10 個值：24, 48, 72, ..., 240 小時（1-10 天）
    values = [24.0 * i for i in range(1, 11)]
    stats = compute_percentile_stats(values)

    # p50 = 5.5 天（5 和 6 的平均）
    assert abs(stats["p50"] - 5.5) < 0.1
    # p75: index=6.75, value=7+0.75*(8-7)=7.75 天
    assert abs(stats["p75"] - 7.75) < 0.1
    # p90: index=8.1, value=9+0.1*(10-9)=9.1 天
    assert abs(stats["p90"] - 9.1) < 0.1
    assert stats["count"] == 10


def test_compute_percentile_stats_empty():
    """空列表應回傳 count=0 且 p50/p75/p90 為 0。"""
    stats = compute_percentile_stats([])
    assert stats["p50"] == 0.0
    assert stats["p75"] == 0.0
    assert stats["p90"] == 0.0
    assert stats["count"] == 0


def test_compute_percentile_stats_single():
    """只有一個值時，p50/p75/p90 都應等於該值。"""
    stats = compute_percentile_stats([48.0])
    assert abs(stats["p50"] - 2.0) < 0.01  # 48h = 2 天
    assert abs(stats["p75"] - 2.0) < 0.01
    assert abs(stats["p90"] - 2.0) < 0.01
    assert stats["count"] == 1


def test_compute_percentile_stats_two_values():
    """兩個值時應正確插值。"""
    stats = compute_percentile_stats([24.0, 48.0])  # 1 天, 2 天
    assert abs(stats["p50"] - 1.5) < 0.01


# ============================================================
# group_by_team_project 測試
# ============================================================


def test_aggregate_groups_by_team_project():
    """issues 應正確依 team → project 分組。"""
    issues = [
        make_issue("PROJ-A-1", "PROJ-A"),
        make_issue("PROJ-A-2", "PROJ-A"),
        make_issue("PROJ-B-1", "PROJ-B"),
        make_issue("PROJ-C-1", "PROJ-C"),
    ]

    grouped = group_by_team_project(SAMPLE_CONFIG, issues)

    assert len(grouped["team-alpha"]["PROJ-A"]) == 2
    assert len(grouped["team-beta"]["PROJ-B"]) == 1
    assert len(grouped["team-beta"]["PROJ-C"]) == 1


def test_group_by_team_project_unknown_project(caplog):
    """未對應到任何 team 的 project 應記錄警告，不崩潰。"""
    import logging
    issues = [make_issue("PROJ-X-1", "PROJ-X")]

    with caplog.at_level(logging.WARNING):
        grouped = group_by_team_project(SAMPLE_CONFIG, issues)

    assert "PROJ-X" in caplog.text


# ============================================================
# compute_throughput 測試
# ============================================================


def test_aggregate_throughput_counts_resolved():
    """只計算 resolved 在 recent_days 內的 issue。"""
    now = datetime.now(timezone.utc)
    recent_resolved = now - timedelta(days=5)
    old_resolved = now - timedelta(days=60)

    issues = [
        make_issue("PROJ-A-1", resolved=recent_resolved),
        make_issue("PROJ-A-2", resolved=recent_resolved),
        make_issue("PROJ-A-3", resolved=old_resolved),  # 超過 30 天
        make_issue("PROJ-A-4"),  # 未解決
    ]

    throughput = compute_throughput(issues, recent_days=30)
    assert throughput["completed_issues"] == 2
    assert throughput["story_points"] is None


def test_compute_throughput_no_resolved():
    """無已解決 issue 時 completed_issues 為 0。"""
    issues = [make_issue("PROJ-A-1"), make_issue("PROJ-A-2")]
    throughput = compute_throughput(issues, recent_days=30)
    assert throughput["completed_issues"] == 0


# ============================================================
# compute_weekly_trend 測試
# ============================================================


def test_aggregate_weekly_trend_correct_weeks():
    """週趨勢應正確分組到對應的週。"""
    now = datetime.now(timezone.utc)

    issues = [
        # 最近一週（0-6 天前）= 3 筆
        make_issue("A-1", resolved=now - timedelta(days=1)),
        make_issue("A-2", resolved=now - timedelta(days=3)),
        make_issue("A-3", resolved=now - timedelta(days=6)),
        # 第二週（7-13 天前）= 2 筆
        make_issue("A-4", resolved=now - timedelta(days=8)),
        make_issue("A-5", resolved=now - timedelta(days=13)),
        # 第三週（14-20 天前）= 1 筆
        make_issue("A-6", resolved=now - timedelta(days=15)),
        # 第四週（21-27 天前）= 1 筆
        make_issue("A-7", resolved=now - timedelta(days=21)),
        # 超過 4 週（不計入）
        make_issue("A-8", resolved=now - timedelta(days=30)),
    ]

    trend = compute_weekly_trend(issues, num_weeks=4)

    assert len(trend) == 4
    # [第4週, 第3週, 第2週, 最近1週]
    assert trend[3] == 3  # 最近一週
    assert trend[2] == 2  # 第二週
    assert trend[1] == 1  # 第三週
    assert trend[0] == 1  # 第四週


# ============================================================
# aggregate 整合測試
# ============================================================


def test_aggregate_total_cycle_time():
    """total cycle time 應為各非 backlog/done phase 之和的 p50。"""
    # 兩個已解決 issue，各有已知的 phase duration
    resolved = datetime.now(timezone.utc) - timedelta(days=1)
    issues = [
        make_issue(
            "PROJ-A-1",
            resolved=resolved,
            phase_durations={"dev": 48.0, "qa": 24.0},  # total = 72h = 3天
        ),
        make_issue(
            "PROJ-A-2",
            resolved=resolved,
            phase_durations={"dev": 24.0, "qa": 24.0},  # total = 48h = 2天
        ),
    ]

    result = aggregate(SAMPLE_CONFIG, issues)

    project_data = result["teams"]["team-alpha"]["projects"]["PROJ-A"]
    total_stats = project_data["cycle_time"]["total"]

    # p50 of [72h, 48h] = 60h = 2.5 天
    assert abs(total_stats["p50"] - 2.5) < 0.1
    assert total_stats["count"] == 2


def test_aggregate_phase_only_nonzero():
    """沒有停留時間的 phase 不應計入 p50/p85（count 為 0）。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)
    issues = [
        make_issue(
            "PROJ-A-1",
            resolved=resolved,
            phase_durations={"dev": 48.0},  # 無 planning phase
        ),
    ]

    result = aggregate(SAMPLE_CONFIG, issues)
    project_data = result["teams"]["team-alpha"]["projects"]["PROJ-A"]

    # planning 沒有任何 issue 有值，count 應為 0
    planning_stats = project_data["cycle_time"]["planning"]
    assert planning_stats["count"] == 0
    assert planning_stats["p50"] == 0.0


def test_aggregate_empty_input():
    """空 jira_data 應回傳合法的空結構，不崩潰。"""
    result = aggregate(SAMPLE_CONFIG, [])

    assert "generated_at" in result
    assert "period" in result
    assert "summary" in result
    assert "teams" in result
    assert "trends" in result

    assert result["summary"]["total_completed_issues"] == 0
    assert result["summary"]["avg_cycle_time_days"] is None

    # 每個 team 都應存在，但 projects 內的 issues 列表為空
    assert "team-alpha" in result["teams"]
    assert "team-beta" in result["teams"]


def test_aggregate_github_data_none():
    """github_data=None 時，pr_metrics 應為 null。"""
    result = aggregate(SAMPLE_CONFIG, [], github_data=None)

    for team_data in result["teams"].values():
        for project_data in team_data["projects"].values():
            assert project_data["pr_metrics"] is None
        assert team_data["aggregated"]["pr_metrics"] is None


def test_aggregate_output_structure():
    """輸出結構應包含所有必要欄位。"""
    result = aggregate(SAMPLE_CONFIG, [])

    # 頂層欄位
    required_top_level = {"generated_at", "period", "summary", "teams", "trends"}
    assert required_top_level.issubset(result.keys())

    # summary 欄位
    summary = result["summary"]
    required_summary = {
        "total_completed_issues",
        "avg_cycle_time_days",
        "avg_cycle_time_prev_period",
        "total_prs_merged",
        "avg_pr_pickup_hours",
    }
    assert required_summary.issubset(summary.keys())

    # period 欄位
    assert "start" in result["period"]
    assert "end" in result["period"]


def test_aggregate_teams_have_aggregated_field():
    """每個 team 應有 aggregated 欄位，包含跨 project 的聚合數據。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)
    issues = [
        make_issue("PROJ-B-1", "PROJ-B", resolved=resolved, phase_durations={"dev": 24.0}),
        make_issue("PROJ-C-1", "PROJ-C", resolved=resolved, phase_durations={"dev": 48.0}),
    ]

    result = aggregate(SAMPLE_CONFIG, issues)

    team_beta = result["teams"]["team-beta"]
    assert "aggregated" in team_beta
    assert "cycle_time" in team_beta["aggregated"]
    assert "throughput" in team_beta["aggregated"]

    # aggregated total count 應為 2（兩個 project 各一筆）
    total = team_beta["aggregated"]["cycle_time"]["total"]
    assert total["count"] == 2


def test_aggregate_trends_structure():
    """trends 應包含正確的結構與 week 標籤。"""
    result = aggregate(SAMPLE_CONFIG, [])

    for team_id in ["team-alpha", "team-beta"]:
        assert team_id in result["trends"]
        trend = result["trends"][team_id]
        assert "weeks" in trend
        assert "cycle_time_p50" in trend
        assert "throughput" in trend
        assert "pr_pickup_hours" in trend
        assert trend["pr_pickup_hours"] is None
        assert len(trend["weeks"]) == 4
        assert len(trend["throughput"]) == 4


# ============================================================
# _find_bottleneck_issues 測試
# ============================================================

JIRA_BASE = "https://example.atlassian.net"


def test_find_bottleneck_issues_sorted_desc():
    """應依 phase duration 降序排列。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)
    issues = [
        make_issue("A-1", resolved=resolved, phase_durations={"dev": 24.0}, summary="Fast"),
        make_issue("A-2", resolved=resolved, phase_durations={"dev": 72.0}, summary="Slow"),
        make_issue("A-3", resolved=resolved, phase_durations={"dev": 48.0}, summary="Medium"),
    ]

    result = _find_bottleneck_issues(issues, "dev", JIRA_BASE)

    assert len(result) == 3
    assert result[0]["key"] == "A-2"
    assert result[1]["key"] == "A-3"
    assert result[2]["key"] == "A-1"
    assert result[0]["phase_duration_days"] == 3.0
    assert result[1]["phase_duration_days"] == 2.0
    assert result[2]["phase_duration_days"] == 1.0


def test_find_bottleneck_issues_limit():
    """limit 參數應限制回傳數量。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)
    issues = [
        make_issue(f"A-{i}", resolved=resolved, phase_durations={"dev": float(i * 24)})
        for i in range(1, 6)
    ]

    result = _find_bottleneck_issues(issues, "dev", JIRA_BASE, limit=2)

    assert len(result) == 2
    assert result[0]["key"] == "A-5"
    assert result[1]["key"] == "A-4"


def test_find_bottleneck_issues_excludes_unresolved():
    """未 resolved 的 issue 不應出現在結果中。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)
    issues = [
        make_issue("A-1", resolved=resolved, phase_durations={"dev": 48.0}),
        make_issue("A-2", resolved=None, phase_durations={"dev": 240.0}),  # unresolved
    ]

    result = _find_bottleneck_issues(issues, "dev", JIRA_BASE)

    assert len(result) == 1
    assert result[0]["key"] == "A-1"


def test_find_bottleneck_issues_empty():
    """無 resolved issues 時應回傳空列表。"""
    issues = [make_issue("A-1", resolved=None, phase_durations={"dev": 48.0})]

    result = _find_bottleneck_issues(issues, "dev", JIRA_BASE)

    assert result == []


def test_find_bottleneck_issues_url_and_parent():
    """parent_issue_type="Epic" 時應正確組裝 URL 並帶入 parent 資訊。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)
    issues = [
        make_issue(
            "PROJ-123", resolved=resolved, phase_durations={"qa": 72.0},
            summary="Fix login bug",
            parent_key="PROJ-100", parent_summary="Auth Epic",
            parent_issue_type="Epic",
        ),
    ]

    result = _find_bottleneck_issues(issues, "qa", JIRA_BASE)

    assert len(result) == 1
    item = result[0]
    assert item["url"] == "https://example.atlassian.net/browse/PROJ-123"
    assert item["summary"] == "Fix login bug"
    assert item["parent_key"] == "PROJ-100"
    assert item["parent_summary"] == "Auth Epic"


def test_find_bottleneck_issues_non_epic_parent_excluded():
    """parent_issue_type 不是 "Epic" 時，parent_key/parent_summary 應為 None。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)
    issues = [
        make_issue(
            "PROJ-456", resolved=resolved, phase_durations={"dev": 48.0},
            summary="Sub-task work",
            parent_key="PROJ-200", parent_summary="Some Story",
            parent_issue_type="Story",
        ),
    ]

    result = _find_bottleneck_issues(issues, "dev", JIRA_BASE)

    assert len(result) == 1
    item = result[0]
    assert item["parent_key"] is None
    assert item["parent_summary"] is None


def test_find_bottleneck_issues_no_parent():
    """沒有 parent 的 issue 應正常回傳 None。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)
    issues = [
        make_issue("A-1", resolved=resolved, phase_durations={"dev": 48.0}, summary="Solo task"),
    ]

    result = _find_bottleneck_issues(issues, "dev", JIRA_BASE)

    assert result[0]["parent_key"] is None
    assert result[0]["parent_summary"] is None


def test_aggregate_bottleneck_phase_identification():
    """aggregate 應正確識別 bottleneck phase（p50 最高者）。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)
    issues = [
        make_issue(
            "PROJ-A-1", resolved=resolved,
            phase_durations={"dev": 24.0, "qa": 72.0},  # qa 是瓶頸
            summary="Issue 1",
        ),
        make_issue(
            "PROJ-A-2", resolved=resolved,
            phase_durations={"dev": 48.0, "qa": 96.0},
            summary="Issue 2",
        ),
    ]

    result = aggregate(SAMPLE_CONFIG, issues)
    team = result["teams"]["team-alpha"]

    assert team["aggregated"]["bottleneck_phase"] == "qa"
    assert len(team["aggregated"]["bottleneck_issues"]) == 2
    # 第一筆應是 qa 最慢的（96h = 4 天）
    assert team["aggregated"]["bottleneck_issues"][0]["phase_duration_days"] == 4.0


def test_aggregate_bottleneck_empty_issues():
    """無 issue 時 bottleneck_phase 應為 None，bottleneck_issues 應為空。"""
    result = aggregate(SAMPLE_CONFIG, [])
    team = result["teams"]["team-alpha"]

    assert team["aggregated"]["bottleneck_phase"] is None
    assert team["aggregated"]["bottleneck_issues"] == []


# ============================================================
# SA/SD 識別與合併測試
# ============================================================

SA_SD_CONFIG = {
    **SAMPLE_CONFIG,
    "sa_sd_rules": {
        "issue_types": ["SA/SD"],
        "summary_patterns": [r"^\[SA\]", r"^\[SD\]"],
        "overrides": {},
    },
}


def test_is_sa_sd_by_issue_type():
    """issue_type='SA/SD' 應匹配，'Story' 不應匹配。"""
    import re

    issue_types = {"SA/SD"}
    patterns = []

    sasd = make_issue(issue_type="SA/SD")
    story = make_issue(issue_type="Story")

    assert _is_sa_sd_issue(sasd, issue_types, patterns) is True
    assert _is_sa_sd_issue(story, issue_types, patterns) is False


def test_is_sa_sd_by_summary_pattern():
    """summary='[SA] 分析' 應匹配，'修復 SA 模組' 不應匹配。"""
    import re

    issue_types: set[str] = set()
    patterns = [re.compile(r"^\[SA\]", re.IGNORECASE), re.compile(r"^\[SD\]", re.IGNORECASE)]

    sasd = make_issue(summary="[SA] 分析需求")
    not_sasd = make_issue(summary="修復 SA 模組的 bug")

    assert _is_sa_sd_issue(sasd, issue_types, patterns) is True
    assert _is_sa_sd_issue(not_sasd, issue_types, patterns) is False


def test_is_sa_sd_chinese_adjacent_pattern():
    """中文字元緊鄰 SA/SD 時，(?<![A-Za-z])SA/?SD(?![A-Za-z]) 應正確匹配。"""
    import re

    issue_types: set[str] = set()
    patterns = [re.compile(r"(?<![A-Za-z])SA/?SD(?![A-Za-z])", re.IGNORECASE)]

    chinese_adjacent = make_issue(summary="跨方案 後端SA/SD")
    with_space = make_issue(summary="[be2-web] 前端 SA/SD")
    english_adjacent = make_issue(summary="NASASD mission")

    assert _is_sa_sd_issue(chinese_adjacent, issue_types, patterns) is True
    assert _is_sa_sd_issue(with_space, issue_types, patterns) is True
    assert _is_sa_sd_issue(english_adjacent, issue_types, patterns) is False


def test_sa_sd_per_team_override():
    """override 完全取代全域規則，不繼承全域 issue_types/summary_patterns。"""
    config_with_override = {
        **SAMPLE_CONFIG,
        "sa_sd_rules": {
            "issue_types": ["SA/SD"],
            "summary_patterns": [r"^\[SA\]"],
            "overrides": {
                "team-alpha": {
                    "issue_types": ["Analysis"],
                    "summary_patterns": [],
                }
            },
        },
    }

    # team-alpha 有 override：只匹配 "Analysis"，不匹配 "SA/SD"
    alpha_types, alpha_pats = _build_sa_sd_matcher(config_with_override, "team-alpha")
    assert "Analysis" in alpha_types
    assert "SA/SD" not in alpha_types
    assert alpha_pats == []

    # team-beta 無 override：使用全域規則，匹配 "SA/SD"
    beta_types, beta_pats = _build_sa_sd_matcher(config_with_override, "team-beta")
    assert "SA/SD" in beta_types


def test_sa_sd_merged_into_planning():
    """SA/SD 票的活躍時間應合併到 planning p50，dev count 不含 SA/SD 票。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)

    # 普通票：dev=24h
    normal = make_issue("PROJ-A-1", resolved=resolved, phase_durations={"dev": 24.0})
    # SA/SD 票：planning=48h（活躍時間 = 48h）
    sasd = make_issue(
        "PROJ-A-2",
        resolved=resolved,
        phase_durations={"planning": 48.0},
        issue_type="SA/SD",
    )

    result = aggregate(SA_SD_CONFIG, [normal, sasd])
    project_data = result["teams"]["team-alpha"]["projects"]["PROJ-A"]

    # planning 應包含 SA/SD 的 48h = 2 天（唯一數據點）
    planning = project_data["cycle_time"]["planning"]
    assert planning["count"] == 1
    assert abs(planning["p50"] - 2.0) < 0.01

    # dev count 只有 1（normal 票），不含 SA/SD
    dev = project_data["cycle_time"]["dev"]
    assert dev["count"] == 1


def test_sa_sd_excluded_from_throughput():
    """SA/SD 票不應計入 completed_issues throughput。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)

    normal = make_issue("PROJ-A-1", resolved=resolved, phase_durations={"dev": 24.0})
    sasd = make_issue("PROJ-A-2", resolved=resolved, phase_durations={"dev": 24.0}, issue_type="SA/SD")

    result = aggregate(SA_SD_CONFIG, [normal, sasd])
    throughput = result["teams"]["team-alpha"]["aggregated"]["throughput"]

    # 只有 1 個普通票計入 throughput
    assert throughput["completed_issues"] == 1


def test_no_sa_sd_rules_backward_compat():
    """無 sa_sd_rules config 時，行為應與舊版完全一致。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)
    issues = [
        make_issue("PROJ-A-1", resolved=resolved, phase_durations={"dev": 24.0}),
        make_issue("PROJ-A-2", resolved=resolved, phase_durations={"dev": 48.0}, issue_type="SA/SD"),
    ]

    # SAMPLE_CONFIG 沒有 sa_sd_rules
    result = aggregate(SAMPLE_CONFIG, issues)
    throughput = result["teams"]["team-alpha"]["aggregated"]["throughput"]

    # 舊行為：SA/SD 票照常計入
    assert throughput["completed_issues"] == 2


def test_sa_sd_zero_active_hours():
    """SA/SD 票只有 backlog（活躍時間=0）→ 不產生 planning 數據點。"""
    resolved = datetime.now(timezone.utc) - timedelta(days=1)

    sasd_backlog_only = make_issue(
        "PROJ-A-1",
        resolved=resolved,
        phase_durations={"backlog": 72.0},  # backlog 被排除
        issue_type="SA/SD",
    )

    result = aggregate(SA_SD_CONFIG, [sasd_backlog_only])
    project_data = result["teams"]["team-alpha"]["projects"]["PROJ-A"]

    # planning count 應為 0（無有效數據點）
    planning = project_data["cycle_time"]["planning"]
    assert planning["count"] == 0


def test_sa_sd_unresolved_included():
    """未 resolved 的 SA/SD 票 → 已走過的 planning 時間應被計入。"""
    sasd_unresolved = make_issue(
        "PROJ-A-1",
        resolved=None,  # 未完成
        phase_durations={"planning": 48.0},
        issue_type="SA/SD",
    )

    result = aggregate(SA_SD_CONFIG, [sasd_unresolved])
    project_data = result["teams"]["team-alpha"]["projects"]["PROJ-A"]

    # planning count 應為 1（活躍時間應被計入）
    planning = project_data["cycle_time"]["planning"]
    assert planning["count"] == 1


# ============================================================
# PR dev 補充輔助函式
# ============================================================

PR_BASE = datetime(2026, 2, 1, tzinfo=timezone.utc)


def make_pr(
    repo: str = "repo-a",
    jira_keys: list[str] | None = None,
    created_offset_h: float = 0,
    first_review_offset_h: float | None = None,
    merged_offset_h: float = 20,
    lines: int = 100,
    pr_number: int = 1,
) -> PRMetrics:
    """建立合成 PRMetrics。時間以 PR_BASE 為基準加上偏移小時數。"""
    created = PR_BASE + timedelta(hours=created_offset_h)
    first_review = (
        PR_BASE + timedelta(hours=first_review_offset_h)
        if first_review_offset_h is not None
        else None
    )
    merged = PR_BASE + timedelta(hours=merged_offset_h)
    return PRMetrics(
        repo=repo,
        pr_number=pr_number,
        title="test PR",
        jira_keys=jira_keys or [],
        created_at=created,
        first_review_at=first_review,
        merged_at=merged,
        lines_added=lines // 2,
        lines_deleted=lines // 2,
        is_large=lines > 400,
    )


# _build_jira_pr_index


def test_build_jira_pr_index_basic():
    """反向索引應正確建立，key 正規化為大寫。"""
    pr = make_pr(jira_keys=["proj-a-1", "PROJ-B-2"])
    index = _build_jira_pr_index([pr])

    assert "PROJ-A-1" in index
    assert "PROJ-B-2" in index
    assert index["PROJ-A-1"] == [pr]


def test_build_jira_pr_index_multiple_prs_same_issue():
    """同一 issue 關聯多個 PR 時，index 應包含所有 PR。"""
    pr1 = make_pr(jira_keys=["PROJ-A-1"], pr_number=1)
    pr2 = make_pr(jira_keys=["PROJ-A-1"], pr_number=2)
    index = _build_jira_pr_index([pr1, pr2])

    assert len(index["PROJ-A-1"]) == 2


def test_build_jira_pr_index_excludes_unmerged():
    """未 merge 的 PR 不應進入 index。"""
    merged_pr = make_pr(jira_keys=["PROJ-A-1"], merged_offset_h=10)
    unmerged_pr = PRMetrics(
        repo="repo-a",
        pr_number=2,
        title="unmerged",
        jira_keys=["PROJ-A-1"],
        created_at=PR_BASE,
        first_review_at=None,
        merged_at=None,
        lines_added=10,
        lines_deleted=0,
        is_large=False,
    )
    index = _build_jira_pr_index([merged_pr, unmerged_pr])

    assert len(index["PROJ-A-1"]) == 1
    assert index["PROJ-A-1"][0] is merged_pr


def test_build_jira_pr_index_empty():
    """空列表應回傳空 dict。"""
    assert _build_jira_pr_index([]) == {}


# _compute_pr_dev_hours


def test_compute_pr_dev_hours_with_review():
    """有 review 時，dev hours = created → first_review。"""
    pr = make_pr(created_offset_h=0, first_review_offset_h=8, merged_offset_h=20)
    assert _compute_pr_dev_hours([pr]) == 8.0


def test_compute_pr_dev_hours_without_review():
    """無 review 時，fallback 到 created → merged。"""
    pr = make_pr(created_offset_h=0, first_review_offset_h=None, merged_offset_h=20)
    assert _compute_pr_dev_hours([pr]) == 20.0


def test_compute_pr_dev_hours_multiple_prs():
    """多 PR 取 min(created_at) 和 min(first_review_at)。"""
    pr1 = make_pr(created_offset_h=0, first_review_offset_h=8, merged_offset_h=20, pr_number=1)
    pr2 = make_pr(created_offset_h=2, first_review_offset_h=6, merged_offset_h=24, pr_number=2)
    # earliest_start = +0h, earliest_review = +6h → 6h
    assert _compute_pr_dev_hours([pr1, pr2]) == 6.0


def test_compute_pr_dev_hours_empty():
    """空列表應回傳 0.0。"""
    assert _compute_pr_dev_hours([]) == 0.0


# _enhance_dev_durations_with_prs


def test_enhance_dev_jira_too_short():
    """Jira dev 過短時，應被 PR dev 取代。"""
    resolved = BASE_TIME + timedelta(days=5)
    issue = make_issue("PROJ-A-1", resolved=resolved, phase_durations={"dev": 0.25})
    pr = make_pr(jira_keys=["PROJ-A-1"], created_offset_h=0, first_review_offset_h=48, merged_offset_h=60)

    count = _enhance_dev_durations_with_prs([issue], _build_jira_pr_index([pr]))

    assert issue.phase_durations["dev"] == 48.0
    assert count == 1


def test_enhance_dev_jira_already_correct():
    """Jira dev 比 PR dev 更長時，保留 Jira 值。"""
    resolved = BASE_TIME + timedelta(days=5)
    issue = make_issue("PROJ-A-1", resolved=resolved, phase_durations={"dev": 72.0})
    pr = make_pr(jira_keys=["PROJ-A-1"], created_offset_h=0, first_review_offset_h=48, merged_offset_h=60)

    count = _enhance_dev_durations_with_prs([issue], _build_jira_pr_index([pr]))

    assert issue.phase_durations["dev"] == 72.0
    assert count == 0


def test_enhance_dev_no_matching_pr():
    """無對應 PR 時，不修改 issue。"""
    resolved = BASE_TIME + timedelta(days=5)
    issue = make_issue("PROJ-A-1", resolved=resolved, phase_durations={"dev": 0.1})
    pr = make_pr(jira_keys=["PROJ-B-99"])  # 不同 key

    count = _enhance_dev_durations_with_prs([issue], _build_jira_pr_index([pr]))

    assert issue.phase_durations["dev"] == 0.1
    assert count == 0


def test_enhance_dev_unresolved_skipped():
    """未 resolved 的 issue 應跳過，不修改。"""
    issue = make_issue("PROJ-A-1", resolved=None, phase_durations={"dev": 0.1})
    pr = make_pr(jira_keys=["PROJ-A-1"], created_offset_h=0, first_review_offset_h=48, merged_offset_h=60)

    count = _enhance_dev_durations_with_prs([issue], _build_jira_pr_index([pr]))

    assert issue.phase_durations["dev"] == 0.1
    assert count == 0


# 整合測試


def test_aggregate_dev_enhanced_by_pr():
    """aggregate() 應用 PR 數據補充 dev phase，cycle_time.dev.p50 反映補充後的值。"""
    resolved = NOW - timedelta(days=1)
    # Jira 只記了 0.25h（秒切）
    issue = make_issue(
        "PROJ-A-1",
        project="PROJ-A",
        resolved=resolved,
        phase_durations={"dev": 0.25},
    )
    # PR 顯示實際花了 48h
    pr = make_pr(
        repo="repo-a",
        jira_keys=["PROJ-A-1"],
        created_offset_h=0,
        first_review_offset_h=48,
        merged_offset_h=60,
    )
    config = {
        **SAMPLE_CONFIG,
        "teams": [
            {
                "id": "team-alpha",
                "name": "Team Alpha",
                "jira_projects": ["PROJ-A"],
                "github_repos": ["repo-a"],
            }
        ],
    }

    result = aggregate(config, [issue], github_data=[pr])
    dev_stat = result["teams"]["team-alpha"]["projects"]["PROJ-A"]["cycle_time"]["dev"]

    # p50 應反映 PR 的 48h（= 2.0 天）
    assert dev_stat["count"] == 1
    assert dev_stat["p50"] == 2.0


def test_aggregate_no_github_data_backward_compat():
    """github_data=None 時行為應與舊版完全一致，dev phase 保留 Jira 原值。"""
    resolved = NOW - timedelta(days=1)
    issue = make_issue("PROJ-A-1", project="PROJ-A", resolved=resolved, phase_durations={"dev": 48.0})

    result = aggregate(SAMPLE_CONFIG, [issue], github_data=None)
    dev_stat = result["teams"]["team-alpha"]["projects"]["PROJ-A"]["cycle_time"]["dev"]

    assert dev_stat["count"] == 1
    assert dev_stat["p50"] == 2.0
