"""aggregate.py — 聚合模組

將收集到的原始 IssueMetrics 聚合為 dashboard.json 格式。
所有計算在此完成，前端只讀取預計算結果。
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from collect_jira import IssueMetrics

logger = logging.getLogger(__name__)

# 計算 total 時排除的 phase（這些 phase 不算入週期時間）
EXCLUDED_FROM_TOTAL = {"backlog", "done", "unmapped"}

# 計算吞吐量時視為完成的 phase
DONE_PHASES = {"done"}


def compute_percentile_stats(values: list[float]) -> dict:
    """計算百分位統計數據。

    Args:
        values: 時間值列表（小時）

    Returns:
        {"p50": float, "p85": float, "count": int}  # 輸出單位：天
        若 values 為空，回傳 count=0 且 p50/p85 為 0
    """
    if not values:
        return {"p50": 0.0, "p85": 0.0, "count": 0}

    sorted_values = sorted(values)
    n = len(sorted_values)

    def percentile(p: float) -> float:
        """計算第 p 百分位（0-100）。"""
        if n == 1:
            return sorted_values[0]
        index = (p / 100) * (n - 1)
        lower = int(index)
        upper = lower + 1
        if upper >= n:
            return sorted_values[lower]
        fraction = index - lower
        return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])

    p50_hours = percentile(50)
    p85_hours = percentile(85)

    # 轉換為天
    return {
        "p50": round(p50_hours / 24, 2),
        "p85": round(p85_hours / 24, 2),
        "count": n,
    }


def group_by_team_project(
    config: dict,
    issues: list[IssueMetrics],
) -> dict[str, dict[str, list[IssueMetrics]]]:
    """將 issues 依 team → project 分組。

    Args:
        config: 完整 config.yaml 內容
        issues: 所有 IssueMetrics

    Returns:
        {team_id: {project_key: [IssueMetrics]}}
    """
    # 建立 project_key → team_id 的反向查找
    project_to_team: dict[str, str] = {}
    for team in config.get("teams", []):
        team_id = team["id"]
        for project_key in team.get("jira_projects", []):
            project_to_team[project_key] = team_id

    result: dict[str, dict[str, list[IssueMetrics]]] = {}

    # 初始化所有 team/project 的空列表
    for team in config.get("teams", []):
        team_id = team["id"]
        result[team_id] = {}
        for project_key in team.get("jira_projects", []):
            result[team_id][project_key] = []

    # 分配 issues
    for issue in issues:
        team_id = project_to_team.get(issue.project)
        if team_id and team_id in result:
            if issue.project in result[team_id]:
                result[team_id][issue.project].append(issue)
            else:
                result[team_id][issue.project] = [issue]
        else:
            logger.warning("issue %s 的 project %s 未對應到任何 team", issue.key, issue.project)

    return result


def compute_throughput(issues: list[IssueMetrics], recent_days: int) -> dict:
    """計算吞吐量統計。

    Args:
        issues: issue 列表
        recent_days: 計算最近幾天的完成數

    Returns:
        {"completed_issues": int, "story_points": null, "weekly_trend": [int, ...]}
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=recent_days)

    resolved_issues = [
        issue for issue in issues
        if issue.resolved is not None and issue.resolved >= cutoff
    ]

    weekly_trend = compute_weekly_trend(issues, num_weeks=4)

    return {
        "completed_issues": len(resolved_issues),
        "story_points": None,  # Phase 2+ 預留
        "weekly_trend": weekly_trend,
    }


