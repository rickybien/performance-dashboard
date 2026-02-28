"""collect_jira.py — Jira 資料收集模組

從 Jira Cloud 收集 issue 的 changelog，計算各階段停留時間。
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from jira import JIRA
from jira.exceptions import JIRAError

logger = logging.getLogger(__name__)


@dataclass
class IssueMetrics:
    """單一 Jira issue 的效能指標。"""

    key: str
    project: str
    issue_type: str
    created: datetime
    resolved: Optional[datetime]
    phase_durations: dict[str, float]  # phase → 累計小時
    current_status: str
    assignee: Optional[str]
    sprint_name: Optional[str]  # 供未來使用


def build_status_lookup(config: dict, project_key: str) -> dict[str, str]:
    """建立 status → phase 的反向查找字典。

    Args:
        config: 完整 config.yaml 內容
        project_key: Jira 專案代碼，如 "PROJ-A"

    Returns:
        {"In Progress": "dev", "QA Testing": "qa", ...}
    """
    status_mapping = config.get("status_mapping", {})
    default_mapping = status_mapping.get("default", {})
    overrides = status_mapping.get("overrides") or {}

    project_override = overrides.get(project_key, {})

    # 從 default 建立基礎 lookup，跳過被 override 取代的 phase
    lookup: dict[str, str] = {}
    for phase, statuses in default_mapping.items():
        if phase in project_override:
            # 此 phase 將被 override 完全取代，不採用 default 的映射
            continue
        for status in statuses:
            lookup[status] = phase

    # 套用 per-project override（完全取代對應 phase 的映射）
    for phase, statuses in project_override.items():
        for status in statuses:
            lookup[status] = phase

    return lookup


def parse_changelog(
    changelog_entries: list[dict],
    status_lookup: dict[str, str],
    issue_created: datetime,
    now: datetime,
) -> dict[str, float]:
    """從 changelog 計算各 phase 的累計停留時間（小時）。

    Args:
        changelog_entries: Jira changelog histories，每個 entry 含 created 與 items
        status_lookup: status → phase 反向查找字典
        issue_created: issue 建立時間（timezone-aware）
        now: 當前時間（timezone-aware），用於計算進行中 issue 的最後狀態

    Returns:
        {"planning": 12.5, "dev": 48.0, "unmapped": 2.0, ...}
        時間單位：小時，只含有停留時間的 phase
    """
    # 篩出 status 變更事件並排序
    status_changes: list[tuple[datetime, str, str]] = []  # (timestamp, from_status, to_status)
    for entry in changelog_entries:
        entry_time = _parse_jira_datetime(entry["created"])
        for item in entry.get("items", []):
            if item.get("field") == "status":
                from_status = item.get("fromString", "")
                to_status = item.get("toString", "")
                status_changes.append((entry_time, from_status, to_status))

    status_changes.sort(key=lambda x: x[0])

    phase_durations: dict[str, float] = {}

    if not status_changes:
        # 沒有任何狀態變更：issue 從建立到現在都在初始狀態
        # 初始狀態未知，不計算時間
        return phase_durations

    # 第一個變更前的時間：從 issue_created 到第一個狀態變更
    first_change_time, first_from, first_to = status_changes[0]
    initial_phase = status_lookup.get(first_from)
    if initial_phase:
        duration_hours = (first_change_time - issue_created).total_seconds() / 3600
        if duration_hours > 0:
            phase_durations[initial_phase] = phase_durations.get(initial_phase, 0.0) + duration_hours
    elif first_from:
        duration_hours = (first_change_time - issue_created).total_seconds() / 3600
        if duration_hours > 0:
            logger.warning("未對應狀態: '%s'，計入 unmapped", first_from)
            phase_durations["unmapped"] = phase_durations.get("unmapped", 0.0) + duration_hours

    # 逐一處理狀態變更
    for i, (change_time, from_status, to_status) in enumerate(status_changes):
        end_time = status_changes[i + 1][0] if i + 1 < len(status_changes) else now
        duration_hours = (end_time - change_time).total_seconds() / 3600

        if duration_hours <= 0:
            continue

        phase = status_lookup.get(to_status)
        if phase:
            phase_durations[phase] = phase_durations.get(phase, 0.0) + duration_hours
        elif to_status:
            logger.warning("未對應狀態: '%s'，計入 unmapped", to_status)
            phase_durations["unmapped"] = phase_durations.get("unmapped", 0.0) + duration_hours

    return phase_durations


def _parse_jira_datetime(dt_str: str) -> datetime:
    """解析 Jira 回傳的 datetime 字串為 timezone-aware datetime。"""
    from dateutil import parser as dateutil_parser
    dt = dateutil_parser.parse(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _get_resolved_time(issue) -> Optional[datetime]:
    """從 issue 欄位取得解決時間。"""
    resolutiondate = getattr(issue.fields, "resolutiondate", None)
    if resolutiondate:
        return _parse_jira_datetime(resolutiondate)
    return None


def _get_sprint_name(issue) -> Optional[str]:
    """嘗試從 customfield_10020（Sprint）取得衝刺名稱。"""
    sprint_field = getattr(issue.fields, "customfield_10020", None)
    if sprint_field and isinstance(sprint_field, list) and sprint_field:
        sprint = sprint_field[-1]
        # Sprint 物件可能有 name 屬性或以字串形式存在
        if hasattr(sprint, "name"):
            return sprint.name
        if isinstance(sprint, str) and "name=" in sprint:
            # 解析 "com.atlassian.greenhopper.service.sprint.Sprint@...[...name=Sprint 1,...]"
            import re
            match = re.search(r"name=([^,\]]+)", sprint)
            if match:
                return match.group(1)
    return None


def collect_jira(config: dict) -> list[IssueMetrics]:
    """從 Jira 收集所有團隊、專案的 issue 效能指標。

    Args:
        config: 完整 config.yaml 內容

    Returns:
        所有成功收集的 IssueMetrics 列表
    """
    import os

    jira_config = config.get("jira", {})
    base_url = os.environ.get("JIRA_BASE_URL") or jira_config.get("base_url", "")
    email = os.environ.get("JIRA_EMAIL", "")
    api_token = os.environ.get("JIRA_API_TOKEN", "")

    if not all([base_url, email, api_token]):
        raise ValueError(
            "缺少 Jira 認證設定。請確認環境變數 JIRA_BASE_URL、JIRA_EMAIL、JIRA_API_TOKEN 已設定。"
        )

    jira_client = JIRA(
        server=base_url,
        basic_auth=(email, api_token),
    )

    collection_config = config.get("collection", {})
    lookback_days = collection_config.get("lookback_days", 90)
    jql_filter = collection_config.get("jira_jql_filter", "issuetype in (Story, Bug, Task, Sub-task)")
    api_delay = collection_config.get("api_delay_seconds", 0.5)

    teams = config.get("teams", [])
    all_projects: list[str] = []
    for team in teams:
        all_projects.extend(team.get("jira_projects", []))

    all_issues: list[IssueMetrics] = []
    now = datetime.now(timezone.utc)

    for project_key in all_projects:
        logger.info("收集 Jira 專案: %s", project_key)
        status_lookup = build_status_lookup(config, project_key)

        jql = (
            f"project = {project_key} "
            f"AND {jql_filter} "
            f"AND created >= -{lookback_days}d "
            f"ORDER BY created DESC"
        )

        start_at = 0
        page_size = 100

        while True:
            try:
                issues = jira_client.search_issues(
                    jql,
                    startAt=start_at,
                    maxResults=page_size,
                    expand="changelog",
                )
            except JIRAError as e:
                logger.error("Jira API 錯誤 (project=%s, startAt=%d): %s", project_key, start_at, e)
                break

            if not issues:
                break

            for issue in issues:
                try:
                    metrics = _process_issue(issue, project_key, status_lookup, now)
                    all_issues.append(metrics)
                except Exception as e:
                    logger.error("處理 issue %s 時發生錯誤: %s", issue.key, e)

            if len(issues) < page_size:
                break

            start_at += page_size
            time.sleep(api_delay)

        time.sleep(api_delay)

    logger.info("共收集 %d 個 issue", len(all_issues))
    return all_issues


def _process_issue(issue, project_key: str, status_lookup: dict[str, str], now: datetime) -> IssueMetrics:
    """將單一 Jira issue 轉換為 IssueMetrics。"""
    fields = issue.fields

    created = _parse_jira_datetime(fields.created)
    resolved = _get_resolved_time(issue)

    assignee = None
    if hasattr(fields, "assignee") and fields.assignee:
        assignee = getattr(fields.assignee, "displayName", None)

    issue_type = "Unknown"
    if hasattr(fields, "issuetype") and fields.issuetype:
        issue_type = getattr(fields.issuetype, "name", "Unknown")

    current_status = "Unknown"
    if hasattr(fields, "status") and fields.status:
        current_status = getattr(fields.status, "name", "Unknown")

    # 取得 changelog entries
    changelog_entries: list[dict] = []
    if hasattr(issue, "changelog") and issue.changelog:
        for history in issue.changelog.histories:
            entry = {
                "created": history.created,
                "items": [
                    {
                        "field": item.field,
                        "fromString": item.fromString,
                        "toString": item.toString,
                    }
                    for item in history.items
                ],
            }
            changelog_entries.append(entry)

    phase_durations = parse_changelog(changelog_entries, status_lookup, created, now)

    return IssueMetrics(
        key=issue.key,
        project=project_key,
        issue_type=issue_type,
        created=created,
        resolved=resolved,
        phase_durations=phase_durations,
        current_status=current_status,
        assignee=assignee,
        sprint_name=_get_sprint_name(issue),
    )
