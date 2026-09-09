# workforce/uat-release 分支开发日志

## 2026-09-08 · TikTok Live-write-disabled 确定性发布门禁（开始）

- 基线：`365e5d43c08cb159aa0e2f7100eabae040200a5b`；分支 `workforce/uat-release`；唯一工作目录为 `D:/saas/worktrees/workforce-uat-release/source`。
- 依据：已完整核对《跨境电商数字员工部门平台》V1.7 和综合建设方案，重点核对主 PRD 第 18、19、24、25、26 章及综合方案第 13 章。
- 已核实现状：基线包含 PostgreSQL/RLS 验收脚本、SQLite→PostgreSQL 迁移/备份/独立恢复只读验证脚本、12 个 TikTok Skill 资产门禁、Mock SOP 回放与 14 天影子运行记录。`get_tiktok_production_readiness()` 对 `external_writes` 目前无条件返回 `passed`，不会因 API/Connector/Skill 中新增 Live 写入表面而失败。
- 选定切片：实现只读、可重复的 TikTok Live-write-disabled 代码表面审计，覆盖冻结 API 路由、TikTok 官方 HTTP 动词和 12 个 Skill manifest；将结果接入现有生产就绪卡，并提供 JSON CLI 报告。
- 非目标：不新增 TikTok 业务功能、不改写组织/五专岗/SOP/连接器逻辑、不执行真实 OAuth 或外部读写、不把 Sandbox/Mock/影子运行作为生产放行。
- 风险：静态门禁可能漏过非标准 HTTP 库或误拦合法新路由；因此采用失败关闭的显式冻结清单，新路由必须经审核后更新门禁，并保留“静态证据不替代真实环境验收”的结论。
- 实现前 QA：核对 Python/Node 依赖与命令；运行现有 TikTok release/shadow/Skill 聚焦测试和 Ruff，记录任何基线失败。
- 验证计划：新增正向、新路由、外部 HTTP 写动词和 Skill 写入标记反向测试；运行聚焦 Pytest、Ruff、CLI，再运行相关 TikTok 回归、前端 Vitest/TypeScript build、i18n/config 检查和最终 diff 审计。

## 2026-09-08 · TikTok Live-write-disabled 确定性发布门禁（完成）

- 实现：新增 `backend/app/tiktok/release_gate.py`，以 AST 静态审计冻结 21 个企业 TikTok API 路由和 11 个 TikTok Python 文件；阻断出站 HTTP 写动词、通用 `request`/`send` 调用、`business_execution` 与未审网络库导入，并校验 Skill Pack 注册表及 12 个 manifest 均显式声明 `external_write=false`。
- 接入：`get_tiktok_production_readiness()` 的 `external_writes` 项改为消费同一审计结果，发现问题时失败关闭；新增 `backend/scripts/verify_tiktok_live_write_disabled.py`，输出稳定 JSON，成功退出码为 0、阻断退出码为 2。
- 测试：新增门禁正向、路由漂移、HTTP 写调用、Skill 写标记等反向测试，并覆盖生产就绪卡的通过与阻断状态。TikTok 聚焦测试为 33 passed；变更范围 Ruff 和 `compileall` 通过；CLI 报告 `ok=true`、21 routes、12 skills、11 Python files、0 issues。
- 前端回归：Vitest 为 63 files / 266 tests passed；生产 build 通过，仅保留既有 chunk-size warning。
- 全量回归：后端为 2131 passed、22 failed、11 skipped；失败集中于既有广告执行禁用/配置、Windows symlink/process/timing、Bash/POSIX、harness/MCP/Markdown/runtime-lock 类别，未命中本次变更文件或 TikTok 测试。全量 Ruff 有 2168 个既有问题，变更范围 Ruff 为 clean。
- 外部/环境门禁：i18n 检查因 87 个既有未翻译中文字符串失败；配置检查因净化快照缺少 `frontend-enterprise/.env.example` 失败；`npm ci` 报告 13 个既有依赖漏洞（1 low、3 moderate、9 high）。这些结果不由本切片绕过，且仍不构成真实 OAuth、MFA/TLS/密钥轮换、完整 14 个自然日影子运行、恢复演练或业务/产品/安全签字的替代证据。
- 发布结论：本切片只提供“当前提交的可审计 TikTok 代码与 Skill 表面不含 Live 写入”的确定性证据；以上外部与组织验收完成前，P3-A 仍不可宣称生产放行。

## 2026-09-08 · UAT 前置整改与验收状态

- 已完成仓库内整改：前端 i18n 补齐至 4113 条英文翻译；新增 `frontend-enterprise/.env.example` 并通过 Vite 配置检查；按 npm audit 可用修复更新前端锁文件，审计结果为 0 vulnerabilities。
- 已完成回归：前端 63 个测试文件、266 个测试通过，TypeScript/Vite production build 通过；TikTok 门禁与 33 个 TikTok 测试在合并后的 `main` 上复核通过。
- 真实 OAuth / MFA / TLS / 密钥轮换：未宣称完成。当前快照没有 Partner Center 审核应用凭据、真实回调域名、MFA 测试账号、证书链/轮换窗口或密钥管理器接入；必须由授权的 UAT 运维与安全负责人在隔离环境执行并留存脱敏证据。
- 14 天影子运行：未宣称完成。代码支持 14 天结束时间与周期心跳，但当前没有配置真实租户、生产级 PostgreSQL runtime URL、连续 14 个自然日的心跳/观察记录，因此不能用模拟或缩短时长替代。
- 备份/恢复演练：未宣称完成。`verify_sqlite_postgres_migration.py` 已具备只读核验，但当前环境缺少 `STAFFDECK_POSTGRES_MIGRATOR_URL`、`STAFFDECK_POSTGRES_RESTORE_URL` 和 PostgreSQL 客户端；需在隔离数据库完成行数、校验和、RLS、迁移标记及应用启动证据。
- 业务、产品、安全签字：未完成，需在上述证据包评审后由对应责任人签署；代码提交不能代替组织审批。

## 2026-09-09 · UAT 外部证据接入（完成）

- 新增生产型运行配置检查：要求 PostgreSQL/RLS、关闭自动建表与 Demo Seed、关闭 Mock API、非默认应用密钥、全链路 HTTPS OIDC/Casdoor、Secure Cookie、TikTok Live 模式、受保护 Token Store 和显式影子租户。
- 新增只读 Ed25519 证据验证器：证据包绑定租户、目标 Git commit、发布请求 SHA-256、签名 key id 和有效期；缺失、篡改、过期、错租户/错目标、符号链接或未知字段均失败关闭。
- 证据包覆盖 Casdoor MFA 实测、TLS/证书实测、凭据轮换、PostgreSQL 恢复演练以及业务/安全/产品三方签核。应用只持有公钥，不提供签名私钥或本地“自助通过”接口。
- 加固 14 天影子运行：仅官方 Live 读取计入观察，按 UTC 日期去重；必须覆盖至少 14 个日期、结束后有心跳、保持只读且零连接器错误。仅时间到期但证据不足的运行标记为 `expired`，不再自动完成。
- 生产就绪卡消费上述配置与证据结果；真实 OAuth、14 个自然日影子运行和权威系统验真仍需在 UAT 环境执行，当前开发结果不构成生产放行。
- 验证：TikTok 全域回归 60 passed；变更范围 Ruff、`compileall`、`git diff --check` 通过；Live-write-disabled CLI 仍为 `ok=true`（21 routes、12 Python files、12 read-only Skills）；未配置真实环境时新 CLI 以 exit 2 明确阻断。
