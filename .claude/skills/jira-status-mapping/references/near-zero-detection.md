# 接近零 Duration 偵測

## 問題描述

分析 cycle time 資料時，會遇到某些 issue 的多個 phase duration 接近零（< 5 分鐘）。
這通常代表以下兩種情境之一：

### 情境 A：回溯性批次拖拉

有人在同一時間把 issue 一口氣拖過多個 status 來「結案」。常見特徵：

- 3 個以上的 phase duration 都 < 5 分鐘
- 各次 transition 之間只隔幾秒鐘
- 通常發生在同一天，而且常在 sprint 結束時
- 最後一個 phase（通常是 `done`）可能有真實的 duration，
  因為那個人是在實際部署後才把它拖到 done

### 情境 B：真正快速的任務

小型 bug fix 或設定變更，確實快速通過各 phase。特徵：

- 總 cycle time 仍在合理範圍（小型修復 < 1 天）
- 通常只有 1-2 個 phase 接近零，不是全部
- 有對應的 PR 且確實被 review 過（即使很簡短）
- commit diff 很小但是真實的

## 偵測啟發式規則

當以下條件**全部成立**時，標記該 issue 為「可能是回溯操作」：

1. **3 個以上的 phase** duration < 5 分鐘
2. 從第一次到最後一次 transition 的**總經過時間** < 30 分鐘
3. **沒有對應的 PR**，或 PR 的 merge 時間早於 Jira transition 發生時間

## 被標記的 Issue 該怎麼處理

**不要刪除它們** — 它們代表的是確實完成的工作。

**可選方案：**
1. **從 cycle time 統計中排除** — 對報表準確度最安全
2. **只計算有真實 duration 的 phase** — 如果最後一個 phase 有意義的時間，
   那可能就是真正的工作階段
3. **在 dashboard 上標記** — 獨立顯示，讓工程主管可以和團隊討論

## Config 支援

在 `config.yaml` 中，pipeline 會參考以下設定：

```yaml
analysis:
  near_zero_threshold_minutes: 5
  near_zero_min_phases: 3        # 若有這麼多 phase 低於 threshold 則標記
  near_zero_max_elapsed_minutes: 30
  near_zero_action: "exclude"    # "exclude" | "flag" | "include"
```

## 預防措施

根本原因通常是團隊沒有即時更新 Jira。可以透過以下方式改善：

- 設定 Jira automation rules，根據 PR 事件自動 transition
  （例如建立 branch → In Progress，PR merge → In Review）
- 使用 GitHub → Jira 整合
- 在 sprint retrospective 中討論看板維護習慣