def compute_weekly_trend(issues: list[IssueMetrics], num_weeks: int = 4) -> list[int]:
    """計算最近 N 週各週的完成數。

    Args:
        issues: issue 列表
        num_weeks: 計算週數

    Returns:
        從最舊到最新排列的各週完成數，長度為 num_weeks
    """
    now = datetime.now(timezone.utc)
    # 計算各週的起始時間（從最近一週往前推）
    week_counts = [0] * num_weeks

    for issue in issues:
        if issue.resolved is None:
            continue
        delta_days = (now - issue.resolved).days
        week_index = delta_days // 7
        if 0 <= week_index < num_weeks:
            # week_index 0 = 最近一週，放在列表末尾
            list_index = num_weeks - 1 - week_index
            week_counts[list_index] += 1

    return week_counts


def _compute_iso_week_label(now: datetime, weeks_ago: int) -> str:
    """計算 N 週前的 ISO week 標籤，如 '2026-W04'。"""
    target = now - timedelta(weeks=weeks_ago)
    iso_year, iso_week, _ = target.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _compute_cycle_time_for_project(
    issues: list[IssueMetrics],
    phases: list[dict],
) -> dict:
    """計算單一專案的週期時間統計。

    Returns:
        {phase_id: {"p50": float, "p85": float, "count": int}, ..., "total": {...}}
    """
    # 只計算已解決的 issue
    resolved_issues = [issue for issue in issues if issue.resolved is not None]

    phase_ids = [p["id"] for p in phases]
    cycle_time: dict[str, dict] = {}

    for phase_id in phase_ids:
        values = [
            issue.phase_durations[phase_id]
            for issue in resolved_issues
            if phase_id in issue.phase_durations and issue.phase_durations[phase_id] > 0
        ]
        cycle_time[phase_id] = compute_percentile_stats(values)

    # 計算 total（排除 backlog、done、unmapped）
    total_values: list[float] = []
    for issue in resolved_issues:
        total_hours = sum(
            hours
            for phase, hours in issue.phase_durations.items()
            if phase not in EXCLUDED_FROM_TOTAL and hours > 0
        )
        if total_hours > 0:
            total_values.append(total_hours)

    cycle_time["total"] = compute_percentile_stats(total_values)

    return cycle_time


def _get_week_labels(now: datetime, num_weeks: int = 4) -> list[str]:
    """取得最近 N 週的 ISO week 標籤，從最舊到最新。"""
    return [_compute_iso_week_label(now, num_weeks - 1 - i) for i in range(num_weeks)]


# ============================================================
# GitHub PR 指標輔助函式
# ============================================================


def _compute_hour_stats(values: list[float]) -> dict:
    """計算百分位統計，保留小時單位（不轉換為天）。

    Args:
        values: 小時值列表

    Returns:
        {"p50": float, "p85": float, "count": int}
    """
    if not values:
        return {"p50": 0.0, "p85": 0.0, "count": 0}

    sorted_values = sorted(values)
    n = len(sorted_values)

    def percentile(p: float) -> float:
        if n == 1:
            return sorted_values[0]
        index = (p / 100) * (n - 1)
        lower = int(index)
        upper = lower + 1
        if upper >= n:
            return sorted_values[lower]
        fraction = index - lower
        return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])

    return {
        "p50": round(percentile(50), 1),
        "p85": round(percentile(85), 1),
        "count": n,
    }


def _group_prs_by_team(config: dict, prs: list) -> dict[str, list]:
    """依 repo → team 將 PRs 分組。

    Args:
        config: 完整 config.yaml 內容
        prs: PRMetrics 列表

    Returns:
        {team_id: [PRMetrics]}
    """
    repo_to_team: dict[str, str] = {}
    for team in config.get("teams", []):
        for repo in team.get("github_repos", []):
            repo_to_team[repo] = team["id"]

    result: dict[str, list] = {team["id"]: [] for team in config.get("teams", [])}

    for pr in prs:
        team_id = repo_to_team.get(pr.repo)
        if team_id and team_id in result:
            result[team_id].append(pr)
        else:
            logger.warning("PR repo %s 未對應到任何 team", pr.repo)

    return result


