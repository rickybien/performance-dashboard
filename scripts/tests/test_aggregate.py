"""test_aggregate.py — aggregate 模組單元測試

所有測試使用合成 IssueMetrics，不依賴任何外部服務。
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from aggregate import (
    aggregate,
    compute_percentile_stats,
    compute_throughput,
    compute_weekly_trend,
    group_by_team_project,
)
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
) -> IssueMetrics:
    """建立合成 IssueMetrics。"""
    return IssueMetrics(
        key=key,
        project=project,
        issue_type="Story",
        created=created or BASE_TIME,
        resolved=resolved,
        phase_durations=phase_durations or {"dev": 48.0},
        current_status="Done" if resolved else "In Progress",
        assignee=None,
        sprint_name=None,
    )


SAMPLE_CONFIG = {
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
    """p50/p85 應正確計算並轉換為天。"""
    # 10 個值：24, 48, 72, ..., 240 小時（1-10 天）
    values = [24.0 * i for i in range(1, 11)]
    stats = compute_percentile_stats(values)

    # p50 = 5.5 天（5 和 6 的平均）
    assert abs(stats["p50"] - 5.5) < 0.1
    # p85 = 8.65 天
    assert abs(stats["p85"] - 8.65) < 0.1
    assert stats["count"] == 10


def test_compute_percentile_stats_empty():
    """空列表應回傳 count=0 且 p50/p85 為 0。"""
    stats = compute_percentile_stats([])
    assert stats["p50"] == 0.0
    assert stats["p85"] == 0.0
    assert stats["count"] == 0


def test_compute_percentile_stats_single():
    """只有一個值時，p50 和 p85 都應等於該值。"""
    stats = compute_percentile_stats([48.0])
    assert abs(stats["p50"] - 2.0) < 0.01  # 48h = 2 天
    assert abs(stats["p85"] - 2.0) < 0.01
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
