"""main.py — 資料管線協調器

讀取 config.yaml，執行資料收集與聚合，寫入 dashboard.json。
不含業務邏輯，只負責協調各模組。
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from aggregate import aggregate
from collect_github import collect_github_prs
from collect_jenkins import collect_jenkins_builds
from collect_jira import collect_jira

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

# 專案根目錄（main.py 的上一層）
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


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


def main() -> None:
    """主程式進入點。"""
    config_path = PROJECT_ROOT / "config.yaml"

    if not config_path.exists():
        logger.error("找不到 config.yaml: %s", config_path)
        sys.exit(1)

    logger.info("載入設定檔: %s", config_path)
    config = load_config(config_path)

    logger.info("開始收集 Jira 資料")
    jira_data = collect_jira(config)
    logger.info("Jira 資料收集完成，共 %d 筆", len(jira_data))

    logger.info("開始收集 GitHub PR 資料")
    github_data = collect_github_prs(config)
    logger.info("GitHub PR 資料收集完成，共 %d 筆", len(github_data))

    logger.info("開始收集 Jenkins 建置資料")
    jenkins_data = collect_jenkins_builds(config)
    logger.info("Jenkins 建置資料收集完成，共 %d 筆", len(jenkins_data))

    logger.info("開始聚合資料")
    dashboard = aggregate(config, jira_data, github_data=github_data, jenkins_data=jenkins_data)
    logger.info("資料聚合完成")

    now = datetime.now(timezone.utc)
    write_dashboard_json(dashboard, now)
    logger.info("資料管線執行完成")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("資料管線執行失敗: %s", e)
        sys.exit(1)
