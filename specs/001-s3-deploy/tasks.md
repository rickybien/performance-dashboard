---
description: "Task list for 001-s3-deploy: 前端部署遷移至 AWS S3"
---

# Tasks: 前端部署遷移至 AWS S3

**Input**: Design documents from `/specs/001-s3-deploy/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅

**Tests**: 本功能為純 CI/CD 與 Vite 設定變更，無可 TDD 的業務邏輯（plan.md Constitution Check VII 豁免）。
驗收測試為手動觸發 workflow，依據 quickstart.md 逐項確認。
提交前 MUST 確認既有測試仍通過：
- Python：`cd scripts && uv run --with jira --with pyyaml --with python-dateutil --with pytest --with PyGithub pytest tests/ -v`
- 前端：`cd frontend && npm test`

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (External Prerequisites)

**Purpose**: 確認外部基礎設施就緒（SRE/Repo Admin 操作，非程式碼任務）

- [ ] T001 確認 SRE 已建立 S3 bucket 並啟用 Static Website Hosting（外部操作）
- [ ] T002 確認 Repo Admin 已在 GitHub Secrets 設定 4 個 secrets：`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_REGION`、`AWS_S3_BUCKET`（外部操作）

**Checkpoint**: GitHub Secrets 就緒後，程式碼修改可開始

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 本功能無程式碼層的 blocking prerequisites（無資料庫、無新模組、無共用基礎設施）。
直接進入 User Story 實作。

---

## Phase 3: User Story 3 - Vite base path 適配 (Priority: P1) 🎯 MVP 前置

**Goal**: 確保 Vite build 產物的所有路徑引用相容於 S3 domain root 存取

**Independent Test**: 本地 `npm run build && npm run preview`，瀏覽 `http://localhost:4173/`，確認三個路由正常載入且 console 無錯誤

**注意**：US3 是 US1 的測試前置條件（build 產物 base 正確才能在 S3 正常運作），應在 US1 之前完成

### Implementation for User Story 3

- [x] T003 [US3] 將 Vite base path 從 `/performance-dashboard/` 改為 `/` 於 `frontend/vite.config.js`（FR-005；同時自動適配 FR-006 useMetrics no-op、FR-007 dev server middleware prefix no-op）
- [x] T004 更新 `.specify/memory/constitution.md`：修訂「技術限制與規範」中的 Vite base 規則，由「固定為 `/performance-dashboard/`」改為「由部署目標決定；S3 domain root 使用 `/`，GitHub Pages 子路徑使用對應前綴」，版本號升至 v1.3.0（plan.md Constitution Check justified violation；須緊接 T003 之後執行，確保 codebase 與 constitution 不存在不一致窗口）

**Checkpoint**: 執行 `npm run build`，確認 `frontend/dist/index.html` 中資源引用為 `/assets/...`（非 `/performance-dashboard/assets/...`）。constitution.md 版本號為 v1.3.0

---

## Phase 4: User Story 1 - 自動部署前端至 S3 (Priority: P1) 🎯 MVP

**Goal**: GitHub Actions 自動 build 並將靜態檔案上傳至 S3 bucket，使用者在內網可瀏覽最新版本

**Independent Test**: 手動觸發 `deploy-frontend.yml` workflow，確認 S3 bucket 內容更新且公司內網可存取

**依賴**: T003（Phase 3 US3）必須先完成，確保 build 產物 base path 正確；T004（Phase 3）必須先完成，確保憲法與程式碼一致

### Implementation for User Story 1

- [x] T005 [US1] 移除 `.github/workflows/deploy-frontend.yml` 中的 `peaceiris/actions-gh-pages@v4` deploy 步驟，並將 `permissions: contents: write` 改為 `contents: read`（FR-004）
- [x] T006 [US1] 在 `.github/workflows/deploy-frontend.yml` 頂層新增 concurrency group：`group: deploy-frontend, cancel-in-progress: true`（FR-010）
- [x] T007 [US1] 修正 `.github/workflows/deploy-frontend.yml` 的 "Copy data files to dist" step：改用 `if [ -d data/latest ]; then cp -r data/latest frontend/dist/data/; fi`，確保 `data/latest/` 不存在時 step 靜默跳過而非 fail（EC-002：首次部署前 data 目錄可能不存在，MUST 仍成功部署前端）
- [x] T008 [US1] 在 `.github/workflows/deploy-frontend.yml` 新增 "Deploy to S3" step：`aws s3 sync frontend/dist/ s3://${{ secrets.AWS_S3_BUCKET }}/ --delete`，並在 step env 注入 `AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_REGION`（FR-001、FR-002、FR-003、FR-011）

**Checkpoint**: workflow 執行成功，S3 bucket 有 `index.html`、`assets/`、`data/latest/dashboard.json`，內網可存取 dashboard

---

## Phase 5: User Story 2 - 資料更新觸發部署 (Priority: P2)

**Goal**: 每日 collect-metrics 後若有資料變更，自動觸發 deploy，確保 S3 上 dashboard.json 同步最新

**Independent Test**: 手動觸發 `collect-metrics` workflow，確認 DATA_CHANGED=true 時自動觸發 deploy，S3 dashboard.json 為最新

