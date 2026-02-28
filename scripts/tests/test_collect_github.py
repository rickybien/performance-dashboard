"""test_collect_github.py — collect_github 模組單元測試

使用模擬物件，不依賴實際 GitHub API。
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from collect_github import PRMetrics, _extract_jira_keys, _get_first_review_time


# ============================================================
# _extract_jira_keys 測試
# ============================================================


def test_extract_jira_keys_basic():
    """應能從標題中提取 Jira key。"""
    keys = _extract_jira_keys("PROJ-123: Fix login bug", r"([A-Z][A-Z0-9]+-\d+)")
    assert keys == ["PROJ-123"]


def test_extract_jira_keys_multiple():
    """應能提取多個 Jira key。"""
    keys = _extract_jira_keys("Fix PROJ-123 and PROJ-456", r"([A-Z][A-Z0-9]+-\d+)")
    assert set(keys) == {"PROJ-123", "PROJ-456"}


def test_extract_jira_keys_no_match():
    """無匹配時應回傳空列表。"""
    keys = _extract_jira_keys("Fix login bug without ticket", r"([A-Z][A-Z0-9]+-\d+)")
    assert keys == []


def test_extract_jira_keys_body():
    """應能從 body 中提取 Jira key。"""
    text = "Minor refactor\n\nCloses ALPHA-999"
    keys = _extract_jira_keys(text, r"([A-Z][A-Z0-9]+-\d+)")
    assert "ALPHA-999" in keys


# ============================================================
# _get_first_review_time 測試
# ============================================================


def _make_review(login: str, submitted_at: datetime) -> MagicMock:
    review = MagicMock()
    review.user = MagicMock()
    review.user.login = login
    review.submitted_at = submitted_at
    return review


def test_get_first_review_time_returns_non_author_review():
    """應回傳第一個非作者的 review 時間。"""
    t1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    reviews = [_make_review("author", t1), _make_review("reviewer", t2)]
    pr = MagicMock()
    pr.number = 1
    pr.get_reviews.return_value = reviews

    result = _get_first_review_time(pr, "author")
    assert result == t2


def test_get_first_review_time_no_non_author_review():
    """只有作者自己 review 時應回傳 None。"""
    t1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    reviews = [_make_review("author", t1)]
    pr = MagicMock()
    pr.number = 1
    pr.get_reviews.return_value = reviews

    result = _get_first_review_time(pr, "author")
    assert result is None


def test_get_first_review_time_exception_returns_none():
    """API 拋出例外時應回傳 None，不中斷。"""
    pr = MagicMock()
    pr.number = 1
    pr.get_reviews.side_effect = Exception("API error")

    result = _get_first_review_time(pr, "author")
    assert result is None


# ============================================================
# _compute_pr_metrics 測試（在 aggregate.py 中）
# ============================================================


def _make_pr(
    repo: str = "repo-a",
    created_offset_h: float = 0,
    review_offset_h: float | None = 4,
    merged_offset_h: float = 20,
    lines: int = 200,
    large_threshold: int = 400,
) -> PRMetrics:
    base = datetime(2026, 2, 1, tzinfo=timezone.utc)
    created = base + timedelta(hours=created_offset_h)
    first_review = base + timedelta(hours=review_offset_h) if review_offset_h is not None else None
    merged = base + timedelta(hours=merged_offset_h)
    return PRMetrics(
        repo=repo,
        pr_number=1,
        title="test PR",
        jira_keys=[],
        created_at=created,
        first_review_at=first_review,
        merged_at=merged,
        lines_added=lines // 2,
        lines_deleted=lines // 2,
        is_large=lines > large_threshold,
    )


def test_compute_pr_metrics_basic():
    """應正確計算 pickup 和 merge 時間。"""
    from aggregate import _compute_pr_metrics

    pr = _make_pr(created_offset_h=0, review_offset_h=4, merged_offset_h=20)
    result = _compute_pr_metrics([pr], large_pr_threshold=400)

    assert result is not None
    assert result["total_prs_merged"] == 1
    assert result["pickup_hours"]["p50"] == 4.0
    assert result["merge_time_hours"]["p50"] == 20.0
    assert result["large_pr_pct"] == 0.0


def test_compute_pr_metrics_large_pr():
    """大型 PR 應計入 large_pr_pct。"""
    from aggregate import _compute_pr_metrics

    pr = _make_pr(lines=500, large_threshold=400)
    result = _compute_pr_metrics([pr], large_pr_threshold=400)

    assert result is not None
    assert result["large_pr_pct"] == 100.0


def test_compute_pr_metrics_no_review():
    """無 review 的 PR 不計入 pickup_hours。"""
    from aggregate import _compute_pr_metrics

    pr = _make_pr(review_offset_h=None)
    result = _compute_pr_metrics([pr], large_pr_threshold=400)

    assert result is not None
    assert result["pickup_hours"]["count"] == 0
    assert result["merge_time_hours"]["count"] == 1


def test_compute_pr_metrics_empty():
    """空列表應回傳 None。"""
    from aggregate import _compute_pr_metrics

    result = _compute_pr_metrics([], large_pr_threshold=400)
    assert result is None


def test_compute_pr_metrics_no_token(monkeypatch):
    """未設定 GITHUB_TOKEN 時 collect_github_prs 應回傳空列表。"""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    from collect_github import collect_github_prs

    result = collect_github_prs({"github": {"org": "test"}, "teams": [], "collection": {}})
    assert result == []