def _compute_pr_metrics(prs: list, large_pr_threshold: int) -> Optional[dict]:
    """計算一組 PR 的指標摘要。

    Args:
        prs: PRMetrics 列表
        large_pr_threshold: 超過此行數視為大型 PR

    Returns:
        PR 指標 dict，若 prs 為空則回傳 None
    """
    merged = [pr for pr in prs if pr.merged_at is not None]
    if not merged:
        return None

    pickup_hours = [
        (pr.first_review_at - pr.created_at).total_seconds() / 3600
        for pr in merged
        if pr.first_review_at is not None
    ]

    merge_hours = [
        (pr.merged_at - pr.created_at).total_seconds() / 3600
        for pr in merged
    ]

    large_count = sum(1 for pr in merged if pr.is_large)

    return {
        "total_prs_merged": len(merged),
        "pickup_hours": _compute_hour_stats(pickup_hours),
        "merge_time_hours": _compute_hour_stats(merge_hours),
        "large_pr_pct": round(large_count / len(merged) * 100, 1),
    }


# ============================================================
# Jenkins 建置指標輔助函式
# ============================================================


def _group_builds_by_team(config: dict, builds: list) -> dict[str, list]:
    """依 job → team 將 builds 分組。

    Args:
        config: 完整 config.yaml 內容
        builds: BuildResult 列表

    Returns:
        {team_id: [BuildResult]}
    """
    job_to_team: dict[str, str] = {}
    for team in config.get("teams", []):
        for job in team.get("jenkins_jobs", []):
            job_to_team[job] = team["id"]

    result: dict[str, list] = {team["id"]: [] for team in config.get("teams", [])}

    for build in builds:
        team_id = job_to_team.get(build.job_name)
        if team_id and team_id in result:
            result[team_id].append(build)

    return result


def _compute_build_weekly_trend(builds: list, num_weeks: int = 4) -> list[int]:
    """計算最近 N 週各週的建置數（從最舊到最新）。"""
    now = datetime.now(timezone.utc)
    week_counts = [0] * num_weeks

    for build in builds:
        delta_days = (now - build.timestamp).days
        week_index = delta_days // 7
        if 0 <= week_index < num_weeks:
            list_index = num_weeks - 1 - week_index
            week_counts[list_index] += 1

    return week_counts


def _compute_build_metrics(builds: list) -> Optional[dict]:
    """計算 Jenkins 建置指標摘要。

    Args:
        builds: BuildResult 列表

    Returns:
        建置指標 dict，若無完成的建置則回傳 None
    """
    completed = [b for b in builds if b.result is not None]
    if not completed:
        return None

    success_count = sum(1 for b in completed if b.result == "SUCCESS")
    success_rate = round(success_count / len(completed) * 100, 1)

    durations = [b.duration_ms / 60000 for b in completed if b.duration_ms > 0]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0

    weekly_trend = _compute_build_weekly_trend(builds, num_weeks=4)

    return {
        "success_rate": success_rate,
        "avg_duration_mins": avg_duration,
        "total_builds": len(completed),
        "weekly_trend": weekly_trend,
    }


# ============================================================
# SA/SD 獨立票識別與合併函式
# ============================================================


def _build_sa_sd_matcher(
    config: dict,
    team_id: Optional[str],
) -> tuple[set[str], list[re.Pattern]]:
    """建構 SA/SD 識別規則。

    Args:
        config: 完整 config.yaml 內容
        team_id: 目前 team id，用於查找 per-team override

    Returns:
        (issue_types_set, compiled_patterns)
    """
    rules = config.get("sa_sd_rules", {})
    if not rules:
        return (set(), [])
    source = rules
    if team_id and rules.get("overrides", {}).get(team_id):
        source = rules["overrides"][team_id]
    types = set(source.get("issue_types", []))
    patterns = [re.compile(p, re.IGNORECASE) for p in source.get("summary_patterns", [])]
    return (types, patterns)


