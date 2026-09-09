# workforce/platform-governance 开发日志

## 2026-09-09 · A2A 客户端恢复租户上下文门禁（开始）

- 基线：`26b630b`；分支：`workforce/platform-governance`；开始时工作树干净。
- 已核实现状：A2A 客户端恢复扫描会跨租户列出可恢复记录，随后每个 `_recover_one` 线程按 `run_id` 读取任务和工具并调用 `ToolExecutor`，但恢复 Session 未在识别任务租户后绑定 PostgreSQL RLS 上下文。
- 选定切片：在 `_recover_one` 读取可信 `A2ATaskRun.tenant_id` 后立即绑定 Session 租户上下文，使工具读取、失败状态写入和恢复执行共享同一租户边界；保留跨租户恢复扫描能力。
- 业务意义：避免应用重启后的 A2A 恢复线程因脱离原请求上下文而以无租户事务读取工具或写入任务状态。
- 非目标：不改变 A2A 协议、恢复状态机、工具参数、外部请求、扫描调度或生产凭据；不在本切片覆盖 Codex A2A 服务端进程的全部 Session。
- 风险：恢复扫描本身必须继续支持跨租户 worker；绑定必须发生在工具查询和任何失败写入前，测试不得触发真实外部工具。
- 验证计划：先运行 A2A/Tool Executor 基线；实现后运行新增恢复回归、Tool Executor 套件、Ruff、compileall，并更新本分支开发日志记录结果。

## 2026-09-09 · A2A 客户端恢复租户上下文门禁（完成）

- 改动：`backend/app/tools/a2a_recovery.py` 在恢复线程读取 `A2ATaskRun` 后立即绑定 `run.tenant_id`；工具缺失或工具租户不一致时拒绝执行并写入失败状态，避免 SQLite 兼容路径绕过租户校验。
- 回归：新增 `backend/tests/test_a2a_recovery.py`，覆盖恢复执行上下文绑定及跨租户工具拒绝，测试使用假的 `ToolExecutor`，不触发真实外部 A2A 请求。
- 聚焦验证：`.venv\\Scripts\\python.exe -m pytest tests/test_a2a_recovery.py tests/test_tool_executor.py -q` -> `24 passed`；Ruff `--select I,E9,F`（A2A Recovery 与测试）通过；相关 `compileall` 与 `git diff --check` 通过。
- 安全边界：未改变 A2A 协议、恢复调度、工具参数或外部网络调用；未加入密钥、Token、真实外部载荷或生产写路径。
- 剩余风险与门禁：恢复扫描仍需跨租户列出待恢复记录，这是 worker 级明确边界；Codex A2A 服务端进程的多处 Session、团队唤醒扫描和隔离 PostgreSQL 真实 RLS 验收仍待后续治理。

## 2026-09-09 · 公共 Job 执行器租户上下文门禁（开始）

- 基线：`8d2a8e2`；分支：`workforce/platform-governance`；开始时工作树干净。
- 已核实现状：`run_job` 可跨租户扫描并 CAS claim 一个 `APIJob`，但 claim 后到 started 事件、handler、取消检查、终态写入和失败收尾期间未为该 Job 的独立 Session 绑定租户上下文；具体 Handler 只能各自补救。
- 选定切片：在成功 claim 得到可信 `APIJob.tenant_id` 后立即调用 `set_tenant_context`，让公共执行器后续事务和所有 Handler 共享同一租户边界；保留跨租户队列 claim 能力，不改变 Job 状态机。
- 业务意义：把租户门禁从单个 Handler 提升到统一执行边界，避免新增公共 Job 忘记设置上下文，也让 started、failed、cancelled 和 run 会话收尾审计遵循同一租户。
- 非目标：不改变 CAS claim 条件、队列调度、Job 重试语义、公共 API 权限、前端、外部通知或生产凭据；不在本切片重构跨租户恢复扫描。
- 风险：claim 事务本身必须继续支持跨租户 worker；上下文绑定失败时不能静默执行 Handler，现有 SQLite 测试需保持兼容。
- 验证计划：先运行公共 Job 基线；实现后运行公共 API/Handler 回归、Ruff、compileall，并更新本分支开发日志记录结果。

