"""collect_github.py — GitHub PR 資料收集

從 GitHub API 收集各 team repos 的 PR 指標：
- pickup time（從 PR 開啟到第一個非作者 review 的時間）
- merge time（從 PR 開啟到 merge 的時間）
- PR 大小（lines changed）

需要環境變數：GITHUB_TOKEN
"""

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PRMetrics:
    """單一 PR 的原始指標。"""

    repo: str
    pr_number: int
    title: str
    jira_keys: list[str]
    created_at: datetime
    first_review_at: Optional[datetime]  # None 表示無人 review
    merged_at: Optional[datetime]
    lines_added: int
    lines_deleted: int
    is_large: bool


def _extract_jira_keys(text: str, pattern: str) -> list[str]:
    """從文字中提取 Jira issue key（如 PROJ-123）。"""
    return re.findall(pattern, text, re.IGNORECASE)


def _get_first_review_time(pr, author_login: str) -> Optional[datetime]:
    """取得第一個非作者 review 的提交時間。"""
    try:
        for review in pr.get_reviews():
            if review.user and review.user.login != author_login:
                submitted = review.submitted_at
                if submitted.tzinfo is None:
                    submitted = submitted.replace(tzinfo=timezone.utc)
                return submitted
    except Exception as exc:
        logger.warning("無法取得 PR #%d reviews: %s", pr.number, exc)
    return None


def collect_github_prs(config: dict, since_hours: Optional[int] = None) -> list[PRMetrics]:
    """從 GitHub 收集所有 team repos 的 merged PR 指標。

    若未設定 GITHUB_TOKEN 則回傳空列表（不中斷管線）。

    Args:
        config: 完整 config.yaml 內容
        since_hours: 若指定，只收集最近 N 小時內有更新的 PR（增量模式）。
                     None 表示全量模式，收集 lookback_days 天內的所有 merged PR。

    Returns:
        PRMetrics 列表
    """
    try:
        from github import Github, GithubException
    except ImportError:
        logger.warning("PyGithub 未安裝，跳過 GitHub 資料收集")
        return []

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.warning("未設定 GITHUB_TOKEN，跳過 GitHub 資料收集")
        return []

    github_config = config.get("github", {})
    org = github_config.get("org", "")
    if not org:
        logger.warning("未設定 github.org，跳過 GitHub 資料收集")
        return []

    collection_config = config.get("collection", {})
    lookback_days = collection_config.get("lookback_days", 90)
    api_delay = collection_config.get("github_api_delay_seconds", 0.1)
    jira_pattern = collection_config.get("pr_issue_pattern", r"([A-Z][A-Z0-9]+-\d+)")

    large_pr_threshold = config.get("dashboard", {}).get("large_pr_threshold", 400)
    if since_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    gh = Github(token)
    results: list[PRMetrics] = []

    for team in config.get("teams", []):
        for repo_name in team.get("github_repos", []):
            full_name = f"{org}/{repo_name}"
            try:
                repo = gh.get_repo(full_name)
                prs = repo.get_pulls(state="closed", sort="updated", direction="desc")

                for pr in prs:
                    updated = pr.updated_at
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=timezone.utc)
                    if updated < cutoff:
                        break  # 已按 updated 降冪排序，後面更舊可直接跳出

                    if not pr.merged_at:
                        continue  # 只看 merged PR

                    merged_at = pr.merged_at
                    if merged_at.tzinfo is None:
                        merged_at = merged_at.replace(tzinfo=timezone.utc)
                    if merged_at < cutoff:
                        continue

                    created_at = pr.created_at
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)

                    author = pr.user.login if pr.user else ""
                    first_review_at = _get_first_review_time(pr, author)

                    title_and_body = pr.title + " " + (pr.body or "")
                    jira_keys = list(set(_extract_jira_keys(title_and_body, jira_pattern)))

                    lines_changed = (pr.additions or 0) + (pr.deletions or 0)

                    results.append(
                        PRMetrics(
                            repo=repo_name,
                            pr_number=pr.number,
                            title=pr.title,
                            jira_keys=jira_keys,
                            created_at=created_at,
                            first_review_at=first_review_at,
                            merged_at=merged_at,
                            lines_added=pr.additions or 0,
                            lines_deleted=pr.deletions or 0,
                            is_large=lines_changed > large_pr_threshold,
                        )
                    )

                    time.sleep(api_delay)

            except Exception as exc:
                logger.error("收集 repo %s 失敗: %s", full_name, exc)
                continue

    logger.info("GitHub PR 收集完成，共 %d 筆", len(results))
    return results
