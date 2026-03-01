"""test_collect_jira.py — collect_jira 模組單元測試

所有測試不依賴真實 Jira API，使用合成資料。
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# 將 scripts/ 加入 path，使測試可以 import collect_jira
sys.path.insert(0, str(Path(__file__).parent.parent))

from collect_jira import IssueMetrics, build_status_lookup, compute_phase_durations, parse_changelog


# ============================================================
# 測試輔助
# ============================================================

SAMPLE_CONFIG = {
    "status_mapping": {
        "default": {
            "backlog": ["To Do", "Backlog"],
            "planning": ["Analysis", "SA/SD"],
            "dev": ["In Progress", "Developing"],
            "review": ["In Review", "Code Review"],
            "dev_test": ["Dev Testing", "RD Testing"],
            "qa": ["QA", "QA Testing"],
            "staging": ["Staging", "UAT"],
            "done": ["Done", "Closed"],
        },
        "overrides": {
            "PROJ-SPECIAL": {
                "planning": ["Requirement Review", "Architecture Design"],
            }
        },
    }
}


def make_changelog_entry(created: str, from_status: str, to_status: str) -> dict:
    """建立 changelog history entry。"""
    return {
        "created": created,
        "items": [
            {
                "field": "status",
                "fromString": from_status,
                "toString": to_status,
            }
        ],
    }


def dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """建立 UTC datetime。"""
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# ============================================================
# build_status_lookup 測試
# ============================================================


def test_build_status_lookup_default():
    """預設映射應正確建立 status → phase 反向查找。"""
    lookup = build_status_lookup(SAMPLE_CONFIG, "PROJ-A")

    assert lookup["In Progress"] == "dev"
    assert lookup["Developing"] == "dev"
    assert lookup["In Review"] == "review"
    assert lookup["Code Review"] == "review"
    assert lookup["QA"] == "qa"
    assert lookup["QA Testing"] == "qa"
    assert lookup["Done"] == "done"
    assert lookup["Closed"] == "done"
    assert lookup["To Do"] == "backlog"
    assert lookup["Analysis"] == "planning"


def test_build_status_lookup_with_override():
    """per-project override 應覆蓋指定 phase 的狀態映射。"""
    lookup = build_status_lookup(SAMPLE_CONFIG, "PROJ-SPECIAL")

    # Override 的 planning 狀態
    assert lookup["Requirement Review"] == "planning"
    assert lookup["Architecture Design"] == "planning"

    # 非 planning 的 default 狀態仍應保留
    assert lookup["In Progress"] == "dev"
    assert lookup["Done"] == "done"

    # Default 的 planning 狀態（SA/SD, Analysis）被 override 覆蓋後不再有效，
    # 因為 override 替換整個 planning phase 的映射
    # 根據設計：override 只覆蓋 override 中指定的 phase，其他 phase 保留 default
    # 但 override 中的 planning 完全取代 default 的 planning
    assert "SA/SD" not in lookup or lookup.get("SA/SD") != "planning"


def test_build_status_lookup_no_overrides():
    """無 overrides 設定時不應崩潰。"""
    config_without_overrides = {
        "status_mapping": {
            "default": {"dev": ["In Progress"]},
        }
    }
    lookup = build_status_lookup(config_without_overrides, "PROJ-A")
    assert lookup["In Progress"] == "dev"


def test_build_status_lookup_empty_override_key():
    """overrides 為 None 時不應崩潰。"""
    config_null_overrides = {
        "status_mapping": {
            "default": {"dev": ["In Progress"]},
            "overrides": None,
        }
    }
    lookup = build_status_lookup(config_null_overrides, "PROJ-A")
    assert lookup["In Progress"] == "dev"


# ============================================================
# parse_changelog 測試
# ============================================================

SIMPLE_LOOKUP = {
    "To Do": "backlog",
    "Analysis": "planning",
    "In Progress": "dev",
    "In Review": "review",
    "QA Testing": "qa",
    "Done": "done",
}


def test_parse_changelog_linear_path():
    """正常線性流程：各 phase 時間應正確計算。"""
    created = dt(2026, 1, 1, 9, 0)
    now = dt(2026, 1, 10, 9, 0)

    entries = [
        make_changelog_entry("2026-01-01T10:00:00+00:00", "To Do", "Analysis"),
        make_changelog_entry("2026-01-02T09:00:00+00:00", "Analysis", "In Progress"),
        make_changelog_entry("2026-01-05T09:00:00+00:00", "In Progress", "In Review"),
        make_changelog_entry("2026-01-06T09:00:00+00:00", "In Review", "QA Testing"),
        make_changelog_entry("2026-01-08T09:00:00+00:00", "QA Testing", "Done"),
    ]

    durations = parse_changelog(entries, SIMPLE_LOOKUP, created, now)

    # backlog: 9:00 → 10:00 = 1 小時
    assert abs(durations.get("backlog", 0) - 1.0) < 0.01
    # planning: 10:00 → 次日 9:00 = 23 小時
    assert abs(durations.get("planning", 0) - 23.0) < 0.01
    # dev: Jan 2 9:00 → Jan 5 9:00 = 72 小時
    assert abs(durations.get("dev", 0) - 72.0) < 0.01
    # review: Jan 5 9:00 → Jan 6 9:00 = 24 小時
    assert abs(durations.get("review", 0) - 24.0) < 0.01
    # qa: Jan 6 9:00 → Jan 8 9:00 = 48 小時
    assert abs(durations.get("qa", 0) - 48.0) < 0.01
    # done: Jan 8 9:00 → now (Jan 10 9:00) = 48 小時
    assert abs(durations.get("done", 0) - 48.0) < 0.01


def test_parse_changelog_backward_transition():
    """回退（QA → Dev → QA）時各 phase 時間應累加，不重置。"""
    created = dt(2026, 1, 1, 0, 0)
    now = dt(2026, 1, 10, 0, 0)

    entries = [
        make_changelog_entry("2026-01-01T00:00:00+00:00", "To Do", "In Progress"),
        make_changelog_entry("2026-01-02T00:00:00+00:00", "In Progress", "QA Testing"),
        make_changelog_entry("2026-01-03T00:00:00+00:00", "QA Testing", "In Progress"),  # 回退
        make_changelog_entry("2026-01-05T00:00:00+00:00", "In Progress", "QA Testing"),  # 再進 QA
        make_changelog_entry("2026-01-08T00:00:00+00:00", "QA Testing", "Done"),
    ]

    durations = parse_changelog(entries, SIMPLE_LOOKUP, created, now)

    # dev 第一次：1 天 = 24 小時，第二次：2 天 = 48 小時，合計 72 小時
    assert abs(durations.get("dev", 0) - 72.0) < 0.01
    # qa 第一次：1 天 = 24 小時，第二次：3 天 = 72 小時，合計 96 小時
    assert abs(durations.get("qa", 0) - 96.0) < 0.01


def test_parse_changelog_unmapped_status():
    """未知狀態應計入 'unmapped' key，並記錄警告。"""
    created = dt(2026, 1, 1, 0, 0)
    now = dt(2026, 1, 5, 0, 0)

    entries = [
        make_changelog_entry("2026-01-01T00:00:00+00:00", "To Do", "UNKNOWN_STATUS"),
        make_changelog_entry("2026-01-03T00:00:00+00:00", "UNKNOWN_STATUS", "In Progress"),
    ]

    durations = parse_changelog(entries, SIMPLE_LOOKUP, created, now)

    # UNKNOWN_STATUS: 2 天 = 48 小時
    assert "unmapped" in durations
    assert abs(durations["unmapped"] - 48.0) < 0.01
    # In Progress → now: 2 天 = 48 小時
    assert abs(durations.get("dev", 0) - 48.0) < 0.01


def test_parse_changelog_in_progress_issue():
    """未解決的 issue 仍應計算已完成階段的時間。"""
    created = dt(2026, 1, 1, 0, 0)
    now = dt(2026, 1, 5, 0, 0)

    entries = [
        make_changelog_entry("2026-01-01T00:00:00+00:00", "To Do", "In Progress"),
    ]

    durations = parse_changelog(entries, SIMPLE_LOOKUP, created, now)

    # backlog: 0 小時（created 和第一個 change 同時）
    # dev: Jan 1 → now (Jan 5) = 96 小時
    assert abs(durations.get("dev", 0) - 96.0) < 0.01


def test_parse_changelog_empty_changelog():
    """空 changelog 不應崩潰，回傳空 dict。"""
    created = dt(2026, 1, 1, 0, 0)
    now = dt(2026, 1, 5, 0, 0)

    durations = parse_changelog([], SIMPLE_LOOKUP, created, now)

    assert isinstance(durations, dict)
    assert len(durations) == 0


def test_parse_changelog_non_status_items_ignored():
    """非 status 欄位的 changelog item 應被忽略。"""
    created = dt(2026, 1, 1, 0, 0)
    now = dt(2026, 1, 3, 0, 0)

    entries = [
        {
            "created": "2026-01-01T12:00:00+00:00",
            "items": [
                {"field": "assignee", "fromString": None, "toString": "Alice"},
                {"field": "status", "fromString": "To Do", "toString": "In Progress"},
            ],
        }
    ]

    durations = parse_changelog(entries, SIMPLE_LOOKUP, created, now)

    # backlog: 0:00 → 12:00 = 12 小時
    assert abs(durations.get("backlog", 0) - 12.0) < 0.01
    # dev: 12:00 → now = 36 小時
    assert abs(durations.get("dev", 0) - 36.0) < 0.01


# ============================================================
# compute_phase_durations 直接測試
# ============================================================


def make_status_changes(
    *args: tuple[str, str, str],
) -> list[tuple]:
    """建立 status_changes：(iso_timestamp, from_status, to_status)。"""
    from datetime import datetime, timezone
    result = []
    for ts, frm, to in args:
        from dateutil import parser as dateutil_parser
        parsed = dateutil_parser.parse(ts)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        result.append((parsed, frm, to))
    return result


def test_compute_phase_durations_linear_path():
    """compute_phase_durations：正常線性流程與 parse_changelog 結果一致。"""
    created = dt(2026, 1, 1, 9, 0)
    now = dt(2026, 1, 10, 9, 0)

    changes = make_status_changes(
        ("2026-01-01T10:00:00+00:00", "To Do", "Analysis"),
        ("2026-01-02T09:00:00+00:00", "Analysis", "In Progress"),
        ("2026-01-05T09:00:00+00:00", "In Progress", "In Review"),
        ("2026-01-06T09:00:00+00:00", "In Review", "QA Testing"),
        ("2026-01-08T09:00:00+00:00", "QA Testing", "Done"),
    )

    durations = compute_phase_durations(changes, SIMPLE_LOOKUP, created, now)

    assert abs(durations.get("backlog", 0) - 1.0) < 0.01
    assert abs(durations.get("planning", 0) - 23.0) < 0.01
    assert abs(durations.get("dev", 0) - 72.0) < 0.01
    assert abs(durations.get("review", 0) - 24.0) < 0.01
    assert abs(durations.get("qa", 0) - 48.0) < 0.01
    assert abs(durations.get("done", 0) - 48.0) < 0.01


def test_compute_phase_durations_empty():
    """空 status_changes 回傳空 dict。"""
    created = dt(2026, 1, 1, 0, 0)
    now = dt(2026, 1, 5, 0, 0)

    durations = compute_phase_durations([], SIMPLE_LOOKUP, created, now)

    assert isinstance(durations, dict)
    assert len(durations) == 0


def test_compute_phase_durations_unmapped_collector():
    """未對應狀態應 add() 進 unmapped_collector，不再 log warning。"""
    created = dt(2026, 1, 1, 0, 0)
    now = dt(2026, 1, 5, 0, 0)

    changes = make_status_changes(
        ("2026-01-01T00:00:00+00:00", "To Do", "UNKNOWN_A"),
        ("2026-01-03T00:00:00+00:00", "UNKNOWN_A", "UNKNOWN_B"),
        ("2026-01-04T00:00:00+00:00", "UNKNOWN_B", "In Progress"),
    )

    collector: set[str] = set()
    durations = compute_phase_durations(changes, SIMPLE_LOOKUP, created, now, unmapped_collector=collector)

    # 兩個未對應狀態都應被收集
    assert "UNKNOWN_A" in collector
    assert "UNKNOWN_B" in collector
    # 未對應時間應計入 unmapped
    assert "unmapped" in durations
    # dev: Jan 4 → now (Jan 5) = 24 小時
    assert abs(durations.get("dev", 0) - 24.0) < 0.01


def test_compute_phase_durations_unmapped_in_initial_state():
    """初始狀態（第一個變更前的 from_status）也應被 unmapped_collector 收集。"""
    created = dt(2026, 1, 1, 0, 0)
    now = dt(2026, 1, 5, 0, 0)

    changes = make_status_changes(
        ("2026-01-02T00:00:00+00:00", "MYSTERY", "In Progress"),
    )

    collector: set[str] = set()
    durations = compute_phase_durations(changes, SIMPLE_LOOKUP, created, now, unmapped_collector=collector)

    assert "MYSTERY" in collector
    assert "unmapped" in durations
    # 初始 MYSTERY: Jan 1 → Jan 2 = 24 小時
    assert abs(durations["unmapped"] - 24.0) < 0.01


# ============================================================
# Remap 場景測試
# ============================================================


def test_remap_with_updated_mapping():
    """當 status_transitions 存在且 config 更新 mapping，重算應反映新 mapping。"""
    created = dt(2026, 1, 1, 0, 0)
    now = dt(2026, 1, 5, 0, 0)

    # 舊 mapping 中 "Evaluate" 未對應；新 mapping 加入 planning
    new_lookup = dict(SIMPLE_LOOKUP)
    new_lookup["Evaluate"] = "planning"

    changes = make_status_changes(
        ("2026-01-01T00:00:00+00:00", "To Do", "Evaluate"),
        ("2026-01-03T00:00:00+00:00", "Evaluate", "In Progress"),
    )

    # 舊 mapping：Evaluate 計 unmapped
    old_durations = compute_phase_durations(changes, SIMPLE_LOOKUP, created, now)
    assert "unmapped" in old_durations
    assert abs(old_durations["unmapped"] - 48.0) < 0.01

    # 新 mapping：Evaluate 計 planning
    new_durations = compute_phase_durations(changes, new_lookup, created, now)
    assert "unmapped" not in new_durations
    assert abs(new_durations.get("planning", 0) - 48.0) < 0.01
    # dev: Jan 3 → now (Jan 5) = 48 小時
    assert abs(new_durations.get("dev", 0) - 48.0) < 0.01


def test_backward_compat_no_transitions():
    """舊格式 cache（無 status_transitions）：phase_durations 保持不動。

    模擬 main.py 的行為：無 transitions → 跳過 remap → phase_durations 不變。
    """
    # 假設舊 cache 已有 phase_durations，沒有 status_transitions
    old_cache_entry = {
        "key": "PROJ-1",
        "project": "PROJ",
        "created": "2026-01-01T00:00:00+00:00",
        "resolved": None,
        "phase_durations": {"dev": 72.0, "qa": 48.0},
        # 沒有 status_transitions
    }

    transitions = old_cache_entry.get("status_transitions", [])
    assert transitions == []  # 確認是舊格式

    # 模擬 remap 邏輯：無 transitions → 跳過
    if not transitions:
        remapped = False

    assert not remapped
    # phase_durations 應維持原值
    assert old_cache_entry["phase_durations"]["dev"] == 72.0
    assert old_cache_entry["phase_durations"]["qa"] == 48.0
