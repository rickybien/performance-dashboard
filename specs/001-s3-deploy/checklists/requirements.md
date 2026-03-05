# Requirements Checklist: 001-s3-deploy

**Feature**: 前端部署遷移至 AWS S3
**Date**: 2026-03-04
**Status**: Verified ✅

## Spec Quality Checks

### 1. WHAT/WHY 層面（無實作細節洩漏）

- [x] User Stories 描述使用者行為與目標，未指定具體實作工具
- [x] Acceptance Scenarios 以行為結果描述，未洩漏 CI 步驟細節
- [x] Success Criteria 以使用者可感知的結果定義（載入時間、路由正常）
- [x] Edge Cases 以系統行為描述，非程式碼層面說明
- [x] FR 中雖有提及 AWS CLI / `--delete` 旗標，屬於必要的整合規格，非過度實作細節 ✅

### 2. 所有 FR 可測試性

| FR | 描述 | 可測試 | 測試方式 |
|----|------|--------|---------|
| FR-001 | `frontend/dist/` 上傳至 S3 | ✅ | 執行 deploy workflow 後檢查 S3 bucket 內容 |
| FR-002 | `data/latest/` 上傳至 S3 | ✅ | 執行後確認 S3 `data/latest/dashboard.json` 存在 |
| FR-003 | 認證從 Secrets 注入 | ✅ | 移除 Secrets 確認 workflow 失敗；有 Secrets 確認成功 |
| FR-004 | 移除 gh-pages action | ✅ | 審閱 workflow YAML 確認無 peaceiris action |
| FR-005 | Vite base path 改為 `/` | ✅ | `npm run build` 後檢查產物 HTML 資源引用前綴 |
| FR-006 | useMetrics.js fetch 路徑 | ✅ | 本地 preview 確認 `/data/latest/dashboard.json` 可存取 |
| FR-007 | vite.config.js dev server 適配 | ✅ | `npm run dev` 確認 dev 環境資料正常載入 |
| FR-008 | collect-metrics 觸發機制不變 | ✅ | 執行 collect-metrics workflow 確認 deploy 被觸發 |
| FR-009 | 觸發條件不變 | ✅ | push frontend 變更確認 workflow 觸發；workflow_dispatch 手動觸發 |
| FR-010 | concurrency group 設定 | ✅ | 同時觸發兩次，確認第一次被 cancel 或 queue |
| FR-011 | `--delete` 旗標 | ✅ | S3 存在舊檔，build 後不含該檔，確認部署後 S3 上舊檔消失 |

### 3. Success Criteria 可量測性

| SC | 描述 | 可量測 | 備註 |
|----|------|--------|------|
| SC-001 | 30 秒內載入完整頁面 | ✅ | 可用瀏覽器 DevTools Network 計時 |
| SC-002 | 資料 10 分鐘內更新 | ✅ | 觀察 collect → deploy workflow 總耗時 |
| SC-003 | 3 個路由正常運作 | ✅ | 手動或自動化瀏覽 3 個路由確認無 404/白畫面 |
| SC-004 | 外網無法存取 | ✅ | 從公司外網嘗試連線確認回應 |

- [x] 所有 SC 不含技術實作描述（無提及 S3 URL、CloudFront、CORS 設定等）
- [x] SC-004 標注「SRE 層面保證」，明確非前端責任範圍

### 4. 無未解決的 [NEEDS CLARIFICATION]

- [x] 掃描全文：無任何 `[NEEDS CLARIFICATION]` 標記
- [x] 所有需要確認的決策（base path = `/`、無 CloudFront、不清理舊部署）已在計畫階段確認並寫入 spec

### 5. User Stories 獨立可測試性

- [x] US1（自動部署）可獨立測試：手動觸發 deploy workflow 即可驗證
- [x] US2（資料更新觸發）可獨立測試：手動觸發 collect workflow 驗證
- [x] US3（base path 適配）可獨立測試：本地 build + preview 驗證，無需實際 S3

### 6. 優先順序合理性

- [x] US1（P1）= 核心部署功能，正確
- [x] US3（P1）= base path 是部署前提，合理升為 P1
- [x] US2（P2）= 資料更新整合，屬於端到端完整性，P2 合理

## 總結

**品質評分**: 🟢 良好

spec 清晰定義了遷移的 WHAT（部署至 S3）和 WHY（安全性、內網限制），FR 涵蓋所有需修改的檔案和行為，SC 可量測且不含實作細節。FR-004 和 FR-011 雖提及具體工具，屬於必要的整合規格邊界，非過度規格化。
