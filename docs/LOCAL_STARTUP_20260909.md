# 九骥 Joukir：项目接手分析与本地启动记录

日期：2026-09-09。分析依据为本次交付源码、随包文档及本机运行验证；未对所有业务流程做完整验收。

## 当前结论

项目已在本机启动，并已从 SQLite 演示环境切换到交接包恢复的 PostgreSQL 与 Casdoor。密钥有效，四个数据库恢复完成；针对源码与备份的版本差异，已执行仓库已有的五个迁移，补齐 21 张表。数据库检查、应用健康、企业 SSO 跳转及 12 个数字员工服务身份鉴权通过。

当前人工账号登录和真实模型对话尚未验收。原模型配置及密钥已恢复且解密验证通过，但未发送外部模型请求。恢复范围、验证证据与限制见 [数据库恢复记录](./DATABASE_RESTORE_20260909.md)。

- 应用入口：http://127.0.0.1:5173/workspace/gallery
- 管理入口：http://127.0.0.1:5173/enterprise/agents
- 模型配置：http://127.0.0.1:5173/enterprise/models
- TikTok 事业部：http://127.0.0.1:5173/enterprise/tiktok
- 登录：点击“企业 SSO 登录”，使用交接的原 Casdoor 账号密码；请从应用入口发起登录，不复用旧 OAuth 跳转链接。
- Casdoor：http://localhost:18000；PostgreSQL：`127.0.0.1:55433`。
- 监听范围：仅 `127.0.0.1`，本次没有配置开机自启。

## 项目是什么

这是基于 StaffDeck 扩展的企业数字员工与跨境电商运营平台。基础能力包括数字员工档案、团队协作、知识库、通用技能、SOP、对话及执行记录、工具调用和定时任务；业务扩展覆盖运营数据、商品、广告、社媒、站外渠道、TikTok 事业部，以及统一任务、身份、权限和审批管理。

它是一个具有实际后端、持久化模型、前端页面和测试集的集成项目。代码中已有大量业务模块，但本地种子数据与通过测试的逻辑，不能证明真实店铺授权、模型调用和业务执行已经接通。

| 层次 | 技术和职责 | 优先阅读位置（相对本仓库） |
| --- | --- | --- |
| Web 前端 | React 18、TypeScript、Vite 8、Tailwind CSS 4、Radix；管理页与员工工作台 | `source/frontend-enterprise/src/App.tsx`、`src/enums/routes.ts`、`src/pages/` |
| API 与启动 | Python 3.11+、FastAPI；同一端口提供静态前端和 API | `source/backend/single_port_app.py`、`app/main.py`、`app/api/` |
| 数据存储 | SQLModel/SQLAlchemy；本地 SQLite；另有 PostgreSQL 迁移及租户隔离实现 | `source/backend/app/db/`、`deploy/staffdeck-platform/` |
| 数字员工运行 | Harness v2、技能/SOP、知识、工具、团队、任务和追踪 | `source/backend/app/core/`、`app/harness/`、`app/agents/`、`app/work_tasks/` |
| 业务模块 | BI、广告、社媒、站外、商品生命周期和 TikTok | `source/backend/app/bi/`、`advertising/`、`social/`、`offsite/`、`product_lifecycle/`、`tiktok/` |
| 身份与权限 | 本地登录、Casbin、OIDC/Casdoor、租户及资源范围控制 | `source/backend/app/security/`、`app/accounts/`、`deploy/staffdeck-platform/compose.yml` |

仓库许可证标识为 AGPL-3.0，原文位于 `source/LICENSE`。

## 恢复来源与本次改动

从 `joukir-portable-development-20260909/Joukir-StaffDeck-git-20260909.bundle` 克隆，先验证其 SHA-256 与 manifest 一致。

- 分支：`integration/portable-development-20260909`
- 提交：`e0cb8df042b3a5f856c60b45cf7e9c2bafbc23b5`
- Git 历史和来源分支保留；`origin` 当前指向本地 bundle，并非远程托管仓库。
- 应用位置：`E:\develop\数字员工\joukir-enterprise\source`
- 安装后端锁定依赖到 `source/backend/.venv`，安装前端锁定依赖并构建 `source/frontend-enterprise/dist`。
- 第一阶段创建 SQLite 演示配置和数据库；第二阶段已将 `source/backend/.env` 切换为恢复的原应用密钥、PostgreSQL 与 OIDC 配置，并修正旧机器路径和本机端口。
- 保留 Casbin 与 PostgreSQL 强制 RLS 权限控制，已启用 OIDC；外部业务执行、任务自动执行和 TikTok 官方连接关闭，运行角色为 `api`。
- SQLite 演示库 `source/backend/skill_agent_loop.db` 保留，其原配置保存在受限运行目录 `E:\develop\数字员工\joukir-runtime\sqlite-demo.env`。
- 本机前端配置 `source/frontend-enterprise/.env.local` 设置 `VITE_OIDC_ENABLED=true`，已重新构建。
- 未修改应用业务源码；新增本文及 `source/docs/DEVELOPMENT_LOG.md`。后者被现有 `source/.gitignore` 的 `/docs/` 规则忽略。
- 原始源码包、Git bundle 和加密备份未改动。