def _is_sa_sd_issue(
    issue: IssueMetrics,
    issue_types: set[str],
    patterns: list[re.Pattern],
) -> bool:
    """判斷是否為 SA/SD 獨立票。"""
    if issue.issue_type in issue_types:
        return True
    return any(p.search(issue.summary or "") for p in patterns)


def _compute_sa_sd_planning_hours(issue: IssueMetrics) -> float:
    """SA/SD 票的活躍時間（排除 backlog/done/unmapped），作為 planning 數據點。"""
    return sum(
        hours for phase, hours in issue.phase_durations.items()
        if phase not in EXCLUDED_FROM_TOTAL and hours > 0
    )


def _merge_sa_sd_into_planning(
    cycle_time: dict,
    normal_issues: list[IssueMetrics],
    sa_sd_hours: list[float],
) -> None:
    """將 SA/SD 活躍小時數併入 cycle_time["planning"]（原地修改）。

    只在 sa_sd_hours 非空時才修改，避免不必要的重算。
    """
    if not sa_sd_hours:
        return
    planning_values = [
        issue.phase_durations["planning"]
        for issue in normal_issues
        if issue.resolved is not None
        and "planning" in issue.phase_durations
        and issue.phase_durations["planning"] > 0
    ]
    planning_values.extend(sa_sd_hours)
    cycle_time["planning"] = compute_percentile_stats(planning_values)


def _find_bottleneck_issues(
    issues: list[IssueMetrics],
    bottleneck_phase: str,
    jira_base_url: str,
    limit: int = 10,
) -> list[dict]:
    """找出瓶頸 phase 停留最久的 top N issues。

    Args:
        issues: 該 team 的所有 IssueMetrics
        bottleneck_phase: 瓶頸 phase id
        jira_base_url: Jira Cloud base URL，用於組裝連結
        limit: 回傳筆數上限

    Returns:
        排序後的 issue 列表（停留天數降序）
    """
    candidates = []
    for issue in issues:
        if issue.resolved is None:
            continue
        hours = issue.phase_durations.get(bottleneck_phase, 0.0)
        if hours > 0:
            candidates.append((hours, issue))

    candidates.sort(key=lambda x: x[0], reverse=True)

    browse_url = jira_base_url.rstrip("/") + "/browse/"
    result = []
    for hours, issue in candidates[:limit]:
        is_epic = issue.parent_issue_type == "Epic"
        result.append({
            "key": issue.key,
            "summary": issue.summary,
            "parent_key": issue.parent_key if is_epic else None,
            "parent_summary": issue.parent_summary if is_epic else None,
            "phase_duration_days": round(hours / 24, 2),
            "url": browse_url + issue.key,
        })

    return result


