"""main.py — 資料管線協調器

讀取 config.yaml，執行資料收集與聚合，寫入 dashboard.json。
不含業務邏輯，只負責協調各模組。

增量模式：若 data/cache/issues.json 存在且未強制刷新，
只收集最近 incremental_overlap_hours 小時內有更新的 issue，與 cache 合併後聚合。
全量模式：cache 不存在或強制刷新時，重新收集完整 lookback_days 天的資料。

環境變數控制：
- FORCE_FULL_REFRESH=true → 全部資料來源都全量重抓
- FORCE_JIRA_REFRESH=true → 僅 Jira cache 全量重抓
- FORCE_PR_REFRESH=true → 僅 PR cache 全量重抓
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from aggregate import aggregate
from collect_github import PRMetrics, collect_github_prs
from collect_jenkins import collect_jenkins_builds
from collect_jira import (
    IssueMetrics,
    build_status_lookup,
    collect_jira,
    compute_phase_durations,
    parse_jira_datetime,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

# 專案根目錄（main.py 的上一層）
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_PATH = DATA_DIR / "cache" / "issues.json"
PR_CACHE_PATH = DATA_DIR / "cache" / "prs.json"


def load_config(config_path: Path) -> dict:
    """讀取 config.yaml。"""
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_dashboard_json(data: dict, now: datetime) -> None:
    """將 dashboard.json 寫入 latest/ 與 archive/YYYY-MM/ 兩個位置。"""
    # latest/
    latest_dir = DATA_DIR / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_path = latest_dir / "dashboard.json"
    _write_json(data, latest_path)
    logger.info("已寫入 %s", latest_path)

    # archive/YYYY-MM/
    month_str = now.strftime("%Y-%m")
    archive_dir = DATA_DIR / "archive" / month_str
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / "dashboard.json"
    _write_json(data, archive_path)
    logger.info("已寫入 %s", archive_path)


def _write_json(data: dict, path: Path) -> None:
    """寫入格式化 JSON 檔案，確保以換行符結尾。"""
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")


def _serialize_issue(issue: IssueMetrics) -> dict:
    """將 IssueMetrics 序列化為可 JSON 儲存的 dict。"""
    return {
        "key": issue.key,
        "project": issue.project,
        "issue_type": issue.issue_type,
        "created": issue.created.isoformat(),
        "resolved": issue.resolved.isoformat() if issue.resolved else None,
        "phase_durations": issue.phase_durations,
        "current_status": issue.current_status,
        "assignee": issue.assignee,
        "sprint_name": issue.sprint_name,
        "summary": issue.summary,
        "parent_key": issue.parent_key,
        "parent_summary": issue.parent_summary,
        "parent_issue_type": issue.parent_issue_type,
        "status_transitions": issue.status_transitions,
    }


def _deserialize_issue(d: dict) -> IssueMetrics:
    """從 dict 還原 IssueMetrics。"""
    return IssueMetrics(
        key=d["key"],
        project=d["project"],
        issue_type=d["issue_type"],
        created=datetime.fromisoformat(d["created"]),
        resolved=datetime.fromisoformat(d["resolved"]) if d["resolved"] else None,
        phase_durations=d["phase_durations"],
        current_status=d["current_status"],
        assignee=d.get("assignee"),
        sprint_name=d.get("sprint_name"),
        summary=d.get("summary", ""),
        parent_key=d.get("parent_key"),
        parent_summary=d.get("parent_summary"),
        parent_issue_type=d.get("parent_issue_type"),
        status_transitions=d.get("status_transitions", []),
    )


def load_issues_cache() -> dict[str, dict]:
    """載入 issue cache，回傳 {issue_key: serialized_dict}。檔案不存在時回傳 {}。"""
    if not CACHE_PATH.exists():
        return {}
    with CACHE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_issues_cache(cache: dict[str, dict]) -> None:
    """將 issue cache 寫入 data/cache/issues.json。"""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")
    logger.info("已寫入 cache: %s（%d 筆）", CACHE_PATH, len(cache))


def _serialize_pr(pr: PRMetrics) -> dict:
    """將 PRMetrics 序列化為可 JSON 儲存的 dict。"""
    return {
        "repo": pr.repo,
        "pr_number": pr.pr_number,
        "title": pr.title,
        "jira_keys": pr.jira_keys,
        "created_at": pr.created_at.isoformat(),
        "first_review_at": pr.first_review_at.isoformat() if pr.first_review_at else None,
        "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
        "lines_added": pr.lines_added,
        "lines_deleted": pr.lines_deleted,
        "is_large": pr.is_large,
    }


def _deserialize_pr(d: dict) -> PRMetrics:
    """從 dict 還原 PRMetrics。"""
    return PRMetrics(
        repo=d["repo"],
        pr_number=d["pr_number"],
        title=d["title"],
        jira_keys=d["jira_keys"],
        created_at=datetime.fromisoformat(d["created_at"]),
        first_review_at=datetime.fromisoformat(d["first_review_at"]) if d["first_review_at"] else None,
        merged_at=datetime.fromisoformat(d["merged_at"]) if d["merged_at"] else None,
        lines_added=d["lines_added"],
        lines_deleted=d["lines_deleted"],
        is_large=d["is_large"],
    )


def load_prs_cache() -> dict[str, dict]:
    """載入 PR cache，回傳 {repo#pr_number: serialized_dict}。檔案不存在時回傳 {}。"""
    if not PR_CACHE_PATH.exists():
        return {}
    with PR_CACHE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_prs_cache(cache: dict[str, dict]) -> None:
    """將 PR cache 寫入 data/cache/prs.json。"""
    PR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PR_CACHE_PATH.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")
    logger.info("已寫入 PR cache: %s（%d 筆）", PR_CACHE_PATH, len(cache))


def main() -> None:
    """主程式進入點。"""
    config_path = PROJECT_ROOT / "config.yaml"

    if not config_path.exists():
        logger.error("找不到 config.yaml: %s", config_path)
        sys.exit(1)

    logger.info("載入設定檔: %s", config_path)
    config = load_config(config_path)

    collection_config = config.get("collection", {})
    lookback_days = collection_config.get("lookback_days", 180)
    overlap_hours = collection_config.get("incremental_overlap_hours", 25)
    force_full = os.environ.get("FORCE_FULL_REFRESH", "false").lower() == "true"
    force_jira = force_full or os.environ.get("FORCE_JIRA_REFRESH", "false").lower() == "true"
    force_pr = force_full or os.environ.get("FORCE_PR_REFRESH", "false").lower() == "true"
    now = datetime.now(timezone.utc)

    # ── Jira 資料收集（增量或全量）──────────────────────────────────────────
    cache = {} if force_jira else load_issues_cache()

    if cache:
        logger.info("增量模式：抓取最近 %d 小時內有更新的 issue", overlap_hours)
        updated_issues = collect_jira(config, since_hours=overlap_hours)
        logger.info("增量收集完成，共 %d 筆更新", len(updated_issues))

        # 用最新資料覆蓋 cache 中的舊版本
        for issue in updated_issues:
            cache[issue.key] = _serialize_issue(issue)

        # 清除超過 lookback_days 的 issue
        cutoff = now - timedelta(days=lookback_days)
        before_evict = len(cache)
        cache = {
            k: v for k, v in cache.items()
            if datetime.fromisoformat(v["created"]) >= cutoff
        }
        evicted = before_evict - len(cache)
        if evicted:
            logger.info("清除 %d 筆逾期 issue（cutoff: %s）", evicted, cutoff.date())

        logger.info("cache 合併後共 %d 筆 issue", len(cache))
    else:
        mode = "強制 Jira 全量" if force_jira else "首次執行（無 cache）"
        logger.info("%s：收集 %d 天內的 issue", mode, lookback_days)
        all_issues = collect_jira(config)
        logger.info("全量收集完成，共 %d 筆", len(all_issues))
        cache = {issue.key: _serialize_issue(issue) for issue in all_issues}

    # ── 用最新 status mapping 重算 phase_durations ──────────────────────────
    remapped = 0
    unmapped_report: dict[str, set[str]] = {}  # status → set of project keys

    for data in cache.values():
        transitions = data.get("status_transitions", [])
        if not transitions:
            continue
        project = data["project"]
        lookup = build_status_lookup(config, project)
        status_changes = [
            (parse_jira_datetime(t["timestamp"]), t["from_status"], t["to_status"])
            for t in transitions
        ]
        created = datetime.fromisoformat(data["created"])
        resolved = datetime.fromisoformat(data["resolved"]) if data["resolved"] else None
        local_unmapped: set[str] = set()
        data["phase_durations"] = compute_phase_durations(
            status_changes, lookup, created, resolved or now,
            unmapped_collector=local_unmapped,
        )
        for status in local_unmapped:
            unmapped_report.setdefault(status, set()).add(project)
        remapped += 1

    if remapped:
        logger.info("已用最新 status mapping 重算 %d 筆 issue 的 phase_durations", remapped)

    old_format = len(cache) - remapped
    if old_format > 0:
        logger.warning(
            "%d 筆 cache issue 無 status_transitions（舊格式），建議執行 FORCE_JIRA_REFRESH=true 補齊",
            old_format,
        )

    if unmapped_report:
        lines = ["以下 Jira 狀態未對應到任何 phase（計入 unmapped）："]
        for status, projects in sorted(unmapped_report.items()):
            proj_str = "、".join(sorted(projects))
            lines.append(f"  - '{status}'（出現在 {proj_str}）")
        lines.append("請更新 config.yaml 的 status_mapping，下次 run 將自動重算。")
        logger.warning("\n".join(lines))

    save_issues_cache(cache)
    jira_data = [_deserialize_issue(v) for v in cache.values()]
    logger.info("Jira 資料準備完成，共 %d 筆", len(jira_data))

    # ── GitHub PR 資料收集（增量或全量）─────────────────────────────────────
    pr_cache = {} if force_pr else load_prs_cache()

    if pr_cache:
        logger.info("PR 增量模式：抓取最近 %d 小時內有更新的 PR", overlap_hours)
        updated_prs = collect_github_prs(config, since_hours=overlap_hours)
        logger.info("PR 增量收集完成，共 %d 筆更新", len(updated_prs))

        for pr in updated_prs:
            key = f"{pr.repo}#{pr.pr_number}"
            pr_cache[key] = _serialize_pr(pr)

        # 清除超過 lookback_days 的 PR（以 merged_at 為準）
        pr_cutoff = now - timedelta(days=lookback_days)
        before_evict = len(pr_cache)
        pr_cache = {
            k: v for k, v in pr_cache.items()
            if v.get("merged_at") and datetime.fromisoformat(v["merged_at"]) >= pr_cutoff
        }
        evicted = before_evict - len(pr_cache)
        if evicted:
            logger.info("清除 %d 筆逾期 PR（cutoff: %s）", evicted, pr_cutoff.date())

        logger.info("PR cache 合併後共 %d 筆", len(pr_cache))
    else:
        mode = "強制 PR 全量" if force_pr else "首次執行（無 PR cache）"
        logger.info("%s：收集 %d 天內的 merged PR", mode, lookback_days)
        all_prs = collect_github_prs(config)
        logger.info("PR 全量收集完成，共 %d 筆", len(all_prs))
        pr_cache = {f"{pr.repo}#{pr.pr_number}": _serialize_pr(pr) for pr in all_prs}

    save_prs_cache(pr_cache)
    github_data = [_deserialize_pr(v) for v in pr_cache.values()]
    logger.info("GitHub PR 資料準備完成，共 %d 筆", len(github_data))

    # ── Jenkins 資料收集──────────────────────────────────────────────────────
    logger.info("開始收集 Jenkins 建置資料")
    jenkins_data = collect_jenkins_builds(config)
    logger.info("Jenkins 建置資料收集完成，共 %d 筆", len(jenkins_data))

    logger.info("開始聚合資料")
    dashboard = aggregate(config, jira_data, github_data=github_data, jenkins_data=jenkins_data)
    logger.info("資料聚合完成")

    write_dashboard_json(dashboard, now)
    logger.info("資料管線執行完成")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("資料管線執行失敗: %s", e)
        sys.exit(1)
