#!/usr/bin/env python3
"""
驗證 config.yaml 的 status mapping 完整性與一致性。

用法：
    python validate_mapping.py [--config path/to/config.yaml]

檢查項目：
    - 所有 8 個 phase 在 default mapping 中至少有一個 status
    - 同一 scope 內沒有重複的 status 名稱
    - Override block 只使用合法的 phase ID
    - Override 的 phase 清單不為空
    - 團隊引用的專案 key 都有對應的 mapping

Exit codes：
    0 = 所有檢查通過
    1 = 僅有警告（未指派的專案等）
    2 = 發現錯誤（重複、缺少 phase 等）
"""

import sys
import yaml
from pathlib import Path
from collections import defaultdict

VALID_PHASES = ["backlog", "planning", "dev", "review", "dev_test", "qa", "staging", "done"]

def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def validate(config: dict) -> tuple[list[str], list[str]]:
    """回傳 (errors, warnings)。"""
    errors = []
    warnings = []

    mapping = config.get("status_mapping", {})
    default = mapping.get("default", {})
    overrides = mapping.get("overrides", {})
    teams = config.get("teams", [])

    # 檢查 default 中是否包含所有 phase
    for phase in VALID_PHASES:
        statuses = default.get(phase, [])
        if not statuses:
            errors.append(f"Default mapping 缺少 phase：{phase}")

    # 檢查 default 中的重複項目
    all_default_statuses: dict[str, str] = {}
    for phase, statuses in default.items():
        if phase not in VALID_PHASES:
            errors.append(f"Default 中出現未知的 phase：'{phase}'")
            continue
        for status in (statuses or []):
            normalized = status.strip().lower()
            if normalized in all_default_statuses:
                errors.append(
                    f"Default 中有重複的 status '{status}'："
                    f"同時出現在 '{all_default_statuses[normalized]}' 和 '{phase}'"
                )
            all_default_statuses[normalized] = phase

    # 檢查 overrides
    for project_key, phases in (overrides or {}).items():
        for phase, statuses in phases.items():
            if phase not in VALID_PHASES:
                errors.append(f"Override '{project_key}' 包含未知的 phase：'{phase}'")
            if not statuses:
                warnings.append(f"Override '{project_key}.{phase}' 的 status 清單為空")
            # 檢查 override 內部的重複
            override_statuses: dict[str, str] = {}
            for status in (statuses or []):
                normalized = status.strip().lower()
                if normalized in override_statuses:
                    errors.append(
                        f"Override '{project_key}' 中有重複："
                        f"'{status}' 在 '{phase}' 中出現多次"
                    )
                override_statuses[normalized] = phase

    # 檢查團隊的專案引用
    all_override_projects = set(overrides.keys()) if overrides else set()
    all_team_projects = set()
    for team in teams:
        for proj in team.get("jira_projects", []):
            all_team_projects.add(proj)

    # 有 override 但沒有被任何團隊認領的專案
    orphan_overrides = all_override_projects - all_team_projects
    for proj in orphan_overrides:
        warnings.append(f"專案 '{proj}' 有 override 設定但沒有任何團隊擁有此專案")

    return errors, warnings

def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"

    if not Path(config_path).exists():
        print(f"❌ 找不到設定檔：{config_path}")
        sys.exit(2)

    config = load_config(config_path)
    errors, warnings = validate(config)

    if warnings:
        print(f"\n⚠️  {len(warnings)} 個警告：")
        for w in warnings:
            print(f"   ⚠️  {w}")

    if errors:
        print(f"\n❌ {len(errors)} 個錯誤：")
        for e in errors:
            print(f"   ❌ {e}")
        sys.exit(2)

    if warnings:
        print(f"\n✅ 沒有錯誤。有 {len(warnings)} 個警告需要檢視。")
        sys.exit(1)

    print("\n✅ 所有檢查通過。")
    sys.exit(0)

if __name__ == "__main__":
    main()
