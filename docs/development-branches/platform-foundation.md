# 平台底座与身份权限分支开发日志

## 2026-09-08 · 品牌访问控制面 P0（开始）

- 分支与范围：`prd/platform-foundation`；只修改 `D:\saas\worktrees\joukir-platform\source`。
- 需求依据：平台 PRD `PLAT-V2-02`、`AUTH-FR-002/005`，以及交付合同中的 `Brand`、`BrandMembership`、`StoreAccess`、组合父子范围和 RLS 要求。
- 现状证据：仓库已有租户级 `BusinessResource(store)` 和角色范围，但没有上述三个品牌模型、迁移、API 或测试，成员无法按显式品牌授权解析可见店铺。
- 本步目标：交付品牌模型和 PostgreSQL 正向/回滚迁移；提供租户管理员的幂等成员/店铺授权、成员侧默认拒绝的品牌与店铺查询、追加写审计，并补跨租户/跨品牌负例。
- 边界：本切片建立平台公共授权契约，不在本步重写所有既有业务模块的查询和外发入口；未配置或未验证的外部系统不记录为成功。
- 环境说明：脱敏分支未包含 `source/docs/DEVELOPMENT_LOG.md` 与 `source/docs/DEVELOPER_MEMORY.md`，按父任务指示只读参考 `D:\saas\third_party\StaffDeck\docs` 中的对应文件；技能辅助读取在父任务侧报告为受限，后续按已读取的仓库规则和工程基线继续。

## 2026-09-08 · 品牌访问控制面 P0（完成）

- 数据模型：新增 `Brand`、`BrandMembership`、`StoreAccess` 和追加写 `BrandAccessEvent`；品牌成员与店铺映射均携带非空 `tenant_id`，使用 `(tenant_id, parent_id)` 组合外键阻断跨租户父子引用，时间字段按 UTC `timestamptz` 建模。
- 权限契约：新增 7 条 `/api/enterprise/brands` 路由。租户管理员可创建品牌并通过幂等 `PUT` 授予/撤销成员和店铺范围；普通成员只能列出自己具有 active membership 的 active 品牌，店铺读取必须同时满足租户、品牌成员、访问等级和 active store mapping，未授权默认 403/404。
- 数据库门禁：新增 `20260908_brand_access_v1.sql` 及回滚脚本；包含组合唯一键/外键、store 类型触发器、四表 `ENABLE/FORCE RLS`、runtime/worker 的 transaction tenant 策略、最小 DML grant 和审计表防 UPDATE/DELETE 触发器。worker 没有新增全租户放行策略。
- 审计与幂等：品牌创建、成员变化、店铺映射变化写入无秘密的追加事件；相同品牌创建请求和相同 assignment `PUT` 返回既有资源且不重复写事件。
- 权限表：新增 `brands` capability；租户管理员保留管理权限，各运营业务角色仅有路由级 GET，最终数据可见性继续由显式品牌 membership 决定。
- 测试：`python -m pytest tests/test_brand_access.py tests/test_authorization.py tests/test_business_resources.py tests/test_database_config.py tests/test_tenant_provisioning.py tests/test_account_lifecycle.py -q` 为 `41 passed`；覆盖默认拒绝、viewer/operator、跨品牌、跨租户应用校验、SQLite 组合外键负例、幂等与审计。
- PostgreSQL 边界：`python -m pytest tests/test_postgres_acceptance.py -q` 为 `7 skipped`，原因是当前 worktree 未配置 `POSTGRES_TEST_DATABASE_URL`；本步只验证迁移合同文本，未声称在真实 PostgreSQL 执行成功。
- 全量回归边界：完整后端套件结果为 `2132 passed, 22 failed, 11 skipped`；失败分布在广告执行环境开关、Windows 符号链接权限、微信/飞书进程时序、Harness/通用技能等既有测试域，没有品牌测试失败，也没有失败栈指向本切片改动文件。该结果记录为未全绿，不能用专项通过替代。
- 静态验证：新增文件完整 Ruff、改动旧文件 `I/E9/F` Ruff、Ruff format check、`compileall` 全部通过；直接导入验证 `brand_routes=7 registered=true`；`git diff --check` 通过。
- 未完成：现有 BI/PDCA/Social/Offsite 查询、Job/Worker、导出与外发 Guard 尚未全部调用 `require_brand_store_access`；品牌前端管理页、StoreAccess 受控转移、真实 PostgreSQL 正反 RLS/回滚演练、通用 TenantMembership 多租户切换仍属于后续 P0。新业务模块在接线前不得把本控制面存在误报为全链路 GATE-TENANT 已通过。
