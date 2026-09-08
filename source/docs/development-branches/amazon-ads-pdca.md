# Amazon 广告搜索词诊断与 PDCA 分支日志

## 2026-09-08 · P0 搜索词规则诊断垂直切片（开始）

- 分支：`prd/amazon-ads-pdca`；仅在独立 worktree 中开发。
- 依据：总体 PRD、Amazon PDCA 子项目 PRD、数据库/源码交付合同、需求映射，以及主运行目录中的只读开发日志与开发记忆。
- 现状：`backend/app/advertising` 已有经营约束建议、独立审批、幂等执行策略和 7/14/30 天复盘，但没有搜索词文件输入、字段映射、PDCA Run/Fact/Action 持久化或相应 UI。
- 本步目标：实现合成 CSV 可验证的搜索词上传、严格字段映射、Decimal 指标聚合、保护规则、建议持久化和页面展示。
- 安全边界：新 PDCA 运行固定为 `rules_only`；动作固定为 `advice_only`，没有外部执行接口，不把建议或本地契约测试描述为 Amazon Ads 生产执行成功。
- 已知边界：本切片先覆盖 CSV；XLSX、产品表归属证据、12 Sheet/HTML/JSON 产物、SIF/AI 与周循环留待后续切片。

## 2026-09-08 · P0 搜索词规则诊断垂直切片（完成）

- 交付：新增 UTF-8 CSV multipart 上传与运行列表 API，使用版本化字段映射、Decimal 聚合和零分母显式状态；持久化租户隔离的 Run/Fact/Action 证据。
- 保护约束：缺少产品归属与品牌白名单证据时不生成精准否词；所有动作固定为 `suggested` 且 `external_execution_allowed=false`，不产生审批请求或外部执行记录。
- 数据库：新增 PostgreSQL 可逆迁移，含 RLS/FORCE RLS、最小 `SELECT, INSERT` 授权、复合租户外键、约束和防更新/删除触发器。
- 界面：有权角色可上传 CSV、设定目标 ACoS，并查看运行摘要、警告与优先建议；UI 幂等键同时绑定租户、账户、门店、币种、目标和文件哈希。
- 验证：广告治理与执行相关后端测试 22 项通过；本次 Python 文件 Ruff/compileall 通过；OpenAPI GET/POST multipart 契约通过；定向 Vitest 1 项与前端生产构建通过。
- 现存非阻断噪声：全仓 Ruff 存在本分支修改前的 111 个导入排序问题；Vite 仍报现有大 chunk 告警。
