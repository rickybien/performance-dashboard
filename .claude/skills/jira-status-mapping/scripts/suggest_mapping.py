#!/usr/bin/env python3
"""
使用關鍵字啟發式規則，為 Jira status 名稱建議 phase 分類。

用法：
    # 從參數輸入
    python suggest_mapping.py "In Progress" "Dev Testing" "Ready for QA"

    # 從 stdin 輸入（每行一個 status）
    echo -e "In Progress\nDev Testing" | python suggest_mapping.py

    # 互動模式
    python suggest_mapping.py --interactive

輸出：
    針對每個 status，印出建議的 phase 或「模糊」（若無法判斷）。
    互動模式下會對模糊項目詢問確認。
"""

import sys
import re

# 關鍵字 patterns，按特定程度排序（更特定的在前面）
PHASE_PATTERNS: list[tuple[str, list[str]]] = [
    ("done", [
        r"\bdone\b", r"\breleased\b", r"\bclosed\b", r"\bresolved\b",
        r"\b已完成\b", r"\b已上線\b", r"\bdeployed\b", r"\bproduction\b",
        r"\bshipped\b",
    ]),
    ("staging", [
        r"\bstag(?:ing|e)\b", r"\bregression\b", r"\buat\b",
        r"\bpre-?prod\b", r"\b驗證\b", r"\bstage\s*環境\b",
    ]),
    ("qa", [
        r"\bqa\b", r"\bquality\s*assurance\b", r"\bqa\s*test\b",
        r"\bqa\s*測試\b", r"\bin\s*qa\b",
    ]),
    ("dev_test", [
        r"\bdev\s*test\b", r"\brd\s*test\b", r"\b開發測試\b",
        r"\brd\s*測試\b", r"\bunit\s*test\b", r"\bdev\s*驗證\b",
    ]),
    ("review", [
        r"\breview\b", r"\bpr\b", r"\bcode\s*review\b",
        r"\bpeer\s*review\b", r"\b審查\b",
    ]),
    ("dev", [
        r"\bin\s*progress\b", r"\bdevelop(?:ing|ment)\b", r"\bcoding\b",
        r"\b開發中\b", r"\bimplementat(?:ing|ion)\b", r"\bin\s*dev\b",
    ]),
    ("planning", [
        r"\banalysis\b", r"\bsa\b", r"\bsd\b", r"\bdesign\b",
        r"\bplanning\b", r"\b規劃\b", r"\b需求\b", r"\brequirement\b",
        r"\bspec\b", r"\brefinement\b", r"\bgrooming\b",
    ]),
    ("backlog", [
        r"\bto\s*do\b", r"\bbacklog\b", r"\bpending\b", r"\bopen\b",
        r"\b待處理\b", r"\bawaiting\b", r"\bnew\b",
    ]),
]

# 不屬於 phase 的 status — 需另外標記
NON_PHASE_PATTERNS = [
    (r"\bblocked\b", "BLOCKED — 追蹤為浪費，保留在前一個 phase"),
    (r"\bon\s*hold\b", "ON HOLD — 追蹤為浪費，保留在前一個 phase"),
    (r"\bcancelled\b", "CANCELLED — 排除在 cycle time 計算之外"),
    (r"\bwon'?t\s*(do|fix)\b", "WON'T DO — 排除在 cycle time 計算之外"),
    (r"\bduplicate\b", "DUPLICATE — 排除在 cycle time 計算之外"),
]

def suggest_phase(status: str) -> tuple[str, float]:
    """
    為 status 名稱建議 phase。
    回傳 (phase_或_標籤, 信心度)，信心度為 0.0-1.0。
    """
    normalized = status.strip().lower()

    # 先檢查非 phase 的 patterns
    for pattern, label in NON_PHASE_PATTERNS:
        if re.search(pattern, normalized):
            return label, 0.9

    # 檢查 "Ready for X" pattern — 歸屬於 X 的前一個 phase
    ready_match = re.search(r"ready\s+for\s+(.+)", normalized)
    if ready_match:
        target = ready_match.group(1).strip()
        for phase, patterns in PHASE_PATTERNS:
            for p in patterns:
                if re.search(p, target):
                    phase_order = [pid for pid, _ in PHASE_PATTERNS]
                    idx = phase_order.index(phase)
                    if idx < len(phase_order) - 1:
                        prev_phase = phase_order[idx + 1]  # 清單是反序的
                        return f"{prev_phase}（Ready for {phase}）", 0.7
        return "模糊（Ready for ?）", 0.3

    # 正常比對
    matches = []
    for phase, patterns in PHASE_PATTERNS:
        for p in patterns:
            if re.search(p, normalized):
                matches.append(phase)
                break

    if len(matches) == 1:
        return matches[0], 0.9
    elif len(matches) > 1:
        return f"模糊（{' 或 '.join(set(matches))}）", 0.3
    else:
        return "未知", 0.0

def interactive_mode():
    """互動模式：逐一分類並確認。"""
    print("請輸入 Jira status 名稱（每行一個，空行結束）：\n")
    results = []

    while True:
        try:
            status = input("> ").strip()
        except EOFError:
            break
        if not status:
            break

        suggestion, confidence = suggest_phase(status)

        if confidence >= 0.7:
            print(f"  → {suggestion}（信心度：{confidence:.0%}）")
            confirm = input("  接受？[Y/n] ").strip().lower()
            if confirm in ("", "y", "yes"):
                results.append((status, suggestion))
            else:
                manual = input(f"  請輸入 phase（{', '.join(p for p, _ in PHASE_PATTERNS)}）：").strip()
                results.append((status, manual))
        else:
            print(f"  → {suggestion}")
            manual = input(f"  請手動分類（{', '.join(p for p, _ in PHASE_PATTERNS)}）：").strip()
            results.append((status, manual))

    if results:
        print("\n" + "=" * 50)
        print("結果：")
        print("=" * 50)
        for status, phase in results:
            print(f"  {status:<30} → {phase}")

        # 輸出 YAML snippet
        print("\n# 可貼入 config.yaml 的 YAML 片段：")
        by_phase: dict[str, list[str]] = {}
        for status, phase in results:
            clean_phase = phase.split("（")[0].strip().split(" ")[0]
            by_phase.setdefault(clean_phase, []).append(status)
        for phase, statuses in by_phase.items():
            print(f"    {phase}:")
            for s in statuses:
                print(f'      - "{s}"')

def main():
    if "--interactive" in sys.argv:
        interactive_mode()
        return

    # 從參數或 stdin 讀取 statuses
    statuses = []
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        statuses = args
    else:
        statuses = [line.strip() for line in sys.stdin if line.strip()]

    if not statuses:
        print("用法：python suggest_mapping.py [--interactive] [status1] [status2] ...")
        print("      echo 'status' | python suggest_mapping.py")
        sys.exit(1)

    for status in statuses:
        suggestion, confidence = suggest_phase(status)
        marker = "✅" if confidence >= 0.7 else ("⚠️ " if confidence >= 0.3 else "❓")
        print(f"  {marker} {status:<30} → {suggestion}")

if __name__ == "__main__":
    main()