def aggregate(
    config: dict,
    jira_data: list[IssueMetrics],
    github_data: Optional[list] = None,   # list[PRMetrics]
    jenkins_data: Optional[list] = None,  # list[BuildResult]
) -> dict:
    """聚合所有資料，建構 dashboard.json 結構。

    Args:
        config: 完整 config.yaml 內容
        jira_data: 從 collect_jira 取得的 IssueMetrics 列表
        github_data: 從 collect_github 取得的 PRMetrics 列表，None 表示未收集
        jenkins_data: 從 collect_jenkins 取得的 BuildResult 列表，None 表示未收集

    Returns:
        完整的 dashboard.json dict
    """
    now = datetime.now(timezone.utc)
    collection_config = config.get("collection", {})
    lookback_days = collection_config.get("lookback_days", 90)
    recent_days = collection_config.get("recent_days", 30)
    phases = config.get("phases", [])
    jira_base_url = config.get("jira", {}).get("base_url", "")

    large_pr_threshold = config.get("dashboard", {}).get("large_pr_threshold", 400)

    period_start = now - timedelta(days=lookback_days)

    # 分組 Jira issues
    grouped = group_by_team_project(config, jira_data)

    # 分組 GitHub PRs 和 Jenkins builds（若有）
    prs_by_team = _group_prs_by_team(config, github_data or [])
    builds_by_team = _group_builds_by_team(config, jenkins_data or [])

    # 全域 PR 摘要
    all_prs = github_data or []
    all_merged_prs = [pr for pr in all_prs if pr.merged_at is not None]
    total_prs_merged: Optional[int] = len(all_merged_prs) if all_prs else None

    all_pickup_hours = [
        (pr.first_review_at - pr.created_at).total_seconds() / 3600
        for pr in all_merged_prs
        if pr.first_review_at is not None
    ]
    avg_pr_pickup_hours: Optional[float] = None
    if all_pickup_hours:
        stats = _compute_hour_stats(all_pickup_hours)
        avg_pr_pickup_hours = stats["p50"]

    # 計算全域 Jira 摘要
    resolved_all = [issue for issue in jira_data if issue.resolved is not None]
    total_completed = len(resolved_all)

    avg_cycle_time_days = None
    if resolved_all:
        total_hours_list = [
            sum(
                h for p, h in issue.phase_durations.items()
                if p not in EXCLUDED_FROM_TOTAL and h > 0
            )
            for issue in resolved_all
        ]
        non_zero = [h for h in total_hours_list if h > 0]
        if non_zero:
            avg_cycle_time_days = round(sum(non_zero) / len(non_zero) / 24, 2)

    # 建構 teams 結構
    teams_output: dict = {}
    trends_output: dict = {}
    week_labels = _get_week_labels(now, num_weeks=4)

    for team in config.get("teams", []):
        team_id = team["id"]
        team_name = team["name"]
        team_projects = grouped.get(team_id, {})
        team_prs = prs_by_team.get(team_id, [])
        team_builds = builds_by_team.get(team_id, [])

        sa_sd_types, sa_sd_pats = _build_sa_sd_matcher(config, team_id)
        has_sa_sd = bool(sa_sd_types or sa_sd_pats)

        projects_output: dict = {}
        all_team_issues: list[IssueMetrics] = []
        all_team_sa_sd_hours: list[float] = []

        for project_key, project_issues in team_projects.items():
            if has_sa_sd:
                normal_issues: list[IssueMetrics] = []
                sa_sd_hours: list[float] = []
                for issue in project_issues:
                    if _is_sa_sd_issue(issue, sa_sd_types, sa_sd_pats):
                        if issue.resolved is not None:
                            h = _compute_sa_sd_planning_hours(issue)
                            if h > 0:
                                sa_sd_hours.append(h)
                    else:
                        normal_issues.append(issue)
                all_team_sa_sd_hours.extend(sa_sd_hours)
                all_team_issues.extend(normal_issues)
            else:
                normal_issues = project_issues
                sa_sd_hours = []
                all_team_issues.extend(project_issues)

            cycle_time = _compute_cycle_time_for_project(normal_issues, phases)
            _merge_sa_sd_into_planning(cycle_time, normal_issues, sa_sd_hours)
            throughput = compute_throughput(normal_issues, recent_days)

            projects_output[project_key] = {
                "cycle_time": cycle_time,
                "throughput": throughput,
                "pr_metrics": None,  # PR 指標聚合在 team 層級，project 層級留空
            }

        # Team 聚合（跨所有 project）
        team_cycle_time = _compute_cycle_time_for_project(all_team_issues, phases)
        _merge_sa_sd_into_planning(team_cycle_time, all_team_issues, all_team_sa_sd_hours)
        team_throughput = compute_throughput(all_team_issues, recent_days)
        team_pr_metrics = _compute_pr_metrics(team_prs, large_pr_threshold)
        team_build_metrics = _compute_build_metrics(team_builds)

        # 找出瓶頸 phase（p50 最高，排除 backlog/done/unmapped/total）
        bottleneck_phase_id = None
        max_p50 = 0.0
        for phase in phases:
            pid = phase["id"]
            if pid in EXCLUDED_FROM_TOTAL:
                continue
            stat = team_cycle_time.get(pid)
            if stat and stat["count"] > 0 and stat["p50"] > max_p50:
                max_p50 = stat["p50"]
                bottleneck_phase_id = pid

        bottleneck_issues = []
        if bottleneck_phase_id and jira_base_url:
            bottleneck_issues = _find_bottleneck_issues(
                all_team_issues, bottleneck_phase_id, jira_base_url,
            )

        teams_output[team_id] = {
            "name": team_name,
            "projects": projects_output,
            "aggregated": {
                "cycle_time": team_cycle_time,
                "throughput": team_throughput,
                "pr_metrics": team_pr_metrics,
                "build_metrics": team_build_metrics,
                "bottleneck_phase": bottleneck_phase_id,
                "bottleneck_issues": bottleneck_issues,
            },
        }

        # 趨勢資料
        team_resolved_weekly = compute_weekly_trend(all_team_issues, num_weeks=4)
        team_cycle_p50_weekly = _compute_weekly_cycle_time_p50(all_team_issues, num_weeks=4)

        # PR pickup trend：取 team pr_metrics 中的 p50（單一值，非週趨勢）
        team_pr_pickup_p50 = (
            team_pr_metrics["pickup_hours"]["p50"]
            if team_pr_metrics and team_pr_metrics["pickup_hours"]["count"] > 0
            else None
        )

        trends_output[team_id] = {
            "weeks": week_labels,
            "cycle_time_p50": team_cycle_p50_weekly,
            "throughput": team_resolved_weekly,
            "pr_pickup_hours": team_pr_pickup_p50,
        }

    # 建構 meta section，供前端不必讀 config.yaml 即可取得 phases 與 thresholds
    phases_meta = [
        {"id": p["id"], "label": p["label"], "color": p.get("color", "#888888")}
        for p in phases
        if p["id"] not in {"backlog", "done"}  # 只顯示參與週期時間的 phase
    ]
    thresholds = config.get("dashboard", {}).get(
        "cycle_time_thresholds", {"good": 2.0, "warning": 5.0}
    )

    return {
        "generated_at": now.isoformat(),
        "period": {
            "start": period_start.date().isoformat(),
            "end": now.date().isoformat(),
        },
        "meta": {
            "phases": phases_meta,
            "thresholds": thresholds,
        },
        "summary": {
            "total_completed_issues": total_completed,
            "avg_cycle_time_days": avg_cycle_time_days,
            "avg_cycle_time_prev_period": None,  # 未來實作
            "total_prs_merged": total_prs_merged,
            "avg_pr_pickup_hours": avg_pr_pickup_hours,
        },
        "teams": teams_output,
        "trends": trends_output,
    }


def _compute_weekly_cycle_time_p50(
    issues: list[IssueMetrics],
    num_weeks: int = 4,
) -> list[Optional[float]]:
    """計算最近 N 週各週的 cycle time p50（天）。

    Returns:
        從最舊到最新排列，若該週無資料則為 None
    """
    now = datetime.now(timezone.utc)
    weekly_hours: list[list[float]] = [[] for _ in range(num_weeks)]

    for issue in issues:
        if issue.resolved is None:
            continue
        delta_days = (now - issue.resolved).days
        week_index = delta_days // 7
        if 0 <= week_index < num_weeks:
            total_hours = sum(
                h for p, h in issue.phase_durations.items()
                if p not in EXCLUDED_FROM_TOTAL and h > 0
            )
            if total_hours > 0:
                list_index = num_weeks - 1 - week_index
                weekly_hours[list_index].append(total_hours)

    result: list[Optional[float]] = []
    for hours_list in weekly_hours:
        if hours_list:
            stats = compute_percentile_stats(hours_list)
            result.append(stats["p50"])
        else:
            result.append(None)

    return result
