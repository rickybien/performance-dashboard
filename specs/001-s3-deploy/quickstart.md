# Quickstart: 驗證 S3 部署

**Feature**: 001-s3-deploy | **Date**: 2026-03-04

## 前置條件（SRE/Admin 負責）

在執行 deploy workflow 前，確認以下已完成：

- [ ] SRE 已建立 S3 bucket 並啟用 Static Website Hosting
- [ ] SRE 已建立 IAM user，具備 `s3:PutObject`、`s3:DeleteObject`、`s3:ListBucket`、`s3:GetObject` 權限
- [ ] Repo Admin 已在 GitHub Secrets 設定以下 4 個 secrets：
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_REGION`（例：`ap-northeast-1`）
  - `AWS_S3_BUCKET`（例：`my-dashboard-bucket`）

---

## 本地驗證（開發者）

### 1. 確認 build 產物路徑正確（SC-003）

```bash
cd frontend
npm run build
npm run preview
```

瀏覽 `http://localhost:4173/`（注意：base 為 `/`，不是 `/performance-dashboard/`）

確認：
- [ ] 首頁（Overview）正常載入，無 404
- [ ] 點選任一 team 進入 Team Drilldown，圖表顯示
- [ ] 點選 Comparison 頁，圖表顯示
- [ ] browser console 無 JS error

### 2. 確認 dev server 資料路徑（FR-007）

```bash
cd frontend
npm run dev
```

確認 `http://localhost:5173/data/latest/dashboard.json` 可存取（應回傳 JSON）。
（base 從 `/performance-dashboard/` 改為 `/` 後，middleware prefix 自動更新）

---

## Workflow 驗證（CI/CD）

### 3. 手動觸發 deploy（User Story 1）

```
GitHub → Actions → Deploy Frontend → Run workflow
```

確認：
- [ ] workflow 執行成功（綠色）
- [ ] 登入 AWS Console → S3 bucket，確認 `index.html`、`assets/`、`data/latest/dashboard.json` 存在
- [ ] 從公司內網瀏覽 dashboard domain，頁面 30 秒內完整載入（SC-001）
- [ ] 所有 3 個路由正常（SC-003）

### 4. 確認 --delete 旗標有效（Edge Case: 殘留檔案）

在本地 build 後，S3 不應存在本次 build 產物以外的舊版 `assets/*.js`、`assets/*.css` 等檔案。
（每次 Vite build hash 會變，`--delete` 清除上一版的舊 hash 檔案）

### 5. 確認 concurrency 行為（FR-010）

同時手動觸發兩次 deploy workflow：
- [ ] 第一次被取消（`cancel-in-progress: true`）
- [ ] 第二次執行完成

### 6. 確認資料更新鏈（User Story 2）

```
GitHub → Actions → Collect Metrics → Run workflow (workflow_dispatch)
```

等待 collect 完成後，確認：
- [ ] `DATA_CHANGED=true` 時，自動觸發 Deploy Frontend workflow
- [ ] S3 上的 `dashboard.json` 時間戳更新為最新

---

## 常見問題

**deploy 失敗，錯誤 `Unable to locate credentials`**
→ 確認 GitHub Secrets 4 個 key 全部設定且名稱拼寫正確。

**deploy 成功但頁面顯示空白或 404**
→ 確認 S3 Static Website Hosting 設定的 Index document 為 `index.html`。

**`/data/latest/dashboard.json` fetch 失敗**
→ 確認 `data/latest/` 目錄在 repo 中存在（首次部署前需先跑一次 collect-metrics）。
  首次部署時即使 data 不存在，deploy 仍成功，dashboard 會顯示資料載入錯誤（非白畫面）。

**外網可存取 dashboard**
→ 此為 SRE 層面問題（bucket policy 或 network ACL），非本 feature 負責範圍（SC-004）。
