# Joukir 主仓库迁移设计

日期：2026-09-11

## 目标

在 `E:\develop\数字员工\joukir` 建立新的主开发仓库。新仓库保留当前 Git 完整历史和原始提交 ID，将产品源码从 `source/` 提升到仓库根目录，并合并交接仓库根目录中的部署、CI 和产品文档。迁移完成后，新目录能够独立安装、构建、测试并连接现有的 PostgreSQL 与 Casdoor 恢复环境。

旧目录 `E:\develop\数字员工\joukir-enterprise` 在迁移期间保持不变，迁移完成后由用户手动移除。

## 成功标准

1. 新仓库拥有交接仓库全部 44 次基线提交及本次迁移提交，且不存在指向旧仓库的 Git object alternates。
2. 原 1,152 个已跟踪文件均有明确映射：`source/` 内文件提升到根目录，其余根目录文件原位保留；仅目录合并和本次明确修改的治理文件允许内容变化。
3. 后端、前端、部署脚本、打包脚本、技能包、数据库迁移、测试、文档及 GitHub 配置全部保留。
4. `.venv`、`node_modules`、`dist`、`.dev`、缓存、日志、PID、数据库文件及 Secret 不进入 Git；依赖和构建产物在新目录重新生成。
5. 新目录的后端使用受限权限的本机配置连接现有恢复数据库；前端继续启用企业 OIDC 登录。
6. 前端测试与构建、后端测试基线、Python 编译、数据库生产门禁、应用健康、Casdoor 健康及企业登录跳转均在新目录验证。
7. `main` 作为主分支，仓库具备可直接用于 GitHub Flow 的 CI、CodeQL、Dependabot、发布工作流和 PR 模板。
8. 后续会话可从 `AGENTS.md`、项目记忆、会话交接、开发日志和 ADR 中恢复可靠上下文，且这些文件不包含 Secret。

## 方案选择

采用“保留历史并新增一次根目录迁移提交”。先从当前仓库创建不依赖旧目录的完整克隆，再在新克隆内使用 Git rename 语义提升 `source/` 内容。历史提交仍显示当时的 `source/` 路径，迁移提交之后使用新的根目录路径；`git log --follow` 可跨迁移追踪文件。

不采用重新初始化仓库，因为这会丢失功能来源和修改记录。不采用 history rewrite，因为它会改变所有提交 ID，并容易遗漏 `source/` 外的部署资产。

## 目标目录结构

```text
joukir/
├── .agent/                    # 已有交接分析报告
├── .github/                   # CI、CodeQL、发布、Dependabot、PR 模板
├── backend/                   # FastAPI、数据库迁移、测试与 Python 锁文件
├── deploy/staffdeck-platform/ # PostgreSQL、Casdoor、RLS 与部署脚本
├── docs/                      # PRD、运行手册、记忆、日志、ADR 与迁移报告
├── frontend-enterprise/       # React/Vite 前端、测试与 npm 锁文件
├── packaging/                 # Windows/macOS/Linux 打包源码与资源
├── scripts/                   # 本地开发生命周期脚本
├── skills/                    # Joukir 与 StaffDeck 技能定义
├── AGENTS.md                  # 对后续开发会话生效的仓库规则
├── CONTRIBUTING.md            # GitHub Flow 与本地验证规则
├── LICENSE
├── README.md
└── README.zh.md
```

已有根目录 `deploy/`、`docs/` 和 `.github/` 与 `source/` 中同名目录按文件合并。不存在同名内容覆盖；如发现冲突，停止迁移并逐文件比较。

## Git 与文件迁移

1. 对当前提交创建 `handover-20260909` 标签，保留交接基线指针。
2. 使用完整本地克隆创建 `joukir`，验证 `.git/objects/info/alternates` 不存在并执行 `git fsck --full`。
3. 将工作分支改名为 `main`。
4. 使用 `git mv` 提升 `source/` 中的 tracked 文件和目录；`.github`、`docs` 逐文件合并。
5. 将当前两份本机恢复说明及追加式开发日志纳入新仓库；它们属于接手证据，不包含凭据值。
6. 修正根 `.gitignore`：继续忽略所有运行产物和 Secret，但允许 `docs/` 新文件被跟踪。
7. 删除指向交接 bundle 或旧工作目录的 `origin`。在用户提供目标 GitHub URL 前不创建远程仓库，也不推送。
8. 提交根目录迁移，再提交治理与记忆文件；提交范围不包含环境配置或运行数据。

## 运行配置与数据边界

PostgreSQL、Casdoor 数据卷及运行 Secret 继续位于 `E:\develop\数字员工\joukir-runtime` 和独立 Compose 项目 `joukir-restored-20260909`。新仓库只复制运行所需的 `backend/.env` 与 `frontend-enterprise/.env.local` 到对应忽略路径，并将内部 Python/venv 路径改为新仓库位置。复制和修改过程中不打印 Secret，文件 ACL 仅允许当前管理员与 SYSTEM。

