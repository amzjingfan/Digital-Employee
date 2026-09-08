# workforce/connectors-assets 开发日志

## 2026-09-08 · 开始

- 基线：`365e5d43c08cb159aa0e2f7100eabae040200a5b`；分支 `workforce/connectors-assets`；开始时工作树无未提交改动。
- 项目边界：仅依据“跨境电商数字员工部门平台 V1.7”总 PRD 与综合建设方案；未读取或修改另一个 PRD v2.0 五子项目的子 PRD、分支或工作树。
- 已核实现状：已有 TikTok Seller/Creator/Partner/Ads/Social Mock 只读连接器、Seller 官方只读摘要、BusinessResource Scope、ExternalAuthorization、ConnectorSyncState 和密钥引用脱敏。现有读取门禁会检查 active 状态与 scope，但未在调用时检查 `expires_at`，也未校验授权类型与 BusinessResource 类型是否兼容；现有聚焦测试没有覆盖这两个反例。
- 选定切片：TikTok 只读连接器授权生命周期门禁。在任何 Mock 或官方读取前，失败关闭已过期授权和错误授权类型/资产绑定，并返回稳定错误码；补充聚焦回归，证明拒绝发生在外部客户端调用和 SyncState 成功写入之前。
- 非目标：不增加或调用 TikTok Live 写接口；不修改数字员工、SOP、TikTok 组织/页面/Skill Pack、通用身份架构或发布总控；不接触真实 Token、Cookie、退款、发布、调价、广告修改、下单、付款或生产部署。
- 风险：错误的类型映射可能阻断合法只读资产；时间比较必须兼容 SQLite 返回的 naive UTC 与生产 UTC 时间；错误响应不得暴露密钥引用或授权载荷。
- 验证计划：先跑现有 TikTok Connector 聚焦 Pytest 与 Ruff；新增到期、类型/资产错绑、官方客户端未调用、SyncState 无成功副作用测试；再跑 TikTok 专项回归、Ruff、compileall，并检查最终 diff 和敏感信息。
- 基线 QA：`uv run --project backend --extra dev --frozen ...` 已按锁文件安装开发依赖。仓库根首次运行 Pytest 因 `scripts.verify_tiktok_skill_inventory` 导入路径失败；改从 `backend` 工作目录运行后，`tests/test_tiktok_production_bootstrap.py tests/test_tiktok_official_oauth.py -q` 为 `12 passed in 31.11s`。相关 Ruff 基线通过。

## 2026-09-08 · 完成

- 改动：`backend/app/tiktok/connector.py` 新增授权类型与资产类型矩阵；所有 TikTok 资产要求 `metadata_json.platform=tiktok`；调用时兼容 aware/naive UTC 检查授权到期；官方读取能力显式限定为当前已实现的 Seller，其他官方授权类型返回 `tiktok_connector_unavailable`，不会错误调用 Seller API。
- 回归：新增 `backend/tests/test_tiktok_connector_authorization.py`，覆盖 active 但已过期、Seller 错绑广告账户、非 TikTok 广告资产、五类授权域和 Live Room 的合法 Mock 组合，以及官方 Creator 适配器未实现时不得构造外部客户端。所有拒绝路径均断言不会写入成功的 `ConnectorSyncState`。
- 红灯证据：实现前新测试为 `3 failed`，分别证明过期授权未拒绝、类型/资产错绑未拒绝、官方 Creator 错误进入 Seller 客户端；实现后聚焦测试通过。
- 后端验证：TikTok 全部专项 `38 passed in 13.40s`；Connector + BusinessResource + Crossborder Tools 扩展回归 `29 passed in 19.84s`；变更文件 Ruff 通过；`compileall` 通过。
- 前端验证：`npm test -- --reporter=dot` 为 `63 files / 266 tests passed`；`npm run build` 通过。未修改任何前端文件。
- 既有基线问题：`npm run i18n:check` 报告 87 个现有缺失英文文案；`npm run config:check` 因脱敏备份基线缺少 `frontend-enterprise/.env.example` 失败。`npm ci` 对锁定依赖报告 13 个现存漏洞（1 low、3 moderate、9 high）。这些问题均未由本切片引入，也未在连接器分支扩张修复。
- 安全检查：最终 diff 无前端、迁移、配置或密钥文件；测试只使用显式虚构的 `secret://` 引用和不可逆占位指纹；未调用真实外部接口或任何写操作。
- 剩余风险与外部门禁：真实 TikTok Service ID/授权、非 Seller 官方只读适配器、授权远端撤销、14 天影子运行、PostgreSQL 正式环境复测、依赖漏洞处置和独立安全/业务审批仍未完成。本提交只能证明本地 Connector 调用前门禁，不能作为生产放行。
- 建议后续顺序：先合并本门禁，再由 UAT/发布分支在 PostgreSQL 受限运行账号下重放五授权域反例；之后才接入逐授权域官方只读适配器和远端撤销演练。