## 第一阶段验证结果（SQLite 演示环境）

以下为切换原数据库前的测试和演示结果，不能作为原账号和原业务流程已经验收的证明。原库阶段的结果见数据库恢复记录。

| 验证 | 本次结果 |
| --- | --- |
| 后端依赖 | `uv sync --locked --extra dev` 成功，安装 79 个包 |
| 前端依赖 | `npm ci` 成功，安装 561 个包 |
| 前端构建 | TypeScript 检查及 Vite 生产构建成功 |
| 前端测试 | 64 个测试文件、271 项测试通过 |
| 国际化 | 4209 条英文翻译覆盖检查通过 |
| 前端配置 | `config:check` 通过 |
| 后端专项 | 单端口服务、种子数据、角色、接口权限、BI 流水线共 31 项通过 |
| 健康检查 | `/api/health` HTTP 200，`status=ok`，`app=九骥 Joukir` |
| 页面服务 | `/workspace/gallery`、`/enterprise/tiktok` HTTP 200 |
| 登录 | 浏览器及 API 管理员登录通过，`/api/auth/me` HTTP 200 |
| 数字员工 API | `/api/enterprise/agents` HTTP 200，11 个示例员工 |
| 任务和 TikTok API | 任务列表、TikTok 概览和生产就绪检查均 HTTP 200 |
| TikTok 就绪状态 | `ready=false`，与尚未配置正式连接的状态一致 |
| 浏览器业务页面 | 员工档案展示示例能力与记录；TikTok 页面显示组织模板尚未初始化 |

后端专项首次执行在测试断言结束后遇到系统临时目录权限错误；指定仓库内独立 `--basetemp` 后重跑成功，最终退出码为 0。前端存在已有 React key/ref 警告，构建主 JS 约 2.4 MB（gzip 约 751 KB），存在大包警告。

本次未运行全部后端测试。交接包记录的旧环境结果为 **2207 passed / 22 failed / 12 skipped**，不能与本次 31 项专项通过混淆。

## 重新启动

依赖和前端产物已经准备好。先确认 Docker Desktop 已运行，在当前管理员 PowerShell 启动恢复的基础服务：

```powershell
$platformDir = 'E:\develop\数字员工\joukir-runtime\platform'
docker compose --env-file "$platformDir\.env" -f "$platformDir\compose.yml" -p joukir-restored-20260909 up -d --pull never postgres casdoor
```

确认本项目的旧 Web 进程已停止且端口 5173 空闲后执行：

```powershell
Set-Location 'E:\develop\数字员工\joukir-enterprise\source\backend'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:ULTRARAG_DATA_DIR = 'E:\develop\数字员工\joukir-runtime\data'
.\.venv\Scripts\python.exe -m uvicorn single_port_app:app --host 127.0.0.1 --port 5173 --no-access-log
```

此命令以前台方式运行，关闭该终端或按 Ctrl+C 即停止。端口已占用时不要重复启动。当前这次运行使用隐藏后台进程；启动进程 PID 保存在 `source/.dev/local-web.pid`，日志位于 `E:\develop\数字员工\joukir-runtime\logs\web.log` 和 `web.err.log`。运行 Secret 仅允许当前管理员和 SYSTEM 读取。

改过前端代码后，先重新构建：

```powershell
Set-Location 'E:\develop\数字员工\joukir-enterprise\source'
npm --prefix frontend-enterprise run build
```

健康检查：

```powershell
Invoke-RestMethod 'http://127.0.0.1:5173/api/health'
```

本次没有使用 `scripts/dev_up.ps1`：该入口强制准备沙箱运行时，其中包含 `allowAllDomains` 补丁。自动审批以扩大沙箱网络权限为由拒绝安装；因此采用文档支持的直接 Uvicorn 入口。未绕过审批安装该补丁，命令执行沙箱能力暂未配置。

## 接手后优先处理的缺口

1. **真实对话验收**：原模型配置和应用密钥已恢复，并已验证配置能够解密；仍需用原账号登录后验证一次真实模型调用和数字员工对话。
2. **人工身份验收**：数据库、Casdoor、OIDC 跳转及全部 12 个活跃 M2M 身份验证通过；尚未使用人工账号密码完成登录与角色页面验收。
3. **素材完整性**：备份说明明确不含 MinIO 对象数据；仅恢复数据库不保证原素材文件可用。
4. **真实业务接通**：TikTok、广告、社媒和渠道需逐项验收授权、同步及执行。M2M 身份恢复不代表外部业务链路可用。当前仅启动 PostgreSQL、Casdoor 和 Web/API，未启动 Redis、MinIO、Superset 或后台任务执行器。
5. **文档一致性**：交付缺少 `backend/.env.example`、`docs/DEVELOPER_MEMORY.md` 及部分 AGENTS 引用文档；旧 README 的 SQLite 限制描述与集成后的 PostgreSQL 实现不一致；README 推荐的 `/docs` 在当前代码中被明确关闭，实测返回 404。
6. **质量基线**：复核交接记录中 22 项后端失败并建立适合目标操作系统的测试基线；再做真实连接器和人工业务验收。前端大包与已有警告可另列优化事项。

建议下一步使用原账号登录，验证已恢复模型的一次对话，再选择一个具体业务流程验收。
