---
name: jira-status-mapping
description: >
  將各 Jira 專案中多樣化的 workflow status 名稱正規化對應到標準的 cycle time phases
  （backlog、planning、dev、review、dev_test、qa、staging、done），橫跨多個專案與團隊。
  當使用者提到 Jira status mapping、cycle time phases、workflow 正規化、status-to-phase
  設定、unmapped statuses、新增 Jira 專案到 dashboard、或是要稽核／更新 config.yaml 中的
  status_mapping 時，請使用此 skill。也適用於使用者貼上 Jira status 名稱、changelog 資料、
  或詢問「這個 status 屬於哪個 phase」的情境。此 skill 涵蓋約 36 個 Jira 專案，
  18 個團隊各自有不一致的 workflow 命名慣例。
---

# Jira Status → Cycle Time Phase 對應

## 目的

KKDay 的 18 個工程團隊使用約 36 個 Jira 專案，每個專案可能有不同的 workflow status
名稱（英文、中文、縮寫、團隊自訂慣例）。此 skill 將所有 status 正規化為 8 個標準
phase，用於 cycle time 分析。

## 8 個標準 Phase

| Phase ID   | 標籤        | 說明                                 |
|------------|-------------|--------------------------------------|
| backlog    | Backlog     | 尚未開始處理                         |
| planning   | SA/SD       | 系統分析與設計                       |
| dev        | Development | 開發中（寫程式）                     |
| review     | PR Review   | Code review 進行中                   |
| dev_test   | RD Testing  | 開發端測試                           |
| qa         | QA Testing  | QA 團隊測試                          |
| staging    | Staging     | Stage 環境 / UAT / 回歸測試         |
| done       | Done        | 已上線至 production                  |

這些 phase 是**有序的**。Cycle time 從 issue 首次進入 `planning` 開始計算，
直到進入 `done` 為止。

## Config 結構

Status mapping 存放在 `config.yaml` 的 `status_mapping` 區段。結構如下：

```yaml
status_mapping:
  default:
    <phase_id>:
      - "Status 名稱 A"
      - "Status 名稱 B"
  overrides:
    <JIRA_PROJECT_KEY>:
      <phase_id>:
        - "該專案專屬的 Status 名稱"
```

**解析規則：**
1. 先查詢該 issue 的專案 key 是否在 `overrides` 中
2. 若該專案對某個 phase 有 override，使用 override 的清單
3. 否則 fallback 到 `default`
4. 若某個 status 完全無法匹配 → 標記為 `unmapped`

## 工作流程：新增專案

當使用者要將新的 Jira 專案加入 dashboard 時：

1. **取得該專案的 workflow statuses**
   - 透過 Jira API：`GET /rest/api/3/project/{projectKey}/statuses`
   - 或請使用者直接貼上 status 清單

2. **將每個 status 分類到對應的 phase**
   - 先用模糊比對對照 default mapping
   - 遇到模糊不清的 status，**詢問使用者**，不要自行猜測
   - 常見的模糊情境：
     - "In Progress" 在某些團隊代表 dev，在某些團隊代表 planning
     - "Review" 可能是 code review 也可能是 QA review
     - "Testing" 可能是 dev_test 也可能是 qa
     - "Ready for X" 類型的 status 是過渡狀態 — 通常歸屬於**下一個** phase 的前一步
       （例如 "Ready for QA" → 仍屬於 `dev_test` 或 `review`，不是 `qa`）
     - "Reopened" → 視為回到 `dev`

3. **決定用 default 還是 override**
   - 如果 status 名稱已經存在於 default 中 → 不需要 override
   - 如果只有 1-2 個 status 不同 → 只針對那些 phase 加最小的 override
   - 如果整個 workflow 差異很大 → 加一個完整的 override block
   - **絕對不要**把專案特有的 status 名稱塞進 default 清單

