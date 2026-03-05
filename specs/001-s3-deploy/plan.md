# Implementation Plan: 前端部署遷移至 AWS S3

**Branch**: `001-s3-deploy` | **Date**: 2026-03-04 | **Spec**: [spec.md](./spec.md)
**Input**: 前端部署從 GitHub Pages 遷移至 AWS S3，CI/CD 仍由 GitHub Actions 驅動，S3 認證透過 GitHub Secrets 注入。維持 Vue + Python 架構，無資料庫，資料 commit 回程式內。

## Summary

純 CI/CD 與設定層的遷移，不涉及任何業務邏輯或 dashboard.json schema 變更。
核心工作為：（1）將 `deploy-frontend.yml` 的 `peaceiris/actions-gh-pages` 替換為 `aws s3 sync --delete`；（2）將 Vite `base` 從 `/performance-dashboard/` 改為 `/`（因 S3 部署於 domain root）。
其餘元件（`useMetrics.js`、`collect-metrics.yml`、Python pipeline、dashboard.json schema）均無需修改。

## Technical Context

**Language/Version**: Python 3.12+, Node.js 20 (frontend build), GitHub Actions
**Primary Dependencies**: AWS CLI v2（ubuntu-latest 內建）, Vite 5, Vue 3, vue-router
**Storage**: 無資料庫；靜態 JSON commit 至 repo，deploy 時 cp 至 `frontend/dist/data/`
**Testing**: Python: pytest (uv)；前端: vitest + @vue/test-utils；CI/CD 變更無 unit test
**Target Platform**: AWS S3 static website hosting，公司內網透過 SRE 設定的 domain 存取
**Project Type**: 靜態網站部署（CI/CD 基礎設施變更）
**Performance Goals**: SC-001: 30 秒內載入完整 dashboard 頁面
**Constraints**: S3 bucket 由 SRE 預先建立；SRE 負責 domain 與網路限制；無 CloudFront
**Scale/Scope**: 單一 S3 bucket，build 產物 < 1MB + data JSON < 1MB

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 狀態 | 說明 |
|------|------|------|
| I. 靜態優先 | ✅ 相容 | S3 仍為純靜態部署，useMetrics() 不變，無瀏覽器端 API call |
| II. config.yaml 單一真相 | N/A | 本功能不涉及 config.yaml 映射 |
| III. 百分位數，非平均值 | N/A | 本功能不涉及指標計算 |
| IV. 漸進式容錯 | ✅ 相容 | S3 上傳失敗時 workflow step 失敗回報，不影響 master 分支狀態 |
| V. 聚合邏輯測試覆蓋 | N/A | 無新聚合邏輯；CI/CD 設定檔無可 unit test 的業務邏輯 |
| VI. 向後相容 Schema 演進 | ✅ 相容 | dashboard.json schema 不變 |
| VII. TDD | ⚠️ 豁免（有理由） | 純 CI/CD 與 Vite 設定變更，無業務邏輯可應用 Red-Green-Refactor；測試仍執行確認既有邏輯不受影響 |

**技術限制規範衝突（Justified Violation）**:

> 憲法「技術限制與規範」章節規定：「Vite base：固定為 `/performance-dashboard/`，禁止修改（對應 GitHub Pages 子路徑）。」

此規則的成立前提是「部署於 GitHub Pages 子路徑」，本功能正是要遷移離開 GitHub Pages。
FR-005 要求 base 改為 `/` 以符合 S3 domain root 存取語義，屬正當理由。
**應對措施**：在實作 commit 後，追加一個 `docs: amend constitution to v1.3.0` commit 更新憲法，
將 Vite base 規則改為「由部署目標決定；S3 domain root 使用 `/`」。

## Project Structure

### Documentation (this feature)

```text
specs/001-s3-deploy/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

Note: `contracts/` 略過 — 本功能為純基礎設施變更，無對外 API 或服務合約。

### Source Code (repository root)

```text
.github/workflows/
├── deploy-frontend.yml   # 主要修改：移除 gh-pages，改用 aws s3 sync
└── collect-metrics.yml   # 不需修改（FR-008/FR-009）

frontend/
└── vite.config.js        # 修改：base '/performance-dashboard/' → '/'

# 不需修改（FR-006 no-op）：
# frontend/src/composables/useMetrics.js  (已使用 import.meta.env.BASE_URL)

# 需追加修改（憲法修訂）：
# .specify/memory/constitution.md
```

**Structure Decision**: 純設定層修改，無新目錄或模組。Vue + Python 架構完整保留。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Vite base 規則偏離憲法 | 部署目標從 GitHub Pages 子路徑遷移至 S3 domain root，`/performance-dashboard/` 前綴在 S3 環境無效 | 維持 `/performance-dashboard/` base 會導致 S3 上所有資源 404；無替代方案可迴避此改動 |
| VII TDD 豁免 | CI/CD YAML 與 Vite 設定檔無可測試的業務邏輯單元；AWS CLI 為外部工具 | 為 `aws s3 sync` 撰寫 mock 測試的複雜度遠超其驗證價值；接受測試（手動 workflow 觸發）更有效 |
