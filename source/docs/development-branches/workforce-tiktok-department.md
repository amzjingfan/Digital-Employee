# workforce/tiktok-department 分支开发日志

## 2026-09-08 · 开始

- 基线：`365e5d43c08cb159aa0e2f7100eabae040200a5b`；分支：`workforce/tiktok-department`；工作树启动时无未提交改动。
- 项目边界：仅依据“跨境电商数字员工部门平台 V1.7”总 PRD 与综合建设方案，责任域限定为 TikTok 事业部 P3-A；未读取或修改另一套 PRD v2.0 五子项目，也不触碰 `worktrees/joukir-*` 或 `prd/*` 分支。
- 已核实现状：组织与六真人岗位、五个 TikTok 专岗、12 Skill Pack、五条主 SOP Mock Replay、六 Tab、30/30 异常矩阵、M2M 验证和 production readiness 已存在。当前 `tiktok.shadow` 仅按 14 天时间推进状态；任务级人工对照没有持久证据，`record_shadow_observation` 无调用者，readiness 可在零样本、零质量结论时把时间届满视为通过。
- 选定切片：补齐“影子运行人工对照与质量门禁”本地闭环。人工评审必须绑定当前租户的 TikTok 任务，以 append-only `WorkTaskEvidence` 保存采纳结论与严重问题；聚合采纳率、严重漏检/越权/虚假声明/未审批写入等护栏，并让 14 天门禁在证据不足或护栏失败时保持阻塞。
- 非目标：不修改 TikTok 远程连接器、ExternalAuthorization/密钥生命周期，不接真实 TikTok 授权，不执行发布、消息、调价、广告、佣金、下单或付款，不重做现有 Bootstrap/Skill/SOP/页面能力。
- 风险：人工摘要可能包含敏感业务原文；接口将限制长度并要求只记录脱敏结论。既有影子计数兼容性需保留，但 readiness 改为从不可变任务证据计算，不信任可变计数器。
- 验证计划：先跑现有 TikTok shadow/readiness 与前端页面聚焦测试；实现后运行新增后端回归、相关 TikTok 回归、Ruff/compileall、前端 Vitest/TypeScript build、i18n/config 检查，并审查最终 diff。

## 2026-09-08 · 完成

- 实现：新增 `POST /api/enterprise/tiktok/shadow/evaluations`，仅管理员可为当前租户、处于复核/完成状态且明确 `external_writes=false` 的 TikTok 任务追加人工对照。证据与 Trace 事件同事务写入；同一影子运行/任务的相同请求幂等返回，不同结论拒绝覆盖。
- 不可变快照：证据路由固化影子运行、问题分类与评审时 SOP，避免任务后续编辑改变历史 SOP 覆盖率；事件固化评审人、结论、问题分类、SOP 与只读声明。
- 质量门禁：至少 30 条任务级评审、五条主 SOP 全覆盖、采纳或修改后采纳比例至少 70%，且严重漏检、越权访问、虚假声明、未审批外部写入均为零。14 天仅代表时间门禁完成，任一质量条件不足时 production readiness fail-closed。
- 管理界面：风险与 KPI Tab 展示人工样本数、采纳率、护栏问题和 SOP 覆盖，并提供只读任务人工对照录入；新增英文词条与交互回归。
- 验证结果：Ruff check/format 与 `compileall` 通过；shadow 聚焦测试 9/9、TikTok 回归 33/33 通过；前端 63 个文件、267 个测试通过；TypeScript/Vite build 通过（仅保留既有 chunk-size warning）。
- 已知基线阻塞：前端 `i18n:check` 保持既有 87 条缺失，本切片新增文本均已覆盖；配置检查因该分支快照没有 `frontend-enterprise/.env.example` 无法执行。
- 依赖与安全：后端通过 `uv sync --extra dev` 恢复本地环境；前端 `npm ci` 报告既有 13 个审计项（1 low、3 moderate、9 high），本切片未做依赖升级或审计自动修复。