4. **更新 config.yaml**
   - 加上 override block（如果需要）
   - 把該專案加到對應團隊的 `jira_projects` 清單中

5. **驗證**
   - 執行 `python scripts/validate_mapping.py`（參見 scripts/）
   - 檢查：unmapped statuses、重複項目、沒有任何 status 的 phase

## 工作流程：稽核現有 Mapping

當使用者要檢查 mapping 是否正確或完整時：

1. **執行稽核腳本**
   ```bash
   python scripts/audit_statuses.py --config config.yaml
   ```
   此腳本會從 Jira API 拉取實際 statuses，與 config 交叉比對。

2. **檢視輸出結果**，包含：
   - ✅ 已對應：status → phase
   - ⚠️ 未對應：存在於 Jira 但不在 config 中
   - 🗑️ 過時項目：在 config 中但 Jira 已不再使用

3. **針對每個未對應的 status**，依照上述規則進行分類

## 對應啟發式規則

遇到不熟悉的 status 名稱時，使用以下關鍵字判斷：

**關鍵字 → Phase 對照：**
- `backlog`：「to do」「backlog」「pending」「open」「待處理」「awaiting」「new」
- `planning`：「analysis」「sa」「sd」「design」「planning」「規劃」「需求」
  「requirement」「spec」「refinement」「grooming」
- `dev`：「progress」「development」「developing」「coding」「開發」
  「implementation」「in dev」
- `review`：「review」「pr」「code review」「peer review」「審查」
- `dev_test`：「dev test」「rd test」「開發測試」「rd 測試」「unit test」
- `qa`：「qa」「quality」「qa 測試」「testing」（當上下文是 QA 團隊時）
- `staging`：「staging」「stage」「regression」「uat」「pre-prod」「驗證」
- `done`：「done」「released」「closed」「已完成」「已上線」「resolved」
  「production」「deployed」

**模糊情境處理：**
- 單獨出現 "Testing" → 詢問是哪個團隊負責（dev 還是 QA？）
- "Ready for X" → 歸屬於 X 的**前一個** phase
- "Blocked" / "On Hold" → 不是 phase；這段時間應另外追蹤為浪費（waste）。
  在 mapping 上保留在被 block 前的 phase。記錄警告。
- "Cancelled" / "Won't Do" → 完全排除在 cycle time 計算之外

## Cycle Time 計算的邊界案例

這些不是 mapping 決策本身，但會影響 mapped 資料的使用方式：

- **逆向流轉**（例如 QA → Dev）：計算每次進入某 phase 的時間並加總。
  這對於量測 rework 很重要。
- **跳過的 phase**：有些 issue 直接從 dev 跳到 done（hotfix）。
  這是正常的 — 被跳過的 phase 時間為 0。
- **接近零的 duration**：可能是批次拖拉 status（回溯性更新），也可能是真正快速的任務。
  若超過 3 個 phase 的 duration 都 < 5 分鐘，標記為可能是回溯操作。
  詳見 `references/near-zero-detection.md`。

## 腳本

- `scripts/validate_mapping.py` — 驗證 config.yaml：檢查 unmapped statuses、
  重複項目、空的 phase。每次修改 config 後都要執行。
- `scripts/audit_statuses.py` — 從 Jira API 拉取實際 statuses，與 config 比對，
  回報差異。需要設定環境變數 JIRA_BASE_URL、JIRA_EMAIL、JIRA_API_TOKEN。
- `scripts/suggest_mapping.py` — 輸入 status 名稱（stdin 或參數），
  使用關鍵字啟發式規則建議 phase 分類。互動模式下會對模糊項目詢問確認。

## 參考文件

- `references/near-zero-detection.md` — 如何偵測與處理回溯性批次拖拉的 issue
  （造成假的接近零 cycle time）
- `references/common-statuses.md` — 所有 36 個專案已知的 Jira status 名稱總表
  及其目前的 phase 對應（活文件）
