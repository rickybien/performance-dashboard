# Feature Specification: 前端部署遷移至 AWS S3

**Feature Branch**: `001-s3-deploy`
**Created**: 2026-03-04
**Status**: Draft
**Input**: 前端部署從 GitHub Pages 遷移至 AWS S3，CI/CD 仍由 GitHub Actions 驅動，S3 認證透過 GitHub Secrets 注入，SRE 已設定 domain 限公司內網存取。

## User Scenarios & Testing

### User Story 1 - 自動部署前端至 S3 (Priority: P1)

當工程師推送前端變更到 master 時，GitHub Actions 自動 build 並將靜態檔案上傳至 S3 bucket，使用者在內網可瀏覽到最新版本。

**Why this priority**: 這是遷移的核心功能，沒有這個其他都沒意義。

**Independent Test**: 手動觸發 deploy-frontend.yml workflow，確認 S3 bucket 內容更新且內網可存取。

**Acceptance Scenarios**:

1. **Given** master 分支上 `frontend/**` 有新 push，**When** deploy-frontend workflow 被觸發，**Then** build 產物和 `data/latest/` 被上傳至 S3 bucket
2. **Given** deploy workflow 執行成功，**When** 使用者在公司內網瀏覽 dashboard domain，**Then** 可正常載入並顯示 dashboard 頁面和圖表
3. **Given** deploy workflow 執行成功，**When** 使用者在公司外網嘗試存取 dashboard domain，**Then** 無法存取（SRE 層面阻擋）

---

### User Story 2 - 資料更新觸發部署 (Priority: P2)

每日排程收集 metrics 後，若資料有更新，自動觸發前端部署，確保 S3 上的 dashboard.json 同步最新。

**Why this priority**: 確保每日資料更新能即時反映在 dashboard 上，這是 pipeline 端到端正常運作的保證。

**Independent Test**: 手動觸發 collect-metrics workflow（使用 workflow_dispatch），確認資料更新後自動觸發 deploy，S3 上 dashboard.json 為最新版。

**Acceptance Scenarios**:

1. **Given** collect-metrics workflow 執行完成且有資料變更，**When** workflow 觸發 deploy-frontend，**Then** S3 上 dashboard.json 更新為最新內容
2. **Given** collect-metrics workflow 執行完成但無資料變更，**When** workflow 結束，**Then** 不觸發 deploy-frontend（行為不變）

---

### User Story 3 - Vite base path 適配 S3 部署 (Priority: P1)

前端 build 產物的所有路徑引用（路由、資料載入、靜態資源）MUST 相容於 S3 domain root 存取方式。

**Why this priority**: base path 不正確會導致前端白畫面或資料載入失敗，是部署能否成功的前提。

**Independent Test**: 本地 `npm run build` 後，用 `npm run preview` 預覽，確認所有頁面和圖表正常載入。

**Acceptance Scenarios**:

1. **Given** Vite base path 設為 `/`，**When** 執行 `npm run build`，**Then** 產物中所有資源引用以 `/` 為前綴
2. **Given** 部署至 S3 後，**When** 使用者瀏覽首頁、團隊明細、比較頁，**Then** vue-router hash history 路由皆正常運作
3. **Given** 部署至 S3 後，**When** 頁面載入，**Then** `useMetrics()` 成功 fetch `/data/latest/dashboard.json`

---

### Edge Cases

- S3 上傳失敗（網路逾時、認證過期）時，workflow MUST 回報失敗但不影響 master 分支狀態
- `data/latest/` 目錄不存在時（首次部署前可能發生），deploy workflow MUST 仍然成功部署前端，dashboard 顯示載入錯誤而非白畫面
- 同時觸發多次 deploy 時（collect-metrics 和手動觸發同時發生），workflow concurrency 設定 MUST 確保最後一次部署結果為最終狀態
- 前端移除頁面或資源後重新部署，S3 上的對應檔案 MUST 被刪除，不留殘留檔案

## Requirements

### Functional Requirements

- **FR-001**: deploy-frontend.yml MUST 將 `frontend/dist/` 完整上傳至指定 S3 bucket
- **FR-002**: deploy-frontend.yml MUST 將 `data/latest/` 上傳至 S3 bucket 的 `data/latest/` 路徑下
- **FR-003**: S3 認證（`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_S3_BUCKET`、`AWS_REGION`）MUST 從 GitHub Secrets 注入
- **FR-004**: deploy-frontend.yml MUST 移除 `peaceiris/actions-gh-pages@v4` 步驟，改用 AWS CLI `aws s3 sync`
- **FR-005**: Vite base path MUST 從 `/performance-dashboard/` 改為 `/`
- **FR-006**: `useMetrics.js` 的 data fetch 路徑 MUST 適配新的 base path `/`
- **FR-007**: `vite.config.js` 的 dev server middleware MUST 適配新的 base path `/`
- **FR-008**: collect-metrics.yml 觸發 deploy 的機制 MUST 維持不變（`gh workflow run deploy-frontend.yml`）
- **FR-009**: deploy workflow 的觸發條件 MUST 維持不變（push to master paths + workflow_dispatch）
- **FR-010**: deploy workflow MUST 設定 concurrency group，確保不同時執行多次部署
- **FR-011**: S3 同步 MUST 使用 `--delete` 旗標，確保 S3 上不存在於 build 產物中的檔案被自動清除（避免前端刪除頁面或資源後殘留舊檔案）

### Key Entities

- **S3 Bucket**: 存放前端 build 產物和 data JSON，由 SRE 預先建立並設定 static website hosting
- **GitHub Secrets**: `AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_S3_BUCKET`、`AWS_REGION`
- **deploy-frontend.yml**: 需修改的核心 workflow 檔案

## Success Criteria

### Measurable Outcomes

- **SC-001**: deploy workflow 成功執行後，使用者在公司內網可在 30 秒內載入完整 dashboard 頁面
- **SC-002**: 每日 metrics 收集後，S3 上的 dashboard 資料在 10 分鐘內更新（包含 collect + deploy 時間）
- **SC-003**: 所有 3 個前端路由（Overview、Team Drilldown、Comparison）在新部署環境下正常運作
- **SC-004**: dashboard 在公司外部網路無法存取（SRE 層面保證）
