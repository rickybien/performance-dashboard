# 常見 Jira Statuses — 總表

這是一份活文件。每次執行稽核發現新 status 時，請更新此表。

最後更新日期：<!-- 請更新此日期 -->

## 使用方式

新增專案時，先查此表。如果該 status 已有已知的 mapping，直接沿用。
如果是全新的 status，完成分類後請加入此表。

## 主要清單

| Status 名稱        | 語言     | Phase    | 備註                               |
|---------------------|----------|----------|------------------------------------|
| To Do               | EN       | backlog  |                                    |
| Backlog             | EN       | backlog  |                                    |
| Pending             | EN       | backlog  |                                    |
| Open                | EN       | backlog  |                                    |
| 待處理              | ZH       | backlog  |                                    |
| Awaiting            | EN       | backlog  |                                    |
| New                 | EN       | backlog  |                                    |
| Analysis            | EN       | planning |                                    |
| SA/SD               | EN       | planning |                                    |
| In Analysis         | EN       | planning |                                    |
| Design              | EN       | planning |                                    |
| Planning            | EN       | planning |                                    |
| System Design       | EN       | planning |                                    |
| 規劃中              | ZH       | planning |                                    |
| 需求分析            | ZH       | planning |                                    |
| Requirement Review  | EN       | planning |                                    |
| Refinement          | EN       | planning |                                    |
| In Progress         | EN       | dev      |                                    |
| In Development      | EN       | dev      |                                    |
| Developing          | EN       | dev      |                                    |
| Coding              | EN       | dev      |                                    |
| 開發中              | ZH       | dev      |                                    |
| In Review           | EN       | review   |                                    |
| Code Review         | EN       | review   |                                    |
| PR Review           | EN       | review   |                                    |
| Peer Review         | EN       | review   |                                    |
| 審查中              | ZH       | review   |                                    |
| Dev Testing         | EN       | dev_test |                                    |
| Dev Test            | EN       | dev_test |                                    |
| RD Testing          | EN       | dev_test |                                    |
| RD Test             | EN       | dev_test |                                    |
| 開發測試            | ZH       | dev_test |                                    |
| RD 測試中           | ZH       | dev_test |                                    |
| QA                  | EN       | qa       |                                    |
| QA Testing          | EN       | qa       |                                    |
| In QA               | EN       | qa       |                                    |
| Quality Assurance   | EN       | qa       |                                    |
| QA 測試中           | ZH       | qa       |                                    |
| Staging             | EN       | staging  |                                    |
| Regression          | EN       | staging  |                                    |
| UAT                 | EN       | staging  |                                    |
| Stage 環境          | ZH       | staging  |                                    |
| Done                | EN       | done     |                                    |
| Released            | EN       | done     |                                    |
| Closed              | EN       | done     |                                    |
| 已完成              | ZH       | done     |                                    |
| 已上線              | ZH       | done     |                                    |
| Resolved            | EN       | done     |                                    |

## 非 Phase 的 Status

| Status 名稱   | 處理方式                                  |
|----------------|-------------------------------------------|
| Blocked        | 追蹤為浪費（waste）；保留在前一個 phase   |
| On Hold        | 追蹤為浪費（waste）；保留在前一個 phase   |
| Cancelled      | 排除在 cycle time 計算之外                |
| Won't Do       | 排除在 cycle time 計算之外                |
| Duplicate      | 排除在 cycle time 計算之外                |
| Reopened       | 視為回到 dev                              |

## 各專案特有 Status

<!-- 在稽核過程中發現時，請在此新增 -->
<!-- 格式：
| Status 名稱        | 專案     | Phase    | 備註                       |
|---------------------|----------|----------|----------------------------|
| Awaiting Review     | PROJ-B   | review   | Team B 自訂的 status       |
-->