## 2026-09-08 · 配置与模式门禁

- 改动：新增 `tiktok_connector_mode` 配置，类型限定为 `mock`、`replay`、`live`，默认安全值为 `mock`。Mock 读取只允许 `mock`；已实现的官方 Seller 读取只允许 `live`；`replay` 在尚无连接器回放后端前保持 fail-closed。
- 门禁：模式不匹配时在构造官方客户端或写入成功 `ConnectorSyncState` 前返回稳定错误码 `tiktok_connector_unavailable`；原有过期、授权域/资产类型、scope 与官方能力门禁保持不变。
- 回归：新增 Mock 在 live/replay 模式拒绝、官方 Seller 在 mock 模式拒绝且不构造客户端的测试；官方成功摘要测试显式使用 live 模式，避免依赖环境默认值。
- 验证：聚焦 Connector/OAuth `18 passed`；TikTok 专项（排除脱敏备份基线中需从仓库根导入 `scripts` 的既有 bootstrap 收集问题）`34 passed`；变更文件 Ruff 通过；后端 `compileall` 通过。
- 风险/边界：本切片没有实现 replay 连接器，也没有启用真实 TikTok 凭据或外部写操作；`live` 仅解除模式门禁，真实官方配置、权限、令牌有效性仍由官方客户端与发布审批负责。

## 2026-09-08 · 生产就绪卡联动（开始）

- 目标：让生产就绪卡反映连接器实际执行模式，避免官方配置与授权已就绪但运行时仍处于 `mock`/`replay` 时误报通过。
- 范围：新增独立 `tiktok_connector_mode` readiness gate；只有 `live` 为通过，其他模式保持阻塞；不改变连接器调用门禁、不接真实凭据、不执行外部写操作。
- 验证计划：先验证“官方授权配置通过但模式为 mock 时 readiness 仍阻塞”，再跑 TikTok 及相关资源回归、Ruff、compileall。

## 2026-09-08 · 生产就绪卡联动（完成）

- 实现：`get_tiktok_production_readiness()` 新增 `tiktok_connector_mode` gate；只有 `live` 通过，`mock`/`replay` 均阻塞，并明确提示仅适用于本地或回放验证。
- 回归：新增官方配置与 active 官方授权存在、但模式为 `mock` 时 readiness 仍阻塞的测试；同时确认官方授权 gate 本身仍可正确显示通过，避免模式问题被配置问题掩盖。
- 验证：TikTok 专项（排除既有 bootstrap 导入路径问题）`35 passed`；相关 BusinessResource/Crossborder 回归 `11 passed`；变更范围 Ruff 与 compileall 通过；PostgreSQL acceptance 因未设置 `STAFFDECK_RUN_POSTGRES_ACCEPTANCE=1` 按设计 `7 skipped`，本机未使用任何数据库凭据或修改外部数据。
- 剩余门禁：需要 UAT/发布环境提供隔离 PostgreSQL runtime URL 与受限账号后，才能完成真实 PostgreSQL RLS/权限回放；在此之前不宣称生产放行。
