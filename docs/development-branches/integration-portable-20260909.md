# 十分支集成与可迁移开发包

## 2026-09-09 · 开始

- 目标：合并已完成的五条“跨境电商智能运营 SaaS PRD v2.0”分支与五条“跨境电商数字员工部门平台 V1.7”分支成果，整理一份可迁移到其他电脑继续开发的源码与文档交付包。
- 基线：本地 `main` 提交 `d637a20e5b05ba69b26b9df7f857d403745df8a6`。
- 集成分支：`integration/portable-development-20260909`。
- 隔离：只在 `D:/saas/worktrees/joukir-portable-integration-20260909` 合并和验证；不改写 `main`，不覆盖运行中的 `D:/saas/third_party/StaffDeck`，不 push 远端。
- 纳入分支：`prd/platform-foundation`、`prd/bi-analytics`、`prd/amazon-ads-pdca`、`prd/social-operations`、`prd/offsite-channels`、`workforce/platform-governance`、`workforce/seven-role-workflows`、`workforce/tiktok-department`、`workforce/connectors-assets`、`workforce/uat-release`。
- 合并策略：按依赖和提交祖先关系去重；先合入五条通用 SaaS 分支，再合入 UAT 聚合线及其后续增量，最后处理 TikTok 重叠改动；冲突只在独立集成工作树中解决。
- 验收：每条目标分支均为集成分支祖先；工作树干净；后端专项/全量测试、Ruff、前端测试、i18n/config 检查和生产构建按环境可执行范围验证；迁移包排除密钥、运行数据、缓存、虚拟环境和依赖目录，并提供 SHA-256、提交清单、环境重建与继续开发说明。

## 2026-09-09 · 完成

### 集成结果

- 从 `d637a20e5b05ba69b26b9df7f857d403745df8a6` 出发，按依赖顺序形成 9 个显式 merge commit：
  - `5377468`：`prd/platform-foundation`
  - `249f5de`：`prd/bi-analytics`
  - `2457484`：`prd/amazon-ads-pdca`
  - `099e2d3`：`prd/social-operations`
  - `1356abf`：`prd/offsite-channels`
  - `bf2cbd1`：`workforce/uat-release`，其中已经包含 `workforce/seven-role-workflows`
  - `965e6e4`：`workforce/platform-governance`
  - `9a306f0`：`workforce/connectors-assets`
  - `8ba432b`：`workforce/tiktok-department`
- 十条目标分支的 tip commit 均已通过 `merge-base --is-ancestor` 验证为集成分支祖先；`workforce/seven-role-workflows` 因已包含在 UAT 聚合线中，不制造无内容 merge。
- 与基线相比，完成收尾提交前的净变更为 `100 files changed, 14645 insertions, 168 deletions`。收尾提交另加入本日志、迁移指南和英文 i18n 补全。
- 原始本地 `main`、运行源码 `D:/saas/third_party/StaffDeck` 与远端 refs 均未被改写；没有 push。

### 冲突与安全语义

- BI 合并采用加法式导入、模型和路由注册，保留既有平台能力。
- Amazon 广告冲突统一到 `DateTime` 类型并合并双方 i18n，广告写入仍默认关闭，只有显式 sandbox 环境变量才可进入执行测试。
- UAT 日志保留两条独立项目的证据；连接器/TikTok 重叠部分采用更严格的 UAT 门禁，同时保留人工质量评估证据。
- 人工评估证据不会增加官方连接器观察次数或错误计数，防止用人工数据伪造生产连接器稳定性。
- TikTok 生产就绪必须同时满足：连续不少于 14 个不同 UTC 日期的官方连接器观察、零连接器错误、最终 heartbeat 合格，以及不少于 30 次人工对比、采用率不少于 70%、5 类 SOP 覆盖、无严重 guardrail 问题。
- 冻结的 Live-write 清单纳入两个仅限内部治理的 POST 路由：`/authorizations/{authorization_id}/revoke` 与 `/shadow/evaluations`；门禁共核对 23 条路由，并继续失败关闭。

### 验证证据

- 后端集成专项：平台与 BI `16 passed`；Amazon 广告 `12 passed`（显式 `BUSINESS_EXECUTION_ENABLED=true`、`BUSINESS_EXECUTION_MODE=sandbox`、`BUSINESS_EXECUTION_TENANT_IDS=tenant_demo`）；社媒 `6 passed`；站外渠道 `7 passed`；平台治理 `20 passed`；UAT/TikTok 聚合 `44 passed`；最终 TikTok 12 文件回归 `61 passed`。
- 后端全量：`2207 passed, 22 failed, 12 skipped`，耗时 `837.76s`。22 项失败与该 Windows 工作站的既有基线一致，分为默认关闭广告执行的 3 项、Windows 符号链接权限、进程终止/时序、POSIX/Bash/SIGALRM/fcntl 平台差异、Harness 路径/返回语义以及 MCP stdio 本地编码差异；本轮触达能力的专项回归均通过。不得把本结果描述为全量绿灯，应在 Linux CI 与具备符号链接权限的 Windows CI 复跑。
- Python：67 个相对基线变更的 Python 文件通过 Ruff `I,E9,F`；`python -m compileall -q app` 通过。
- 前端：Vitest `64 files / 271 tests passed`；i18n 检查通过 `4209` 条英文翻译；Vite 环境配置检查通过；TypeScript 与生产构建通过。保留现有 `>500 kB` chunk 警告；`npm ci` 报告 2 个 moderate 级依赖漏洞，未执行破坏性自动升级。
- 门禁 CLI：Live-write 清单返回 `ok=true`、`routes=23`、`python=12`、`skills=12`；UAT 证据检查在没有真实外部证据的本机环境按设计返回退出码 2，证明门禁未被本地 Mock 绕过。
- 结构检查：JSON/YAML 解析、`git diff --check` 与目标分支祖先关系均通过。

### 迁移与发布边界

- 继续开发优先使用 Git bundle，以保留 `main`、集成分支、十条目标分支和完整提交历史；源码 ZIP 只用于快速查看或无 Git 场景。
- 迁移包不包含 `.env`、Token、Cookie、密钥、证书、数据库、对象存储内容、`node_modules`、虚拟环境、缓存或构建产物；新电脑必须从 `.env.example` 重新配置环境。
- 真实 OAuth/广告/社媒/站外/TikTok 连接器、生产回调、长期观察窗、人工 UAT、生产数据库迁移与回滚演练仍需在目标环境完成。未配置、Replay、Seed、Mock、Sandbox 或本地 CLI 成功均不等于生产接通。
- 迁移细节、恢复命令、验证矩阵与已知限制见仓库根目录 `docs/PORTABLE_DEVELOPMENT_20260909.md`。最终 commit 是包含本段记录的收尾提交，可在解包后用 `git rev-parse HEAD` 核对，并以交付目录中的 `manifest.json` 和 `SHA256SUMS.txt` 为准。