**注意**：per FR-008 與 FR-009，`collect-metrics.yml` 與 deploy trigger 機制**維持不變**，本 user story **不需任何程式碼修改**。
任務為驗證現有機制在新 S3 部署目標下仍正常運作。

### Verification for User Story 2

- [ ] T009 [US2] 確認 `.github/workflows/collect-metrics.yml` 的 `gh workflow run deploy-frontend.yml` trigger 機制在 S3 部署後仍有效（驗證任務，無程式碼修改，FR-008）

**Checkpoint**: collect-metrics 完成並 DATA_CHANGED=true 後，deploy workflow 自動觸發，S3 資料更新

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 文件同步、既有測試確認、手動驗收（憲法修訂已提前至 Phase 3 T004）

- [x] T010 [P] 更新 `PROJECT_SPEC.md` §8 CI/CD 流程：反映 deploy workflow 改用 `aws s3 sync`，移除 gh-pages 相關描述（憲法開發工作流程，CI/CD workflow 修改需更新）
- [x] T011 執行既有測試確認無回歸：`cd scripts && uv run --with jira --with pyyaml --with python-dateutil --with pytest --with PyGithub pytest tests/ -v` 以及 `cd frontend && npm test`
- [ ] T012 依 `specs/001-s3-deploy/quickstart.md` 逐項執行手動驗收測試（SC-001～SC-004），包含「首次部署前 data/latest/ 不存在」場景驗證（EC-002）

**Checkpoint**: 所有驗收測試通過，文件同步完成

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 外部操作，可立即開始
- **Foundational (Phase 2)**: 無（略過）
- **US3 (Phase 3)**: 無程式碼依賴，可在 Setup 完成後立即進行
- **US1 (Phase 4)**: 依賴 T003（US3）+ T004（憲法修訂）完成
- **US2 (Phase 5)**: 依賴 US1 完成（S3 deploy 正常運作後才能驗證 trigger chain）
- **Polish (Phase 6)**: T010 可在 US1 後立即並行；T011/T012 依賴全部實作完成

### User Story Dependencies

```
T001 T002 (外部設定)
  ↓
T003 [US3] vite.config.js
T004       constitution.md v1.3.0  ← 緊接 T003，不可推遲
  ↓
T005 → T006 → T007 → T008 [US1] deploy-frontend.yml
  ↓
T009 [US2] 驗證 trigger chain
  ↓
T010 [P]  PROJECT_SPEC.md §8
T011 T012 最終驗證
```

### Parallel Opportunities

- T001 和 T002（外部設定）可同時進行
- T003 和 T004 邏輯上獨立（不同文件），可並行但 T004 **必須在 US1 開始前完成**
- T005、T006、T007、T008 皆修改同一文件，必須依序執行
- T010 與 T011/T012 中的 Python/前端測試可並行

---

## Parallel Example: User Story 1

```text
# US1 的 deploy-frontend.yml 修改（同一檔案，依序處理）
Task T005: "移除 gh-pages 步驟 + 更新 permissions"
  ↓
Task T006: "加入 concurrency group"
  ↓
Task T007: "修正 copy step 加入 data/latest 存在性 guard（EC-002）"
  ↓
Task T008: "加入 Deploy to S3 step"

# Polish 階段 T010 可與 T011 並行：
Task T010: "更新 PROJECT_SPEC.md §8"
Task T011: "執行既有測試"
```

---

## Implementation Strategy

### MVP First (User Story 1 + US3 前置)

1. 完成 Phase 1（Setup）：確認 GitHub Secrets 就緒
2. 完成 Phase 3（US3）：`vite.config.js` base → `/`，緊接更新 constitution.md v1.3.0
3. 完成 Phase 4（US1）：改寫 `deploy-frontend.yml`（含 EC-002 guard）
4. **STOP and VALIDATE**：手動觸發 workflow，確認 S3 部署成功（SC-001、SC-003）
5. 驗證通過後進入 Phase 5、6

### Incremental Delivery

1. T003 + T004 → constitution 與程式碼一致 ✅
2. T005~T008 (US1) → 手動觸發 workflow 驗證 S3 基本部署 ✅
3. T009 (US2) → 驗證 daily trigger chain ✅
4. T010~T012 → 文件同步 + 最終驗收 ✅

---

## Notes

- [P] tasks = 不同檔案，無相互依賴
- [Story] label 對應 spec.md 的 User Story
- US2 **無程式碼修改**：現有 collect-metrics trigger 機制在 S3 環境下仍有效（FR-008/FR-009）
- FR-006 (useMetrics.js) 和 FR-007 (dev server middleware) 均為 **no-op**：自動受益於 T003 的 base 修改
- T004（憲法修訂）已從 Polish phase 提前至 Phase 3，緊跟 T003 後執行
- T007 為新增任務，處理 EC-002（data/latest 不存在時 deploy 仍應成功）
- 每個 commit MUST 只做一件事：不得混入多種目的的變更
- 憲法 v1.3.0 修訂（T004）需單獨 commit：`docs: amend constitution to v1.3.0（更新 Vite base 規則適配 S3 部署）`
