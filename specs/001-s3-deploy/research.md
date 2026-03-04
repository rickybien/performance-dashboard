# Research: 前端部署遷移至 AWS S3

**Feature**: 001-s3-deploy | **Date**: 2026-03-04

## 研究問題

本功能為純 CI/CD 基礎設施遷移（GitHub Pages → S3），使用者已確認：
- 維持 Vue + Python 架構不變
- 無資料庫，資料 commit 回程式內
- tech stack 變更只跟 S3 有關

以下三個研究問題在實作前評估。

---

## R-001: `aws s3 sync --delete` 的行為與注意事項

**Decision**: 使用 `aws s3 sync frontend/dist/ s3://${BUCKET}/ --delete`，一次指令涵蓋 FR-001 + FR-002 + FR-011。

**Rationale**:
- `aws s3 sync` 只上傳有差異的檔案（基於 ETag/大小），比 `aws s3 cp --recursive` 高效。
- `--delete` 旗標自動刪除 S3 上不存在於 source 的物件，解決殘留舊檔案問題（FR-011）。
- 在 workflow 執行 `cp -r data/latest frontend/dist/data/` 後，`dist/` 目錄已包含 data 檔案，單次 sync 即同時滿足 FR-001 和 FR-002，無需兩條獨立指令。

**Alternatives considered**:
- `aws s3 cp --recursive`：無增量比對，每次全量上傳，效率低。
- 兩條獨立 `aws s3 sync`（一條 dist、一條 data）：不必要的複雜度，因 data 已 cp 進 dist。
- `aws s3 website sync`（第三方 action）：引入外部依賴，aws cli 已足夠。

**注意事項**:
- ubuntu-latest runner 已預裝 AWS CLI v2，無需額外安裝步驟。
- `AWS_REGION` 環境變數需設定（即使 bucket region 可推斷，顯式設定更穩定）。
- `--delete` 不影響 S3 bucket 外的物件（S3 版本控制歷史、其他前綴的物件）。

---

## R-002: GitHub Actions AWS credentials 注入最佳實踐

**Decision**: 使用 GitHub Secrets 環境變數（`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_REGION`），透過 `env:` 注入 workflow step。`AWS_S3_BUCKET` 在 `run:` 指令中以 `${{ secrets.AWS_S3_BUCKET }}` 直接引用。

**Rationale**:
- Secrets 以 `env:` 注入後，AWS CLI 自動識別標準環境變數（`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_REGION`）。
- `AWS_S3_BUCKET` 不是 AWS CLI 標準環境變數，需在 `aws s3 sync` 指令中直接展開。
- 此方案不需要 `aws configure`，也不依賴 OIDC / role assumption（雖然 OIDC 是更現代的做法，但 SRE 已提供 IAM user credentials，維持現有 secrets 方案即可）。

**Alternatives considered**:
- GitHub OIDC + AWS IAM Role：無需長效憑證，更安全；但需 SRE 配合設定 Trust Policy，超出本次 scope。
- `aws-actions/configure-aws-credentials` action：封裝良好但引入第三方依賴，且此功能夠簡單不需要封裝。
- 憑證放 config.yaml：違反憲法原則 II（Secrets MUST 存放 GitHub Secrets，禁止硬碼）。

---

## R-003: Vite base path 與 S3 static website hosting 相容性

**Decision**: `base: '/'`，對應 S3 bucket 設定為 domain root 存取。

**Rationale**:
- S3 Static Website Hosting 預設以 bucket 或 custom domain root 提供服務，不存在 sub-path 前綴。
- Vite `base: '/'` 讓所有資源引用為絕對路徑（`/assets/index.js`），與 S3 root 存取完全相容。
- `useMetrics.js` 已使用 `import.meta.env.BASE_URL`（Vite 注入 `base` 的值），base 改為 `/` 後，fetch URL 自動變為 `/data/latest/dashboard.json`，**不需修改任何 JS 程式碼**（FR-006 no-op）。
- `vite.config.js` dev server middleware 的 prefix 為 `${base}data/`，base 改為 `/` 後自動變為 `/data/`（FR-007 自動適配，**無需手動修改邏輯**）。
- vue-router hash history（`#/`）不受 S3 routing 影響，所有路由仍正常運作（SC-003）。

**Alternatives considered**:
- 維持 `base: '/performance-dashboard/'`：在 S3 domain root 部署時，所有資源 URL 帶有 `/performance-dashboard/` 前綴，但 S3 bucket 沒有此前綴目錄，導致全面 404。直接排除。
- CloudFront + sub-path rewrite：可支援 sub-path，但 SRE 表示無 CloudFront，且超出本次 scope。

---

## R-004: concurrency group 策略

**Decision**: `cancel-in-progress: true`，確保最新 push 觸發的 deploy 為最終狀態。

**Rationale**:
- `cancel-in-progress: true`：新 deploy 觸發時，取消正在執行的舊 deploy，讓最新版本盡快上線。
- 若 collect-metrics push 資料後同時觸發兩次 deploy（path match + `gh workflow run`），concurrency 確保只有一個在執行，最終結果為最新 build（EC-003）。

**Alternatives considered**:
- `cancel-in-progress: false`：所有 deploy 排隊執行，最後一個也是最新，但浪費 runner 時間且延遲更長。對靜態網站而言 `true` 更適合。

---

## 結論

所有研究問題已解決，無 NEEDS CLARIFICATION 項目。
實作變更集中於兩個檔案：`deploy-frontend.yml`（主要）和 `vite.config.js`（一行）。
追加任務：修訂 `constitution.md` 更新 Vite base 規則（v1.3.0）。