## 2026-09-09 · 公共 Job 执行器租户上下文门禁（完成）

- 改动：`backend/app/public_api/jobs.py` 在跨租户 CAS claim 成功并获得可信 `APIJob.tenant_id` 后立即绑定 Session 租户上下文；started 事件、Handler、取消检查、终态写入和失败收尾均复用该上下文，跨租户队列扫描能力保持不变。
- 回归：`backend/tests/test_public_api_v1.py` 新增执行器上下文测试，验证 Handler 在执行前观察到正确租户且 Job 正常完成。
- 聚焦验证：`.venv\\Scripts\\python.exe -m pytest tests/test_public_api_v1.py -q` -> `18 passed`（1 个既有 Starlette 弃用警告）；合并反馈公共 Job 回归 -> `24 passed`；Ruff `--select I,E9,F`（公共 Job 与测试）通过；相关 `compileall` 通过。
- 安全边界：未改变 claim CAS 条件、Job 状态机、权限、队列调度、前端或外部通知；未加入密钥、Token、真实外部载荷或生产写路径。
- 剩余风险与门禁：claim 阶段仍需无租户上下文扫描 Job 表，这是为支持跨租户 worker 的明确边界；其他全量恢复/清理扫描入口及隔离 PostgreSQL 账号下的真实 RLS 验收仍待后续治理。

## 2026-09-08 · 异步反馈分析租户上下文门禁（开始）

- 基线：`8f6e155`；分支：`workforce/platform-governance`；开始时工作树干净。
- 已核实现状：`feedback.analyze` 的内部排队、旧版异步执行入口和持久化 Job Handler 都可在独立 `Session(engine)` 中运行；旧版入口未设置租户上下文，服务按反馈主键读取，SQLite 兼容路径还可能在租户校验前分析到其他租户反馈。
- 选定切片：为反馈排队与执行路径绑定可信 `tenant_id`，让分析服务支持带租户读取并在进入模型分析前拒绝租户不一致记录；新增成功上下文和跨租户拒绝回归。
- 业务意义：保证反馈内容、会话消息、执行轨迹和分析结果始终留在发起反馈的租户边界内，并让 PostgreSQL `FORCE RLS` 在后台分析事务中生效。
- 非目标：不改变反馈分类提示词、模型重试策略、公开 Job 状态机、前端、外部通知或生产凭据。
- 风险：持久化 Job Handler 由公共 Job 执行器调用，必须在按 Job 租户绑定上下文后再分析；旧版入口与内部排队入口需保持 API 兼容。
- 验证计划：先运行反馈分析基线；实现后运行反馈/公共 Job 相关回归、Ruff、compileall，并更新本分支开发日志记录结果。

## 2026-09-08 · 异步个人记忆采集租户上下文门禁（开始）

- 基线：`70b0c023e429a7d4f9ddda044631a1762ae5635d`；分支：`workforce/platform-governance`；开始时工作树干净。
- 已核实现状：`memory.capture_turn` 任务元数据携带 `tenant_id`，但 Worker 直接创建 `Session(engine)` 后未绑定 PostgreSQL RLS 租户上下文；任务内的 session、model config、消息历史和记忆写入因此缺少事务级租户门禁。
- 选定切片：在异步 Memory Worker 解析并校验 `ChatTurnRequest` 后，立即为独立数据库 Session 设置可信 `tenant_id`；增加上下文绑定回归，覆盖任务执行使用入队请求的租户且不扩大跨租户查询范围。
- 业务意义：保证后台个人记忆采集在 PostgreSQL `FORCE RLS` 下只能读取和写入所属租户数据，不因脱离请求线程而退化为无上下文访问。
- 非目标：不改变记忆抽取提示词、去重策略、对话边界、队列调度、前端、TikTok、连接器、生产凭据或外部写操作。
- 风险：Session 上下文必须在首次查询前绑定；测试使用 SQLite 时仍需保持调用契约，不能引入仅 PostgreSQL 可运行的分支。
- 验证计划：先运行 Memory/Async Job 基线；实现后运行同套件、Ruff、compileall，并更新本分支开发日志记录结果。

