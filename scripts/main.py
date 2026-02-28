"""main.py — 資料管線協調器

讀取 config.yaml，執行資料收集與聚合，寫入 dashboard.json。
不含業務邏輯，只負責協調各模組。

增量模式：若 data/cache/issues.json 存在且 FORCE_FULL_REFRESH != true，
只收集最近 incremental_overlap_hours 小時內有更新的 issue，與 cache 合併後聚合。
全量模式：cache 不存在或 FORCE_FULL_REFRESH=true 時，重新收集完整 lookback_days 天的資料。
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from aggregate import aggregate
from collect_github import collect_github_prs
from collect_jenkins import collect_jenkins_builds
from collect_jira import IssueMetrics, collect_jira

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
    now = datetime.now(timezone.utc)

    # ── Jira 資料收集（增量或全量）──────────────────────────────────────────
    cache = {} if force_full else load_issues_cache()

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
        mode = "強制全量" if force_full else "首次執行（無 cache）"
        logger.info("%s：收集 %d 天內的 issue", mode, lookback_days)
        all_issues = collect_jira(config)
        logger.info("全量收集完成，共 %d 筆", len(all_issues))
        cache = {issue.key: _serialize_issue(issue) for issue in all_issues}

    save_issues_cache(cache)
    jira_data = [_deserialize_issue(v) for v in cache.values()]
    logger.info("Jira 資料準備完成，共 %d 筆", len(jira_data))

    # ── GitHub / Jenkins 資料收集（維持原邏輯）──────────────────────────────
    logger.info("開始收集 GitHub PR 資料")
    github_data = collect_github_prs(config)
    logger.info("GitHub PR 資料收集完成，共 %d 筆", len(github_data))

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
