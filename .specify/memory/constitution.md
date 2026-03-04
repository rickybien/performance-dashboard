<!-- Sync Impact Report
版本變更：1.0.0 → 1.1.0
修訂原因：新增原則 VII（TDD）。

新增原則（1 個）：
  - VII. 測試驅動開發（Test-Driven Development，非協商）

修改章節：
  - Governance：原則數量從 6 更新為 7

範本一致性檢查：
  - .specify/templates/plan-template.md  ✅ 相容（Constitution Check 欄位已存在）
  - .specify/templates/spec-template.md  ✅ 相容（無原則特定衝突）
  - .specify/templates/tasks-template.md ✅ 已更新（「Tests are OPTIONAL」改為與 TDD 一致的強制措辭）

延遲項目（TODO）：無。
-->

# Engineering Metrics Dashboard 工程憲法

## 核心原則

### I. 靜態優先（Static-First）

前端 MUST 只讀取預聚合的靜態 JSON，禁止在瀏覽器中發起任何即時 API call。
所有計算 MUST 在 Python pipeline 完成並寫入 `data/latest/dashboard.json`。
dashboard.json 總大小 MUST 維持在 1 MB 以下，確保頁面載入速度。
前端資料取得 MUST 透過 `useMetrics()` composable，採模組級 cache，SPA 生命週期內僅 fetch 一次。

**原因**：靜態部署於 GitHub Pages，零後端維運成本；24 小時更新精度已足夠工程指標使用場景。

### II. config.yaml 為唯一真相來源（Single Source of Truth）

所有 team↔project↔repo↔Jira status 對應關係 MUST 定義在 `config.yaml`，
禁止硬碼於任何 Python 或 JavaScript 檔案。
修改 config.yaml 後，重新執行 pipeline 即可生效，無需改動程式碼。
status_mapping override 語義 MUST 為「完全取代」（非疊加）：
若 project 有 override 某 phase，則該 phase 的 default 映射全部失效，僅保留 override 清單。

**原因**：18 個團隊、36 個 Jira 專案各有不同的 workflow 命名慣例；集中管理才能安全修改而不影響程式邏輯。

### III. 百分位數，非平均值（Percentiles Over Averages）

Cycle time 報告 MUST 呈現 p50（中位數）、p75、p90。
禁止以 mean/average 作為主要 cycle time 指標，因為離群值會嚴重扭曲平均值。
前端顯示 MUST 優先使用 `filtered.p50`（pass-through filter 後），
若 `filtered.count` 為 0 則 fallback 至原始 `p50`。
Pass-through filter 門檻（`filter_threshold_hours`）MUST 可透過 config.yaml 調整，預設值 1.0 小時。

**原因**：p50 代表典型工程師體驗；在 B2B/ROB 回溯批次拖票場景下，平均值完全失去意義。

### IV. 漸進式容錯（Graceful Degradation）

任何單一資料來源（Jira、GitHub、Jenkins）失敗時，pipeline MUST 繼續執行其餘部分並記錄錯誤日誌。
無 GitHub token、Jenkins 停用、或 API 呼叫失敗時，對應欄位 MUST 設為 null 或空陣列，
而非拋出未處理例外導致 pipeline 崩潰。
Jenkins circuit breaker：連續 3 次 job 連線失敗後 MUST 跳過所有剩餘 jobs。
Jira API 分頁錯誤 MUST 記錄已收集資料後繼續進行聚合，而非清空結果。

**原因**：pipeline 運行於 GitHub Actions 定時任務（UTC 18:00），任何未處理例外會導致整日資料遺失，
且無人工監控即時介入。

### V. 聚合邏輯測試覆蓋（Tested Aggregation Logic）

`aggregate.py` 是系統核心（~1000 行），其所有公開函式和邊界情況 MUST 有 pytest 測試覆蓋。
新增或修改聚合邏輯時，MUST 同步新增對應測試，並確認全部既有測試通過，才可提交。
前端元件的關鍵顯示邏輯（filtered p50 優先、色階判斷、cellTitle 資訊）SHOULD 有 vitest 單元測試。
測試執行指令：
- Python：`cd scripts && uv run --with jira --with pyyaml --with python-dateutil --with pytest --with PyGithub pytest tests/ -v`
- 前端：`cd frontend && npm test`

**原因**：SA/SD 合併、pass-through 過濾、windowed 聚合等邏輯互相依賴且具有邊界案例，
測試是唯一可靠的正確性保證。

### VII. 測試驅動開發（Test-Driven Development，非協商）

開發新功能或修改現有邏輯時，MUST 遵循 Red-Green-Refactor 循環：

1. **Red**：先撰寫能明確描述預期行為的測試，確認測試目前**失敗**
2. **Green**：撰寫最少量的程式碼使測試通過
3. **Refactor**：在測試保護下重構，確保所有測試仍然通過

