#!/usr/bin/env python3
"""
稽核 Jira statuses 與 config.yaml mapping 的差異。

從 Jira API 拉取各專案實際使用的 workflow statuses，
與設定檔交叉比對，找出缺口。

用法：
    python audit_statuses.py --config config.yaml

需要環境變數：JIRA_BASE_URL、JIRA_EMAIL、JIRA_API_TOKEN

輸出：
    針對每個專案：
    - ✅ 已對應：status → phase
    - ⚠️  未對應：存在於 Jira 但不在 config 中
    - 🗑️  過時：在 config 中但 Jira 已不再使用
"""

import os
import sys
import json
import yaml
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from base64 import b64encode

def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def jira_request(path: str, base_url: str, auth_header: str) -> dict:
    """發送已認證的 Jira API 請求。"""
    url = f"{base_url.rstrip('/')}{path}"
    req = Request(url, headers={
        "Authorization": auth_header,
        "Accept": "application/json",
    })
    time.sleep(0.3)  # 尊重 rate limit
    with urlopen(req) as resp:
        return json.loads(resp.read())

def get_project_statuses(project_key: str, base_url: str, auth_header: str) -> list[str]:
    """取得某 Jira 專案的所有 workflow statuses。"""
    try:
        data = jira_request(f"/rest/api/3/project/{project_key}/statuses", base_url, auth_header)
        statuses = set()
        for issue_type in data:
            for status in issue_type.get("statuses", []):
                statuses.add(status["name"])
        return sorted(statuses)
    except HTTPError as e:
        print(f"   ❌ 無法取得 {project_key} 的 statuses：{e.code} {e.reason}")
        return []

def resolve_mapping_for_project(project_key: str, config: dict) -> dict[str, str]:
    """建立某專案的 status→phase 查詢表，含 override 解析。"""
    mapping = config.get("status_mapping", {})
    default = mapping.get("default", {})
    overrides = mapping.get("overrides", {})
    project_overrides = overrides.get(project_key, {}) if overrides else {}

    status_to_phase: dict[str, str] = {}

    for phase_id, statuses in default.items():
        # 若該專案＋phase 有 override 就用 override，否則用 default
        effective_statuses = project_overrides.get(phase_id, statuses) or []
        for status in effective_statuses:
            status_to_phase[status.strip().lower()] = phase_id

    return status_to_phase

def audit_project(project_key: str, live_statuses: list[str], config: dict) -> dict:
    """稽核單一專案。回傳 {mapped, unmapped, stale}。"""
    status_to_phase = resolve_mapping_for_project(project_key, config)

    mapped = {}
    unmapped = []
    live_normalized = set()

    for status in live_statuses:
        normalized = status.strip().lower()
        live_normalized.add(normalized)
        phase = status_to_phase.get(normalized)
        if phase:
            mapped[status] = phase
        else:
            unmapped.append(status)

    # 找出過時項目：在 config 中但 Jira 已不再使用
    stale = []
    for config_status, phase in status_to_phase.items():
        if config_status not in live_normalized:
            stale.append((config_status, phase))

    return {"mapped": mapped, "unmapped": unmapped, "stale": stale}

def main():
    config_path = "config.yaml"
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--config" and i < len(sys.argv) - 1:
            config_path = sys.argv[i + 1]

    base_url = os.environ.get("JIRA_BASE_URL", "")
    email = os.environ.get("JIRA_EMAIL", "")
    token = os.environ.get("JIRA_API_TOKEN", "")

    if not all([base_url, email, token]):
        print("❌ 缺少環境變數。請設定 JIRA_BASE_URL、JIRA_EMAIL、JIRA_API_TOKEN")
        sys.exit(1)

    auth = b64encode(f"{email}:{token}".encode()).decode()
    auth_header = f"Basic {auth}"

    config = load_config(config_path)
    teams = config.get("teams", [])

    all_projects = set()
    for team in teams:
        for proj in team.get("jira_projects", []):
            all_projects.add(proj)

    total_unmapped = 0
    total_stale = 0

    for project_key in sorted(all_projects):
        print(f"\n{'='*60}")
        print(f"📋 專案：{project_key}")
        print(f"{'='*60}")

        live_statuses = get_project_statuses(project_key, base_url, auth_header)
        if not live_statuses:
            continue

        result = audit_project(project_key, live_statuses, config)

        if result["mapped"]:
            print(f"\n  ✅ 已對應（{len(result['mapped'])} 個）：")
            for status, phase in sorted(result["mapped"].items(), key=lambda x: x[1]):
                print(f"     {status:<30} → {phase}")

        if result["unmapped"]:
            print(f"\n  ⚠️  未對應（{len(result['unmapped'])} 個）：")
            for status in result["unmapped"]:
                print(f"     {status}")
            total_unmapped += len(result["unmapped"])

        if result["stale"]:
            print(f"\n  🗑️  過時（{len(result['stale'])} 個）：")
            for status, phase in result["stale"]:
                print(f"     {status}（原屬 {phase}）")
            total_stale += len(result["stale"])

    print(f"\n{'='*60}")
    print(f"總結：已稽核 {len(all_projects)} 個專案")
    print(f"  ⚠️  未對應 statuses 總計：{total_unmapped}")
    print(f"  🗑️  過時項目總計：{total_stale}")
    if total_unmapped > 0:
        print(f"\n執行 `python scripts/suggest_mapping.py` 可取得未對應 statuses 的 phase 建議。")

if __name__ == "__main__":
    main()
