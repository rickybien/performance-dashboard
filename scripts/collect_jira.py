"""collect_jira.py — Jira 資料收集模組

從 Jira Cloud 收集 issue 的 changelog，計算各階段停留時間。
使用 /rest/api/3/search/jql（Jira Cloud v3 API）。
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests

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
    summary: str = ""
    parent_key: Optional[str] = None        # parent issue key（Epic 時才有意義）
    parent_summary: Optional[str] = None    # parent issue 標題
    parent_issue_type: Optional[str] = None  # parent 的 issue type（如 "Epic"）
    status_transitions: list[dict] = field(default_factory=list)
    # 每個 dict: {"timestamp": "ISO str", "from_status": str, "to_status": str}


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


def compute_phase_durations(
    status_changes: list[tuple[datetime, str, str]],
    status_lookup: dict[str, str],
    issue_created: datetime,
    now: datetime,
    unmapped_collector: set | None = None,
) -> dict[str, float]:
    """計算各 phase 的累計停留時間（小時）。

    Args:
        status_changes: status 變更列表 [(timestamp, from_status, to_status), ...]，不需預先排序
        status_lookup: status → phase 反向查找字典
        issue_created: issue 建立時間（timezone-aware）
        now: 計算終止時間（timezone-aware）
        unmapped_collector: 若提供，遇到未對應的 status 會 add() 進去；否則 log warning

    Returns:
        {"planning": 12.5, "dev": 48.0, "unmapped": 2.0, ...}
        時間單位：小時，只含有停留時間的 phase
    """
    sorted_changes = sorted(status_changes, key=lambda x: x[0])
    phase_durations: dict[str, float] = {}

    if not sorted_changes:
        return phase_durations

    # 第一個變更前的時間：從 issue_created 到第一個狀態變更
    first_change_time, first_from, _ = sorted_changes[0]
    initial_phase = status_lookup.get(first_from)
    if initial_phase:
        duration_hours = (first_change_time - issue_created).total_seconds() / 3600
        if duration_hours > 0:
            phase_durations[initial_phase] = phase_durations.get(initial_phase, 0.0) + duration_hours
    elif first_from:
        duration_hours = (first_change_time - issue_created).total_seconds() / 3600
        if duration_hours > 0:
            if unmapped_collector is not None:
                unmapped_collector.add(first_from)
            else:
                logger.warning("未對應狀態: '%s'，計入 unmapped", first_from)
            phase_durations["unmapped"] = phase_durations.get("unmapped", 0.0) + duration_hours

    # 逐一處理狀態變更
    for i, (change_time, _from_status, to_status) in enumerate(sorted_changes):
        end_time = sorted_changes[i + 1][0] if i + 1 < len(sorted_changes) else now
        duration_hours = (end_time - change_time).total_seconds() / 3600

        if duration_hours <= 0:
            continue

        phase = status_lookup.get(to_status)
        if phase:
            phase_durations[phase] = phase_durations.get(phase, 0.0) + duration_hours
        elif to_status:
            if unmapped_collector is not None:
                unmapped_collector.add(to_status)
            else:
                logger.warning("未對應狀態: '%s'，計入 unmapped", to_status)
            phase_durations["unmapped"] = phase_durations.get("unmapped", 0.0) + duration_hours

    return phase_durations


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
    status_changes: list[tuple[datetime, str, str]] = []
    for entry in changelog_entries:
        entry_time = parse_jira_datetime(entry["created"])
        for item in entry.get("items", []):
            if item.get("field") == "status":
                from_status = item.get("fromString", "")
                to_status = item.get("toString", "")
                status_changes.append((entry_time, from_status, to_status))

    return compute_phase_durations(status_changes, status_lookup, issue_created, now)


def parse_jira_datetime(dt_str: str) -> datetime:
    """解析 Jira 回傳的 datetime 字串為 timezone-aware datetime。"""
    from dateutil import parser as dateutil_parser
    dt = dateutil_parser.parse(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def collect_jira(config: dict, since_hours: Optional[int] = None) -> list[IssueMetrics]:
    """從 Jira 收集所有團隊、專案的 issue 效能指標。

    Args:
        config: 完整 config.yaml 內容
        since_hours: 若指定，只收集最近 N 小時內有更新的 issue（增量模式）。
                     None 表示全量模式，收集 lookback_days 天內建立的所有 issue。

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

    collection_config = config.get("collection", {})
    lookback_days = collection_config.get("lookback_days", 90)
    jql_filter = collection_config.get("jira_jql_filter", "issuetype in (Story, Bug, Task, Sub-task)")
    api_delay = collection_config.get("api_delay_seconds", 0.5)
    changelog_delay = collection_config.get("jira_changelog_api_delay_seconds", 0.1)

    teams = config.get("teams", [])
    all_projects: list[str] = []
    for team in teams:
        all_projects.extend(team.get("jira_projects", []))

    all_issues: list[IssueMetrics] = []
    now = datetime.now(timezone.utc)

    search_url = f"{base_url}/rest/api/3/search/jql"
    auth = (email, api_token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    for project_key in all_projects:
        logger.info("收集 Jira 專案: %s", project_key)
        status_lookup = build_status_lookup(config, project_key)

        if since_hours is not None:
            jql = (
                f"project = {project_key} "
                f"AND {jql_filter} "
                f"AND updated >= -{since_hours}h "
                f"ORDER BY updated DESC"
            )
        else:
            jql = (
                f"project = {project_key} "
                f"AND {jql_filter} "
                f"AND created >= -{lookback_days}d "
                f"ORDER BY created DESC"
            )

        next_page_token: str | None = None
        page_size = 100

        while True:
            payload: dict = {
                "jql": jql,
                "maxResults": page_size,
                "fields": [
                    "summary", "status", "issuetype", "assignee",
                    "created", "resolutiondate", "customfield_10020",
                    "parent",
                ],
            }
            if next_page_token:
                payload["nextPageToken"] = next_page_token

            try:
                resp = requests.post(search_url, auth=auth, headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except requests.HTTPError as e:
                body = e.response.text if e.response is not None else ""
                logger.error("Jira API 錯誤 (project=%s): %s | response: %s", project_key, e, body)
                break
            except requests.RequestException as e:
                logger.error("Jira 連線錯誤 (project=%s): %s", project_key, e)
                break

            issues = data.get("issues", [])
            if not issues:
                break

            for issue in issues:
                try:
                    changelog_values = _fetch_issue_changelog(base_url, auth, issue["key"])
                    issue["changelog"] = {"histories": changelog_values}
                    time.sleep(changelog_delay)
                    metrics = _process_issue(issue, project_key, status_lookup, now)
                    all_issues.append(metrics)
                except Exception as e:
                    logger.error("處理 issue %s 時發生錯誤: %s", issue.get("key"), e)

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

            time.sleep(api_delay)

        time.sleep(api_delay)

    logger.info("共收集 %d 個 issue", len(all_issues))
    return all_issues


def _fetch_issue_changelog(base_url: str, auth: tuple, issue_key: str) -> list[dict]:
    """呼叫 /rest/api/3/issue/{key}/changelog，回傳 changelog entries。

    回傳格式與 search 嵌入式 changelog.histories 相容，
    每筆含 created 與 items[]{field, fromString, toString}。
    """
    url = f"{base_url}/rest/api/3/issue/{issue_key}/changelog"
    get_headers = {"Accept": "application/json"}
    entries: list[dict] = []
    start_at = 0
    page_size = 100

    while True:
        resp = requests.get(
            url,
            auth=auth,
            headers=get_headers,
            params={"startAt": start_at, "maxResults": page_size},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        values = data.get("values", [])
        entries.extend(values)
        if data.get("isLast", True) or len(values) < page_size:
            break
        start_at += page_size

    return entries


def _process_issue(issue: dict, project_key: str, status_lookup: dict[str, str], now: datetime) -> IssueMetrics:
    """將單一 Jira issue（dict）轉換為 IssueMetrics。"""
    fields = issue.get("fields", {})

    created = parse_jira_datetime(fields["created"])

    resolved = None
    if fields.get("resolutiondate"):
        resolved = parse_jira_datetime(fields["resolutiondate"])

    assignee = None
    if fields.get("assignee"):
        assignee = fields["assignee"].get("displayName")

    issue_type = fields.get("issuetype", {}).get("name", "Unknown")
    current_status = fields.get("status", {}).get("name", "Unknown")

    sprint_name = _get_sprint_name_from_field(fields.get("customfield_10020"))

    summary = fields.get("summary", "")

    parent_key = None
    parent_summary = None
    parent_issue_type = None
    parent = fields.get("parent")
    if parent:
        parent_key = parent.get("key")
        parent_fields = parent.get("fields", {})
        parent_summary = parent_fields.get("summary")
        parent_issue_type = parent_fields.get("issuetype", {}).get("name")

    changelog_entries: list[dict] = []
    for history in issue.get("changelog", {}).get("histories", []):
        entry = {
            "created": history["created"],
            "items": [
                {
                    "field": item.get("field"),
                    "fromString": item.get("fromString"),
                    "toString": item.get("toString"),
                }
                for item in history.get("items", [])
            ],
        }
        changelog_entries.append(entry)

    # 提取 status transitions 以供 cache 儲存（日後 remap 用）
    status_transitions: list[dict] = []
    for entry in changelog_entries:
        for item in entry.get("items", []):
            if item.get("field") == "status":
                status_transitions.append({
                    "timestamp": entry["created"],
                    "from_status": item.get("fromString", ""),
                    "to_status": item.get("toString", ""),
                })

    phase_durations = parse_changelog(changelog_entries, status_lookup, created, now)

    return IssueMetrics(
        key=issue["key"],
        project=project_key,
        issue_type=issue_type,
        created=created,
        resolved=resolved,
        phase_durations=phase_durations,
        current_status=current_status,
        assignee=assignee,
        sprint_name=sprint_name,
        summary=summary,
        parent_key=parent_key,
        parent_summary=parent_summary,
        parent_issue_type=parent_issue_type,
        status_transitions=status_transitions,
    )


def _get_sprint_name_from_field(sprint_field) -> Optional[str]:
    """從 customfield_10020（Sprint）取得衝刺名稱。"""
    if not sprint_field or not isinstance(sprint_field, list):
        return None
    sprint = sprint_field[-1]
    if isinstance(sprint, dict):
        return sprint.get("name")
    if isinstance(sprint, str) and "name=" in sprint:
        import re
        match = re.search(r"name=([^,\]]+)", sprint)
        if match:
            return match.group(1)
    return None