測試 MUST 在實作程式碼之前撰寫，禁止先實作再補測試。
Python 聚合與收集邏輯（`aggregate.py`、`collect_*.py`）MUST 嚴格遵循 TDD。
前端元件關鍵顯示邏輯（色階判斷、filtered p50 選擇）SHOULD 遵循 TDD（vitest）。
提交前 MUST 執行全部測試並確認通過，禁止在 CI 中跳過測試步驟。

**原因**：TDD 迫使在實作前釐清需求與邊界案例，並在開發過程中維持測試作為安全網。
`aggregate.py` 的複雜邏輯（SA/SD 合併、pass-through 過濾、windowed 聚合）尤其受益於此流程，
可防止因局部修改而引入難以察覺的回歸錯誤。

### VI. 向後相容的 Schema 演進（Backward-Compatible Schema Evolution）

`dashboard.json` 輸出 schema 演進 MUST 向後相容：可新增欄位，但禁止移除或重命名現有欄位。
收集器 dataclass 新增欄位時，序列化/反序列化 MUST 使用 `.get()` 預設值確保 cache 向後相容。
移除欄位時，MUST 先確認前端程式碼已完全不再讀取，且需在 commit 訊息中明確說明。

**原因**：dashboard.json 由 CI 每日更新，前端從 GitHub Pages 讀取；
兩者部署週期不同步，schema 破壞性變更會導致前端白畫面或 JavaScript 例外。

## 技術限制與規範

- **Python 執行環境**：Python 3.12+，一律使用 `uv` 執行腳本與管理依賴，禁止直接呼叫 `python`。
- **前端框架**：Vue 3 Composition API（`<script setup>` 語法），禁止 Options API。
- **路由**：vue-router hash history，確保 GitHub Pages 靜態部署相容性。
- **Vite base**：固定為 `/performance-dashboard/`，禁止修改（對應 GitHub Pages 子路徑）。
- **Secrets 管理**：所有 API 金鑰 MUST 存放於 GitHub Secrets，禁止硬碼於程式碼或 config.yaml。
- **API 速率限制**：Jira search 頁間延遲 0.5 秒、changelog 每 issue 延遲 0.1 秒、GitHub API 呼叫延遲 0.1 秒。
- **Commit 訊息**：使用繁體中文描述，遵循 Conventional Commits 格式（`feat:`、`fix:`、`chore:`、`docs:`）。
- **檔案大小原則**：每個模組保持小而聚焦，一個 collector 對應一個資料來源。
- **型別標註**：Python 程式碼 MUST 使用 type hints；Vue 元件使用 `<script setup>` 隱含型別。

## 開發工作流程

每次改動程式邏輯後，MUST 同步更新 `PROJECT_SPEC.md` 對應章節：

| 變更類型 | 需更新的章節 |
|---------|------------|
| 新增/修改 dataclass 欄位 | §5 資料管線規格 |
| 變更 dashboard.json 輸出結構 | §6 輸出 Schema |
| 新增/修改前端元件或頁面 | §7 前端規格 |
| 修改 CI/CD workflow | §8 CI/CD 流程 |
| 新增/修改 config.yaml 欄位 | §4 config.yaml 規格 |
| 測試數量變更 | §9 測試策略 |
| 純重構（輸出不變）或純文件修改 | 不需更新 |

**重跑 Pipeline 判斷原則**（避免機械式詢問，根據變更判斷後主動說明）：
- **需要重跑**（主動建議）：aggregate.py 輸出結構變更、collector 邏輯變更、config 映射變更
- **不需要重跑**：純前端 UI 變更、測試修改、文件更新、重構但輸出不變

**增量模式**（pipeline 預設行為）：
使用 `data/cache/` 增量更新，以 `incremental_overlap_hours`（預設 25h）時間窗避免漏更新，
重跑時可透過環境變數 `FORCE_FULL_REFRESH=true` 強制全量。

## Governance

本憲法是本專案所有開發決策的最高指導原則。
任何功能設計若與憲法原則衝突，MUST 以憲法為準，或先提案修訂憲法後再實作。

**修訂程序**：
1. 說明現有原則為何不再適用或需要擴充
2. 更新 `constitution.md`，遞增版本號（見下方規則）
3. 審查並更新所有受影響的範本（`.specify/templates/`）
4. 更新 `PROJECT_SPEC.md` 中受影響的章節
5. 以 `docs: amend constitution to vX.Y.Z（原因摘要）` 格式提交 commit

**版本號規則（Semantic Versioning）**：
- **MAJOR**：原則被移除或根本性重新定義（破壞現有開發慣例）
- **MINOR**：新增原則或重要章節、重大擴充現有原則
- **PATCH**：文字澄清、拼字修正、非語義性調整

**合規審查**：
每個功能的 `plan.md` 中 MUST 有 Constitution Check 欄位，確認與 7 項原則的相容性。
若某原則不適用於當前功能，MUST 明確說明原因（而非留空或省略）。

**執行時開發指引**：
詳見 `CLAUDE.md`（AI 輔助開發行為規範）與 `PROJECT_SPEC.md`（完整技術規格）。

**Version**: 1.1.0 | **Ratified**: 2026-03-04 | **Last Amended**: 2026-03-04