不把 `.venv`、`node_modules` 或旧 `dist` 复制到新目录。后端通过锁文件重建虚拟环境，前端通过 `npm ci` 重建依赖并产生新的 `dist`。旧 `.dev` PID 和日志不迁移；切换时只停止命令行和可执行路径均匹配旧仓库的 Web 进程。

现有 PostgreSQL/Casdoor 容器和数据卷不重建、不删除。SQLite 演示数据库不是功能源码，也不是当前权威数据源；保留在旧目录直到用户自行清理，现有 PostgreSQL 恢复数据不受影响。

## GitHub Flow

`main` 为受保护主分支，日常开发使用短期 `feature/*`、`fix/*`、`docs/*` 或 `chore/*` 分支，通过 Pull Request 合并。提交使用现有 Conventional Commit 风格。PR 模板要求说明问题、改动、风险、验证命令、受影响路由/角色、数据库迁移及文档/ADR。

CI 在 push/PR 到 `main` 时保留现有门禁：后端锁定依赖安装、Python 编译、TikTok 相关 Ruff 检查和 12 个 TikTok 回归测试文件；前端运行完整 Vitest 和生产构建，并新增 `config:check` 与 `i18n:check`。完整后端测试套件在迁移验收中执行并记录基线；确认稳定后再单独扩大 PR 门禁范围。保留 CodeQL、Dependabot 和多平台 release 工作流，并将原 CI 中的 `source/backend`、`source/frontend-enterprise` 路径改为新根目录路径。

远程仓库创建、可见性、组织归属和 GitHub branch protection 需要目标 GitHub 仓库信息，本次只把本地仓库准备到可绑定和推送状态。获得真实 GitHub URL 后再把完整的远程绑定与首次推送命令补入文档；在此之前不写占位远程。

## 长期项目记忆

- `AGENTS.md`：强制后续会话先读取项目记忆和当前会话交接；开发前后更新日志；架构决定写 ADR；禁止记录 Secret。
- `docs/PROJECT_MEMORY.md`：保存稳定架构、关键入口、运行边界、已知测试基线、当前数据库形态和维护规则。
- `docs/SESSION_HANDOFF.md`：保存当前工作状态、最近验证、未完成事项和下一步；每次跨会话任务结束时更新。
- `docs/DEVELOPMENT_LOG.md`：只追加实施证据，记录目标、改动、验证和剩余风险。
- `docs/adr/`：记录会长期影响架构或工作方式的决定。本次创建仓库根目录迁移 ADR。
- `docs/README.md`：作为全部产品、运维、PRD、迁移及记忆文档的索引。

记忆文件只保存可复用事实、路径、配置键名和验证结果，不保存密码、令牌、连接串、API Key、Cookie、私钥或原始外部授权载荷。

## 验证策略

迁移前从 Git 索引生成源文件路径与 blob ID 映射。迁移后验证每个原文件均存在于预期新路径，除 `.gitignore`、`AGENTS.md`、CI 和文档等明确修改项外，blob 内容完全一致。额外检查新目录不存在旧绝对源码路径引用和意外跟踪的 Secret/生成物。

功能验证按以下顺序执行：

1. `git fsck --full`、分支/标签/提交数量、无 alternates、迁移映射无遗漏。
2. `uv sync --locked --extra dev` 与 `npm ci`。
3. Python `compileall`、当前 CI 列出的 Ruff 检查、完整后端 pytest；如存在交接基线失败，保存具体数量和失败列表，并在旧目录执行同一命令对照，只有新目录新增的失败才属于迁移回归。
4. 前端 `config:check`、`i18n:check`、完整 Vitest、生产构建。
5. PostgreSQL production gate。
6. 停止旧目录 Web，使用新目录后台启动；验证 `/api/health`、主要页面、OIDC 配置、Casdoor 健康和浏览器企业登录跳转。
7. 对比新旧功能目录和 Git tracked 清单，确认所有模块均有映射。

任何验证失败都先保留旧服务和旧目录，诊断后再切换。只有新目录实际健康后才把 PID 和启动说明指向新仓库。

## 回退与清理

迁移操作不修改或删除旧源码目录、数据库容器、数据卷和加密备份。新目录验证失败时，可继续从旧目录启动。迁移完成后也不自动删除 `joukir-enterprise`；由用户检查新仓库后手动删除。

新仓库将提供 GitHub 远程绑定说明。绑定和首次推送完成后，建议在 GitHub UI 为 `main` 启用 PR、必需 CI/CodeQL 检查、至少一次审核以及禁止 force push。
