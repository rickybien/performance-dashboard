"""collect_jenkins.py — Jenkins 建置資料收集

從 Jenkins API 收集各 team 的 Jenkins job 建置指標：
- 建置結果（SUCCESS / FAILURE / UNSTABLE / ABORTED）
- 建置起始時間
- 建置持續時間

需要環境變數：JENKINS_USER, JENKINS_API_TOKEN
config.yaml 中 jenkins.enabled 必須為 true 才會執行。
"""

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


@dataclass
class BuildResult:
    """單一 Jenkins 建置的原始資料。"""

    job_name: str
    build_number: int
    result: Optional[str]  # SUCCESS, FAILURE, UNSTABLE, ABORTED，None 表示進行中
    duration_ms: int
    timestamp: datetime  # 建置起始時間


def _fetch_builds_for_job(
    base_url: str,
    job_name: str,
    auth: HTTPBasicAuth,
    cutoff: datetime,
    api_delay: float,
) -> list[BuildResult]:
    """從 Jenkins API 取得單一 job 的建置列表。

    Jenkins 回傳建置資料由新到舊，遇到比 cutoff 更早的建置即停止。
    """
    url = (
        f"{base_url.rstrip('/')}/job/{job_name}/api/json"
        f"?tree=builds[number,result,duration,timestamp]"
    )

    try:
        resp = requests.get(url, auth=auth, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("無法取得 Jenkins job %s 資料: %s", job_name, exc)
        return []

    time.sleep(api_delay)

    builds_raw = resp.json().get("builds", [])
    results: list[BuildResult] = []

    for b in builds_raw:
        ts_ms = b.get("timestamp", 0)
        if not ts_ms:
            continue

        build_time = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        if build_time < cutoff:
            break  # 已由新到舊排序，後面更舊可直接跳出

        results.append(
            BuildResult(
                job_name=job_name,
                build_number=b.get("number", 0),
                result=b.get("result"),  # None 表示建置進行中
                duration_ms=b.get("duration", 0),
                timestamp=build_time,
            )
        )

    return results


def collect_jenkins_builds(config: dict) -> list[BuildResult]:
    """從 Jenkins 收集所有 team jobs 的建置資料。

    若 jenkins.enabled = false 或缺少認證則回傳空列表（不中斷管線）。

    Args:
        config: 完整 config.yaml 內容

    Returns:
        BuildResult 列表
    """
    jenkins_config = config.get("jenkins", {})

    if not jenkins_config.get("enabled", False):
        logger.info("Jenkins 未啟用（jenkins.enabled = false），跳過建置資料收集")
        return []

    base_url = jenkins_config.get("base_url", "")
    if not base_url:
        logger.warning("未設定 jenkins.base_url，跳過 Jenkins 資料收集")
        return []

    user = os.environ.get("JENKINS_USER")
    token = os.environ.get("JENKINS_API_TOKEN")
    if not user or not token:
        logger.warning(
            "未設定 JENKINS_USER / JENKINS_API_TOKEN，跳過 Jenkins 資料收集"
        )
        return []

    auth = HTTPBasicAuth(user, token)

    collection_config = config.get("collection", {})
    lookback_days = collection_config.get("lookback_days", 90)
    api_delay = collection_config.get("api_delay_seconds", 0.5)

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    results: list[BuildResult] = []

    for team in config.get("teams", []):
        for job_name in team.get("jenkins_jobs", []):
            builds = _fetch_builds_for_job(base_url, job_name, auth, cutoff, api_delay)
            results.extend(builds)
            logger.info(
                "Jenkins job %s（team: %s）: 收集到 %d 筆建置",
                job_name,
                team.get("id", ""),
                len(builds),
            )

    logger.info("Jenkins 建置資料收集完成，共 %d 筆", len(results))
    return results
