"""test_collect_jenkins.py — collect_jenkins 模組單元測試

使用模擬物件，不依賴實際 Jenkins API。
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from collect_jenkins import BuildResult, _fetch_builds_for_job


# ============================================================
# 測試輔助
# ============================================================


def _build_result(result: str | None, duration_ms: int, days_ago: int = 1) -> dict:
    """建立模擬 Jenkins API 回傳的 build 字典。"""
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "number": 1,
        "result": result,
        "duration": duration_ms,
        "timestamp": int(ts.timestamp() * 1000),
    }


SAMPLE_JENKINS_CONFIG = {
    "jenkins": {
        "base_url": "https://jenkins.example.com",
        "enabled": True,
    },
    "collection": {
        "lookback_days": 90,
        "api_delay_seconds": 0,
    },
    "teams": [
        {
            "id": "team-alpha",
            "name": "Team Alpha",
            "jenkins_jobs": ["build-service-auth"],
        }
    ],
}


# ============================================================
# _compute_build_metrics 測試（在 aggregate.py 中）
# ============================================================


def _make_build(result: str | None, duration_ms: int, days_ago: int = 1) -> BuildResult:
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return BuildResult(
        job_name="test-job",
        build_number=1,
        result=result,
        duration_ms=duration_ms,
        timestamp=ts,
    )


def test_compute_build_metrics_success_rate():
    """success_rate 應為成功建置佔所有完成建置的百分比。"""
    from aggregate import _compute_build_metrics

    builds = [
        _make_build("SUCCESS", 300000),
        _make_build("SUCCESS", 360000),
        _make_build("FAILURE", 120000),
        _make_build("SUCCESS", 420000),
    ]
    result = _compute_build_metrics(builds)

    assert result is not None
    assert result["success_rate"] == 75.0
    assert result["total_builds"] == 4


def test_compute_build_metrics_avg_duration():
    """avg_duration_mins 應為持續時間的平均值（分鐘）。"""
    from aggregate import _compute_build_metrics

    builds = [
        _make_build("SUCCESS", 600000),   # 10 分鐘
        _make_build("SUCCESS", 1200000),  # 20 分鐘
    ]
    result = _compute_build_metrics(builds)

    assert result is not None
    assert result["avg_duration_mins"] == 15.0


def test_compute_build_metrics_excludes_in_progress():
    """進行中的建置（result=None）不應計入 total_builds 和 success_rate。"""
    from aggregate import _compute_build_metrics

    builds = [
        _make_build("SUCCESS", 300000),
        _make_build(None, 0),  # 進行中
    ]
    result = _compute_build_metrics(builds)

    assert result is not None
    assert result["total_builds"] == 1
    assert result["success_rate"] == 100.0


def test_compute_build_metrics_empty():
    """空列表應回傳 None。"""
    from aggregate import _compute_build_metrics

    result = _compute_build_metrics([])
    assert result is None


def test_compute_build_metrics_all_in_progress():
    """全部都是進行中時應回傳 None。"""
    from aggregate import _compute_build_metrics

    builds = [_make_build(None, 0), _make_build(None, 0)]
    result = _compute_build_metrics(builds)
    assert result is None


def test_compute_build_weekly_trend():
    """weekly_trend 應從最舊到最新排列。"""
    from aggregate import _compute_build_weekly_trend

    builds = [
        _make_build("SUCCESS", 300000, days_ago=1),   # 第 4 週（最新）
        _make_build("SUCCESS", 300000, days_ago=2),   # 第 4 週
        _make_build("SUCCESS", 300000, days_ago=8),   # 第 3 週
        _make_build("SUCCESS", 300000, days_ago=15),  # 第 2 週
        _make_build("SUCCESS", 300000, days_ago=22),  # 第 1 週（最舊）
    ]
    trend = _compute_build_weekly_trend(builds, num_weeks=4)

    assert len(trend) == 4
    assert trend[3] == 2  # 最近一週：2 筆
    assert trend[2] == 1  # 第 3 週：1 筆
    assert trend[1] == 1  # 第 2 週：1 筆
    assert trend[0] == 1  # 第 1 週：1 筆


def test_collect_jenkins_builds_disabled(monkeypatch):
    """jenkins.enabled = false 時應回傳空列表。"""
    from collect_jenkins import collect_jenkins_builds

    config = {"jenkins": {"enabled": False}, "teams": [], "collection": {}}
    result = collect_jenkins_builds(config)
    assert result == []


def test_collect_jenkins_builds_no_credentials(monkeypatch):
    """未設定環境變數時應回傳空列表。"""
    monkeypatch.delenv("JENKINS_USER", raising=False)
    monkeypatch.delenv("JENKINS_API_TOKEN", raising=False)

    from collect_jenkins import collect_jenkins_builds

    config = {
        "jenkins": {"enabled": True, "base_url": "https://jenkins.example.com"},
        "teams": [],
        "collection": {},
    }
    result = collect_jenkins_builds(config)
    assert result == []


def test_collect_jenkins_circuit_breaker(monkeypatch):
    """連續 3 次失敗後應立即放棄剩餘 jobs，不再繼續嘗試。"""
    monkeypatch.setenv("JENKINS_USER", "user")
    monkeypatch.setenv("JENKINS_API_TOKEN", "token")

    call_count = 0

    def mock_fetch(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return None  # 模擬連線失敗

    with patch("collect_jenkins._fetch_builds_for_job", side_effect=mock_fetch):
        from collect_jenkins import collect_jenkins_builds

        config = {
            "jenkins": {"enabled": True, "base_url": "https://jenkins.example.com"},
            "collection": {"lookback_days": 90, "api_delay_seconds": 0},
            "teams": [
                {
                    "id": "team-alpha",
                    "jenkins_jobs": ["job-1", "job-2", "job-3", "job-4", "job-5"],
                }
            ],
        }
        result = collect_jenkins_builds(config)

    # 連續 3 次失敗後停止，job-4 和 job-5 不應被呼叫
    assert result == []
    assert call_count == 3