## 2026-09-08 · 人工接管恢复线程租户上下文门禁（开始）

- 基线：`365e5d43c08cb159aa0e2f7100eabae040200a5b`；分支：`workforce/platform-governance`；开始时工作树干净。
- 已核实现状：聊天流式 Worker、事件中继、异常收尾和标题摘要已通过 `_tenant_session(tenant_id)` 为独立数据库 Session 绑定 PostgreSQL RLS 租户上下文；人工接管异步恢复仍只传 `handoff_id`，恢复和失败记录均直接创建无租户上下文的 `Session(engine)`。
- 选定切片：将已授权回复路径中的可信 `tenant_id` 固定传入人工接管恢复线程，并在读取接管单、会话、写入开始/失败审计以及恢复 AgentLoop 前绑定租户上下文；增加跨租户与上下文绑定回归。
- 业务意义：在 PostgreSQL `FORCE RLS` 下保证人工答复可恢复原 SOP，同时避免后台线程以无上下文或错误租户查询接管、会话和审计记录。
- 非目标：不改变人工接管分派策略、SOP 业务语义、七岗位流程、TikTok、连接器、生产凭据或外部写操作；不尝试用平台级旁路身份反查租户。
- 风险：线程参数签名会影响现有单元测试和内部调用；异常处理必须仍在同一租户上下文内记录失败，且不得因错误 tenant 值回退到非 RLS 查询。
- 验证计划：先运行人工接管与聊天绑定基线测试；实现后运行聚焦 Pytest、相关聊天/团队会话回归、Ruff/compileall，并按仓库可用性运行更广后端回归；本切片不改前端，仍执行前端 Vitest、TypeScript/Vite build、i18n 和配置检查确认无跨层回归。

## 2026-09-08 · 人工接管恢复线程租户上下文门禁（完成）

- 改动：`backend/app/api/chat.py` 将授权回复路径已验证的 `tenant_id` 与 `handoff_id` 一并传入异步线程；恢复主路径与异常审计路径均复用 `_tenant_session` 设置 PostgreSQL 事务级租户上下文，并在 SQLite 兼容路径显式拒绝接管单或会话租户不一致。
- 回归：`backend/tests/test_human_handoff_policy.py` 验证回复调度固定租户、成功恢复前上下文绑定、错误租户无 AgentLoop/无审计副作用、恢复异常仍在同租户上下文记录；`backend/tests/test_feishu_handoff.py` 隔离来源字段测试的后台线程，避免误连默认测试库。
- 环境 QA：系统 Python 3.11 缺少 FastAPI，首次基线在收集阶段失败；随后用 `uv sync --extra dev --frozen` 建立忽略的本地 `.venv`（Python 3.14.7）后，修改前人工接管/聊天基线为 `48 passed`。前端使用 `npm ci --ignore-scripts` 安装忽略的依赖目录；安装审计报告 13 个既有依赖漏洞（1 low、3 moderate、9 high），本切片未改依赖锁文件。
- 聚焦验证：`uv run --frozen pytest tests/test_human_handoff_policy.py tests/test_chat_agent_binding.py tests/test_teams_conversations.py tests/test_feishu_handoff.py -q` -> `100 passed`；`uv run --frozen ruff check --select I,E9,F app/api/chat.py tests/test_human_handoff_policy.py tests/test_feishu_handoff.py` -> 通过；相关 `compileall` -> 通过。
- 治理回归：身份、OIDC、租户、Casbin、RLS、统一任务、审批、审计、个人记忆、人工接管与聊天相关套件 -> `180 passed, 7 skipped`；7 项均为未设置 `STAFFDECK_RUN_POSTGRES_ACCEPTANCE=1` 且未提供隔离 PostgreSQL 验收库，因此不是本地 PostgreSQL 实库证明。
- 全量后端：直接运行因既有 `tests/test_tiktok_production_bootstrap.py` 无法导入 `scripts` 在收集阶段停止；明确排除该文件后为 `2117 passed, 25 failed, 11 skipped`。25 项失败均不在本次人工接管/聊天租户上下文文件，集中于既有广告执行配置、Windows 符号链接/`SIGALRM`/`fcntl`、子进程时序、MCP 编码、Harness 路径与运行锁环境差异。
- 前端验证：Vitest `63 files / 266 tests passed`；TypeScript/Vite 生产构建通过（仅有既有大 chunk 警告）。`npm run i18n:check` 因 87 个既有中文直写项失败；`npm run config:check` 因脱敏备份缺少 `frontend-enterprise/.env.example` 失败；本切片无前端改动。
- 安全边界：未加入密钥、Token、Cookie、真实外部载荷或外部写路径；未调用真实退款、发布、调价、广告、下单、付款或生产部署。
- 剩余风险与门禁：需要在隔离 PostgreSQL 运行账号环境启用 7 项 RLS 验收，证明线程事务的 `SET LOCAL app.tenant_id` 行为；正式 Casdoor MFA/TLS/密钥轮换、真实连接器故障演练和业务/安全签字仍为外部门禁。全量既有失败、i18n/config 门禁及 npm 依赖漏洞应由对应责任域另行处理。

