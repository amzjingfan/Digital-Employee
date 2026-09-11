# BI 数据分析并行分支开发日志

## 2026-09-08 · P0 经营事实与指标质量闭环（开始）

- 分支与范围：`prd/bi-analytics`；仅修改 `D:\saas\worktrees\joukir-bi\source`。
- 需求依据：总 PRD v2.0、BI 子项目 PRD v2.0、数据库交付合同、需求覆盖清单，以及只读参考的主开发日志和开发者记忆。
- 现状审计：现有 `operations_reports` 能冻结审批、执行、调度和授权拒绝证据并创建后续任务；仓库尚无 BI 数据源批次、经营事实、版本化指标定义或金额对账模型。现有报告中的 `data_quality` 仅为数据缺失提示，不是可查询的质量检查记录。
- 本次选择：实现“日粒度经营事实入库 → 批次质量/金额对账 → 版本化 KPI → 运营报告证据”的 P0 垂直切片，覆盖 BI-FR-011/012/020/021/022/024/025 与 BI-V2-01/05/08 的基础合同。
- 选择理由：事实与口径是看板、告警、报告和后续 Airflow 连接器的共同前置；当前代码可在不依赖真实外部账号的情况下用合成数据完成幂等、租户隔离、Decimal 金额和证据链验收。
- 明确边界：不把 Airflow、Superset、MCP SDK 或图表依赖的存在标记为业务能力；不接入真实连接器，不执行外部副作用，不使用 AI 生成或修正事实。
- 验收重点：同一输入重放不重复写入；修订批次不累计旧金额；同一源版本不可静默改值；对账失败保留质量证据且不发布事实；分母为零返回 `null + reason`；两租户相同外部 ID 完全隔离；报告可回溯批次、指标版本与事实选择器。

## 2026-09-08 · P0 经营事实与指标质量闭环（完成）

### 已实现

- 新增 `bi_ingestion_batches`、`bi_data_quality_checks`、`bi_daily_commerce_facts`、`bi_metric_definitions`、`bi_daily_metrics` 五张业务表及 PostgreSQL 正向/回滚迁移。
- 批次以租户、数据源、窗口和规范化输入摘要幂等；同窗口新修订会将旧成功批次和旧事实/指标版本标记为 superseded/current=false，不做金额累加。
- 数据质量门禁持久化外部 ID 唯一性、业务日期窗口、源时间未来偏差、单币种粒度、行数对账、GMV 原始金额对账、广告花费对账、源版本不可变检查。失败批次保留检查证据但不发布事实和指标。
- 金额使用 `Decimal/numeric(24,6)`；首版口径固化 GMV、CTR、CVR、CPC、ACOS、TACOS、ROAS、库存天数八个指标。分母为零时保存 `value=null` 与 `null_reason=denominator_zero`。
- 指标同时生成租户日和店铺日粒度，保存口径版本、批次、源观察时间、新鲜度及事实 ID/选择器摘要；新增批次、事实和日指标查询 API。
- 运营日报/周报现在把通过质量门禁的 BI 指标冻结进 `commerce_kpis`，把失败批次和陈旧指标写入数据质量提示，并追加可回溯的报告证据引用。
- 应用层在每个入口绑定可信租户上下文并限制管理/只读角色；数据库迁移使用 RLS `USING + WITH CHECK`、复合租户外键、仅一个成功窗口/当前事实/当前指标的部分唯一索引。BI Worker 也必须显式设置租户上下文，没有全租户旁路策略。
- 指标定义与质量检查在 PostgreSQL 中追加写；版本化事实和指标只允许从 current 变为 superseded，禁止删除或改写历史内容。

### 变更文件

- `backend/app/bi/__init__.py`
- `backend/app/bi/schema.py`
- `backend/app/bi/service.py`
- `backend/app/api/bi.py`
- `backend/app/db/models.py`
- `backend/app/db/database.py`
- `backend/app/main.py`
- `backend/app/operations_reports/service.py`
- `backend/app/security/authorization.py`
- `backend/app/security/casbin_policy.csv`
- `backend/migrations/20260908_bi_metric_pipeline_v1.sql`
- `backend/migrations/20260908_bi_metric_pipeline_v1.down.sql`
- `backend/tests/test_bi_metric_pipeline.py`
- `backend/tests/test_postgres_acceptance.py`
- `docs/development-branches/bi-analytics.md`

### 验证证据

- `python -m pytest tests/test_bi_metric_pipeline.py tests/test_operations_reports.py tests/test_authorization.py tests/test_postgres_acceptance.py -q`：`15 passed, 8 skipped`；跳过项均为需要 `STAFFDECK_RUN_POSTGRES_ACCEPTANCE=1` 的隔离库验收。
- `python -m pytest tests/test_database_config.py tests/test_single_port_app.py tests/test_business_execution.py tests/test_work_tasks.py -q`：`38 passed`，仅有既有 FastAPI/TestClient 弃用警告。
- `python -m ruff check app/bi app/api/bi.py tests/test_bi_metric_pipeline.py`：通过。
- `python -m ruff check --select I,E9,F app/db/models.py app/operations_reports/service.py app/main.py app/security/authorization.py tests/test_postgres_acceptance.py`：通过；`models.py` 的全量 Ruff 仍有项目既有现代化建议，本分支未扩大清理范围。
- `python -m compileall -q app/bi app/api/bi.py app/operations_reports/service.py app/db/models.py tests/test_bi_metric_pipeline.py`：通过。
- 路由导入检查：新增 `/api/enterprise/bi/ingestion-batches`、`/{batch_id}`、`/metrics/daily`、`/facts` 四条路由；未认证访问指标路由返回 HTTP 401，证明路由已挂载且未绕过认证。
- 使用本机已有 `postgres:17.11-bookworm` 启动一次性空库，创建最小平台角色/函数/基表后实际执行正向与回滚迁移：正向结果依次为 `5` 张 BI 表、`5` 个复合外键、`3` 个部分唯一索引、`5` 张表启用 RLS；回滚后 BI 表为 `0`。一次性容器已删除，未连接或修改现有 Joukir 数据库。

### 风险与下一步

- 本切片只提供确定性手工/连接器规范化入库合同；尚未实现真实领星、Amazon、TikTok、物流、财务连接器、Airflow 30 分钟调度或 CSV/XLSX 映射预览，不能宣称这些数据源已接通。
- PostgreSQL 迁移已在一次性空库执行，但尚未在现有 Joukir 升级副本和 `staffdeck_runtime/staffdeck_worker` 真实连接上运行完整验收；上线前需备份后由迁移 owner 执行，并开启 `STAFFDECK_RUN_POSTGRES_ACCEPTANCE=1` 复测。
- 当前指标覆盖收入、广告和库存基础口径；毛利率仍缺商品成本、平台费、物流和退款成本的独立事实，不用不完整字段伪造毛利率。
- 告警规则、负责人/SLA、行动项状态流转、飞书分发回执、前端 ECharts 看板与异步导出仍属于后续 P0。建议下一切片基于本次指标和质量证据实现“规则告警 → 去重/冷却 → ActionItem → 报告/飞书 Outbox”。
