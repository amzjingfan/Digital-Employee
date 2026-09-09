# Joukir 十分支集成与换机开发指南

日期：2026-09-09

集成分支：`integration/portable-development-20260909`

基线：`d637a20e5b05ba69b26b9df7f857d403745df8a6`

## 1. 交付结论

本快照在独立工作树中合并了五条“跨境电商智能运营 SaaS PRD v2.0”分支与五条“跨境电商数字员工部门平台 V1.7”分支。十条分支的 tip commit 均是最终集成分支的祖先；原始 `main`、运行中的源码目录和远端仓库没有被改写，也没有执行 push。

交付目录提供三种互补产物：

1. `Joukir-StaffDeck-git-20260909.bundle`：完整可重建 Git 历史，推荐用于换机继续开发。
2. `Joukir-StaffDeck-source-20260909.zip`：最终集成提交的干净源码快照，不含 `.git`。
3. `Joukir-development-docs-20260909.zip`：PRD、分支日志、运行手册、验证记录和 Git 清单。

所有产物都由同目录 `manifest.json` 描述，并由 `SHA256SUMS.txt` 提供 SHA-256。复制后先校验摘要，再开始开发。

## 2. 已纳入分支

| 分支 | tip commit | 集成方式 |
| --- | --- | --- |
| `prd/platform-foundation` | `a0b85b4a18d445c0a9def7a2d16d981d07d533b2` | merge `5377468` |
| `prd/bi-analytics` | `3cd6ac8ea28d806b7ead2c1f0dbd002693f37f2c` | merge `249f5de` |
| `prd/amazon-ads-pdca` | `a35d92238bb0d317c791fee1eba2857da9e93980` | merge `2457484` |
| `prd/social-operations` | `5ed925b18c3410e2aa3ab374b4f64a4bd715db8c` | merge `099e2d3` |
| `prd/offsite-channels` | `6a61ee870aede643d2b59bcc9164ce7a45d6a852` | merge `1356abf` |
| `workforce/platform-governance` | `c7774b7935ffabc6ba9847ac0a70f02a02f1a039` | merge `965e6e4` |
| `workforce/seven-role-workflows` | `38a12fc388ab2f190fe2ac19c758a964f0184a68` | 已包含于 UAT 聚合线 |
| `workforce/tiktok-department` | `16dd95817085d3e5047770730654f200a8dae878` | merge `8ba432b` |
| `workforce/connectors-assets` | `89327f2beac8c68378feaf268c7553b436a0fe5f` | merge `9a306f0` |
| `workforce/uat-release` | `be93027f65fe5948e691e954cf0ee4850fc0fa46` | merge `bf2cbd1` |

最终提交 SHA 不硬编码在提交自身；请用交付根目录 `manifest.json` 或恢复仓库后的 `git rev-parse HEAD` 核对。

## 3. 推荐恢复方式：Git bundle

以下命令保留完整历史和全部交付分支。路径按新电脑实际位置替换。

### Windows PowerShell

```powershell
git bundle verify .\Joukir-StaffDeck-git-20260909.bundle
git clone .\Joukir-StaffDeck-git-20260909.bundle .\joukir-enterprise
Set-Location .\joukir-enterprise
git switch integration/portable-development-20260909
git status --short --branch
git rev-parse HEAD
```

### macOS / Linux / WSL

```bash
git bundle verify ./Joukir-StaffDeck-git-20260909.bundle
git clone ./Joukir-StaffDeck-git-20260909.bundle ./joukir-enterprise
cd ./joukir-enterprise
git switch integration/portable-development-20260909
git status --short --branch
git rev-parse HEAD
```

若 `git clone` 因 bundle 含多个分支而未自动选择工作分支，可使用显式 fetch：

```bash
mkdir joukir-enterprise && cd joukir-enterprise
git init
git fetch ../Joukir-StaffDeck-git-20260909.bundle 'refs/heads/*:refs/heads/*'
git switch integration/portable-development-20260909
```

恢复后不要直接在旧 `main` 上继续。建议从集成提交创建新分支：

```bash
git switch -c development/post-integration
```

## 4. 源码 ZIP 的定位

源码 ZIP 是 `git archive` 从最终集成提交生成的确定性源码视图，适合审阅、代码扫描或没有 Git 的临时环境。它没有 `.git` 和分支历史；长期开发仍应使用 bundle。

解压后，应用代码位于 `source/`，平台基础设施位于 `deploy/staffdeck-platform/`，两套产品 PRD 的仓库内副本位于 `docs/prd/`。独立文档包还包含更完整的 SaaS v2.0 PRD 集合。

## 5. 新电脑环境重建

最低环境：

- Git
- Python 3.11 或更高版本
- Node.js 20 或更高版本及 npm
- 若使用 PostgreSQL/Casdoor 本地栈：Docker 兼容容器运行时；Windows 推荐 Rancher Desktop + WSL2
- 可选但推荐：`uv`

进入仓库的 `source/` 后，按项目自带 `README.zh.md` 重建依赖。不要复制旧电脑的虚拟环境、`node_modules` 或运行数据库。

### Windows PowerShell