## 2026-09-08 · 异步个人记忆采集租户上下文门禁（完成）

- 改动：`backend/app/memory/jobs.py` 在后台任务首次查询前调用 `set_tenant_context(db, request.tenant_id)`，使 PostgreSQL 事务继承 `SET LOCAL app.tenant_id`；同时对 `ChatSession` 与 `ModelConfig` 做租户一致性校验，SQLite 兼容路径遇到跨租户任务只记录 `memory_error` 并拒绝进入 MemoryService。
- 回归：`backend/tests/test_memory_service.py` 新增后台任务上下文绑定与跨租户 session/model 拒绝测试，验证 MemoryService 只在请求租户一致且 Session 已绑定时执行。
- 聚焦验证：`.venv\\Scripts\\python.exe -m pytest tests/test_memory_service.py tests/test_async_jobs.py -q` -> `19 passed`；扩展 Memory Review 回归（加 `tests/test_memory_reviews.py`）-> `23 passed`；Ruff `--select I,E9,F`（Memory Worker 与测试）通过；相关 `compileall` 通过。
- 安全边界：未改变记忆抽取提示词、对话边界、队列调度、前端或外部系统；未加入密钥、Token、真实外部载荷或生产写路径。
- 剩余风险与门禁：仍需在隔离 PostgreSQL 账号环境运行 RLS 验收，证明后台线程事务级 `SET LOCAL app.tenant_id` 的真实数据库行为；其他未绑定上下文的历史后台 Worker 不在本切片范围，需后续按 P0 清单逐项收敛。

## 2026-09-08 · 异步反馈分析租户上下文门禁（完成）

- 改动：`backend/app/feedback/jobs.py` 的内部排队、旧异步入口和持久化 Job Handler 均在数据库操作前绑定租户上下文；Handler 只信任 `APIJob.tenant_id`，载荷租户不一致时直接拒绝。`backend/app/feedback/service.py` 的分析读取支持可选租户过滤，避免在 SQLite 兼容路径下先分析后校验。
- 回归：`backend/tests/test_feedback_analysis.py` 新增反馈租户过滤、旧入口上下文、Handler 上下文和载荷篡改拒绝测试。
- 聚焦验证：`.venv\\Scripts\\python.exe -m pytest tests/test_feedback_analysis.py tests/test_public_api_v1.py -q` -> `24 passed`（1 个既有 Starlette 弃用警告）；Ruff `--select I,E9,F`（Feedback Worker/Service 与测试）通过；相关 `compileall` 通过。
- 安全边界：未改变反馈分类提示词、模型重试策略、公共 Job 状态机、前端或外部通知；未加入密钥、Token、真实外部载荷或生产写路径。
- 剩余风险与门禁：公共 Job 执行器在 claim 阶段仍是跨租户扫描入口，需后续单独设计“按 job 租户绑定后执行”的通用治理方案；隔离 PostgreSQL 账号下的真实 RLS 验收仍待环境支持。
