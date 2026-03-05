# Data Model: 前端部署遷移至 AWS S3

**Feature**: 001-s3-deploy | **Date**: 2026-03-04

## 概覽

本功能為純 CI/CD 基礎設施變更，**不引入新的資料實體，不修改 dashboard.json schema**。
以下文件化三個受本功能影響的關鍵實體，以及它們之間的關係。

---

## 實體定義

### E-001: S3 Bucket（外部，由 SRE 管理）

| 屬性 | 值 | 說明 |
|------|-----|------|
| 建立者 | SRE | 本 feature 不負責建立 |
| Static Website Hosting | 已啟用 | SRE 設定 |
| Access | 內網限制 | SRE 透過 bucket policy 或 network ACL 控制 |
| 目錄結構（部署後） | 見下方 | 由 `aws s3 sync` 寫入 |

**S3 bucket 部署後目錄結構**:

```text
s3://{bucket}/
├── index.html
├── assets/
│   ├── index-{hash}.js
│   └── index-{hash}.css
└── data/
    └── latest/
        └── dashboard.json
```

**關係**：`deploy-frontend.yml` 寫入；前端瀏覽器讀取（透過 domain）。

---

### E-002: GitHub Secrets（外部，由 Repo Admin 設定）

| Secret 名稱 | 型別 | 用途 |
|-------------|------|------|
| `AWS_ACCESS_KEY_ID` | string | AWS IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | string (sensitive) | AWS IAM user secret |
| `AWS_REGION` | string | S3 bucket region（例：`ap-northeast-1`）|
| `AWS_S3_BUCKET` | string | S3 bucket 名稱 |

**約束**：
- 所有 secrets MUST 存放於 GitHub Secrets，禁止硬碼（憲法原則）。
- `AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_REGION` 作為 env 變數注入，AWS CLI 自動識別。
- `AWS_S3_BUCKET` 在 `aws s3 sync` 指令中以 `${{ secrets.AWS_S3_BUCKET }}` 直接展開。

**關係**：被 `deploy-frontend.yml` job 在 step 執行時注入為環境變數。

---

### E-003: deploy-frontend.yml（修改後的 Workflow）

**State Machine（workflow 執行狀態）**:

```
[觸發] → checkout → node-setup → npm ci → npm build
       → cp data/latest to dist → aws s3 sync
       → [成功: S3 更新] / [失敗: workflow 標記 fail，master 不受影響]
```

**觸發條件**（FR-009，維持不變）:

| 觸發方式 | 條件 |
|---------|------|
| push | master 分支 + paths: `frontend/**` 或 `data/latest/**` |
| workflow_dispatch | 手動觸發（無條件） |
| 被 collect-metrics 觸發 | `gh workflow run deploy-frontend.yml`（DATA_CHANGED=true 時）|

**Concurrency**:

```yaml
concurrency:
  group: deploy-frontend
  cancel-in-progress: true  # 最新觸發優先
```

**關係**：
- 依賴 E-002（GitHub Secrets）取得 AWS 憑證
- 寫入 E-001（S3 Bucket）
- 被 `collect-metrics.yml` 透過 `gh workflow run` 呼叫（FR-008，不修改）

---

## 不變的資料流

以下資料流本功能**不觸碰**：

```
Python pipeline (collect_*.py + aggregate.py)
  → data/latest/dashboard.json  [commit 至 repo]
  → 觸發 deploy-frontend.yml
  → aws s3 sync 將 dashboard.json 上傳至 S3
  → 瀏覽器 fetch /data/latest/dashboard.json
  → useMetrics() composable 解析並快取
```

`dashboard.json` 的 schema（teams、aggregated、by_window 等）完全不變（VI. 向後相容）。

---

## 變更摘要

| 項目 | 變更前 | 變更後 |
|------|--------|--------|
| 部署目標 | GitHub Pages (`gh-pages` branch) | AWS S3 bucket |
| 部署步驟 | `peaceiris/actions-gh-pages@v4` | `aws s3 sync --delete` |
| Vite base | `/performance-dashboard/` | `/` |
| data fetch URL | `/performance-dashboard/data/latest/dashboard.json` | `/data/latest/dashboard.json` |
| dev server middleware prefix | `/performance-dashboard/data/` | `/data/` |
| workflow permissions | `contents: write` | `contents: read` |
| concurrency | 無 | `group: deploy-frontend, cancel-in-progress: true` |