```powershell
Set-Location .\source
py -3 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
npm --prefix frontend-enterprise ci
Copy-Item backend\.env.example backend\.env
```

### macOS / Linux / WSL

```bash
cd ./source
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e 'backend[dev]'
npm --prefix frontend-enterprise ci
cp backend/.env.example backend/.env
```

如果使用 `uv`，可在 `source/backend` 执行 `uv sync --extra dev --locked`。所有 Secret、模型 API Key、OAuth 凭据、数据库 URL 和回调验签材料都必须在新环境重新注入；交付包故意不包含这些内容。

## 6. 本地启动与最小验收

从 `source/` 执行：

```powershell
.\scripts\dev_up.ps1 --detach
curl.exe http://127.0.0.1:5173/api/health
```

或在 macOS/Linux/WSL 执行：

```bash
./scripts/dev_up.sh --detach
curl http://127.0.0.1:5173/api/health
```

预期健康响应为 `{"status":"ok"}`。随后打开 `http://127.0.0.1:5173/workspace/gallery`。生产型 PostgreSQL/Casdoor 环境的安装、迁移、回滚和 RLS 验证见 `deploy/staffdeck-platform/README.md`；不要把本机路径或旧凭据原样搬迁。

## 7. 建议验证矩阵

### 后端

```powershell
Set-Location .\source\backend
.\.venv\Scripts\python.exe -m compileall -q app
.\.venv\Scripts\python.exe -m pytest tests -q
```

macOS/Linux/WSL 将 Python 路径替换为 `.venv/bin/python`。广告执行相关专项测试只有在明确的 sandbox 配置下才应进入 queued 路径：

```text
BUSINESS_EXECUTION_ENABLED=true
BUSINESS_EXECUTION_MODE=sandbox
BUSINESS_EXECUTION_TENANT_IDS=tenant_demo
```

这些变量不得被误用于真实生产写入。

### 前端

```bash
cd source/frontend-enterprise
npm ci
npm test -- --run
npm run i18n:check
npm run config:check
npm run build
```

### 本交付快照的实测结果

| 检查 | 结果 |
| --- | --- |
| 后端全量 | `2207 passed, 22 failed, 12 skipped`，837.76 秒 |
| 后端集成专项 | 平台/BI 16、Amazon 12、社媒 6、站外 7、平台治理 20、UAT/TikTok 44、最终 TikTok 61，均通过 |
| Python 静态检查 | 67 个变更 Python 文件 Ruff `I,E9,F` 通过；`compileall` 通过 |
| 前端 Vitest | `64 files / 271 tests passed` |
| i18n | `4209` 条英文翻译覆盖通过 |
| 配置/构建 | Vite 配置检查与生产构建通过 |
| Live-write 门禁 | `ok=true`，23 routes / 12 Python / 12 Skills |
| UAT 生产证据 | 本机无真实外部证据，按设计退出 2、失败关闭 |

全量后端的 22 项不是本次集成专项回归失败，但仍是发布前必须处理或在正确 CI 平台复核的基线问题：3 项来自广告执行默认关闭，其余集中于 Windows 符号链接权限、进程终止与时序、POSIX/Bash/SIGALRM/fcntl 差异、Harness 路径/返回语义和 MCP stdio 本地编码。不要将此快照描述为“全量测试全绿”。

前端生产构建保留大于 500 kB chunk 的警告；依赖安装报告 2 个 moderate 级漏洞。交付阶段没有运行自动破坏性升级，换机后应评估依赖升级和代码分包。

## 8. 集成后的关键门禁

- 业务写入默认关闭，未经授权、审批、租户边界、幂等和审计不得开启。
- TikTok Live-write 冻结清单共 23 条路由；清单漂移必须由 CI 拦截。
- 生产就绪必须同时满足真实连接器证据和人工质量证据。人工评估不得增加官方连接器观察次数或掩盖连接器错误。
- 当前 TikTok 证据阈值为：至少 14 个不同 UTC 日期、零连接器错误、最终 heartbeat 合格；至少 30 次人工对比、采用率不低于 70%、5 类 SOP 覆盖且无严重 guardrail 问题。
- Mock、Seed、Replay、Sandbox、未配置接口和本地 CLI 成功都不等于真实 OAuth、回调、广告或渠道生产接通。
- 真实数据库迁移、备份恢复、外部授权、回调验签、长期观察窗和业务负责人 UAT 必须在目标环境另行完成。

## 9. 校验交付文件

PowerShell：

```powershell
Get-Content .\SHA256SUMS.txt
Get-FileHash .\Joukir-StaffDeck-git-20260909.bundle -Algorithm SHA256
Get-FileHash .\Joukir-StaffDeck-source-20260909.zip -Algorithm SHA256
Get-FileHash .\Joukir-development-docs-20260909.zip -Algorithm SHA256
```

macOS/Linux/WSL：

```bash
sha256sum -c SHA256SUMS.txt
```

再执行：

```bash
git bundle verify Joukir-StaffDeck-git-20260909.bundle
```

摘要、字节数、最终提交、分支清单和排除项扫描结果以 `manifest.json` 为准。
