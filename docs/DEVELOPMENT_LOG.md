# 开发记录

## 2026-09-11：规划新主仓库迁移（开始）

- 目标：在全新 `E:\develop\数字员工\joukir` 中保留全部功能源码与 Git 历史，提升 `source/` 为清晰仓库根，建立 GitHub Flow 与长期项目记忆。
- 范围：当前仓库 1,152 个 tracked 文件、44 次基线提交、运行配置边界、依赖重建、测试和新目录启动；旧交接目录不删除。
- 已知约束：`source/` 外的部署与 CI 文件属于功能资产；两层 `.github` 和 `docs` 需要合并；Secret、数据库、日志、PID、依赖和构建产物不进入 Git。
- 决定：用户确认保留现有完整 Git 历史，采用新增一次根目录迁移提交，不重写历史。
- 设计补充：用户要求新仓库使用独立根目录 `tests/`，所有可执行测试源码按 backend、frontend、integration、packaging 分类；技能包内 `evals` 作为发布数据保持自包含。

## 2026-09-11：编写主仓库迁移执行计划（开始）

- 目标：把已批准设计拆分为可验证、可提交、可回退的迁移任务，并立即按计划执行。
- 计划：独立克隆与基线、根目录提升、后端测试集中、前端测试集中、集成/打包测试集中、GitHub 与长期记忆、依赖/配置重建、功能验证和服务切换。
- 验收原则：每个原 tracked blob 都有新路径映射；完整测试对比交接基线；只有新目录健康后才切换 5173 Web 进程。

## 2026-09-09：接手分析与本地首次启动（开始）

- 目标：核对交付源码，安装锁定依赖，启动本地 Web 应用并验证登录和主要页面。
- 范围：从已核验 SHA-256 的 Git bundle 恢复到 `joukir-enterprise`；本地 SQLite 和新配置；保留原始交付包。
- 基线：`integration/portable-development-20260909`，提交 `e0cb8df042b3a5f856c60b45cf7e9c2bafbc23b5`。
- 已知阻碍：交付缺少文档引用的 `backend/.env.example`、开发记忆及部分 agents 文档；Python launcher 未注册运行时，但现有 Python 3.11.15 与 uv 可用；Docker 在当前权限下不可访问；旧数据库备份加密且本次未提供恢复密钥。
- 实施方式：按实际 `app/config.py` 创建仅本地使用的 `.env`，使用随机应用密钥；不启用外部业务写入；模型凭据暂未配置。
- 验证计划：锁定依赖安装、前端构建、服务健康、登录及核心 API、浏览器页面；记录未接通能力与复现命令。

## 2026-09-09：接手分析与本地首次启动（完成）

- 变更：新建本地 `.env`、虚拟环境、依赖、构建产物和 SQLite 演示库；新增仓库 `docs/LOCAL_STARTUP_20260909.md` 与本记录；应用源码未改动。
- 启动方式：隐藏后台运行 `backend/.venv/Scripts/python.exe -m uvicorn single_port_app:app --host 127.0.0.1 --port 5173`。自动审批拒绝原启动脚本的 `allowAllDomains` 沙箱补丁，改用已有文档支持的直接入口；未安装被拒绝的补丁。
- 验证：前端 64 文件 / 271 测试、i18n 4209 条、config 检查及构建通过；后端单端口、种子、角色、鉴权、BI 31 项通过。pytest 临时目录改为仓库内独立 basetemp 后退出 0。
- 运行验收：健康、页面、管理员登录、当前用户、11 个示例员工、任务列表、TikTok 概览与就绪接口均成功；浏览器验证员工档案和 TikTok 页面。
- 局限：模型未配置，旧 PostgreSQL/Casdoor 数据未恢复，TikTok 正式授权及生产模板未配置，命令执行沙箱未安装；生产就绪接口返回 false。当前代码关闭 Swagger，`/docs` 返回 404，与旧文档不符。
- 下一步：按启动记录配置模型、验收示例对话；取得独立备份密钥后规划数据恢复与真实连接器验收。全量后端测试失败基线另行处理。

## 2026-09-09：恢复交付数据库与原身份配置（开始）

- 目标：用户已提供独立密钥，验证加密备份并恢复 Casdoor、StaffDeck 与两个演练数据库，再切换本地应用验证原数据。
- 范围：新建仓库外受限运行目录及独立 Docker Compose 项目；保留现有 SQLite 演示库和配置以便回退。
- 已知环境：Docker 服务可用；现有 WhatsApp 数据库占用 55432；本次 PostgreSQL 拟使用 127.0.0.1:55433，Casdoor 拟使用 127.0.0.1:18000；不修改已有 CRM/WhatsApp 容器与卷。
- 验证计划：密文及明文 SHA-256、AES-GCM 认证、包内摘要、四库恢复、关键计数与角色/RLS、Casdoor 健康及 OIDC、后端健康和原模型配置解密。
- 安全边界：密钥与运行 Secret 不输出到日志；恢复新卷，外部任务和业务写入保持关闭；缺失的 MinIO 数据另行记录。

## 2026-09-09：恢复后代码与数据库版本对齐（开始）

- 已验证：Casdoor 和 StaffDeck 原始关键计数与备份一致；PostgreSQL 16.15、vector 0.8.6、125 张强制 RLS 表、运行角色租户隔离和原模型密钥解密通过。
- 启动阻碍：交付数据库仅有 27 条迁移记录，集成代码启动检查要求的 21 张新业务表缺失。
- 处理范围：只在隔离恢复的 `staffdeck_app` 执行仓库已有 20260908 五个正向迁移，覆盖品牌权限、BI、社媒、站外渠道、PDCA；保留原始 dump 和原始数据校验报告，不改动两个演练库。
- 另修复：备份中的初始化 shell 脚本为 CRLF，运行目录副本转换为 LF 后完成初始化；原始备份未更改。

## 2026-09-09 — 原库登录入口验证（开始）
目标：使用现有 VITE_OIDC_ENABLED 配置开放已恢复 Casdoor 的前端登录入口。范围：前端本机环境配置和构建产物；不修改业务源码。已知阻塞：当前产物在构建时关闭 OIDC，后台配置已验证启用。


## 2026-09-09：恢复后代码与数据库版本对齐（完成）

- 已在独立恢复的 staffdeck_app 执行五个现有事务迁移，补齐 21 张表，迁移数从 27 增至 32；新增表 owner 和 FORCE RLS 验证通过，强制 RLS 表共 146 张。
- 两个演练数据库均恢复完成，原始关键数据、owner、角色访问和 pgvector 版本匹配；原业务关键计数保持一致。
- 修正本机运行路径、数据库端口、OIDC 回调和 M2M 文件位置；原模型配置解密成功，未输出凭据，也未发起外部模型调用。

## 2026-09-09：原库登录入口验证与恢复交付（完成）

- 文件：前端 .env.local 启用 VITE_OIDC_ENABLED=true；后端 .env 切换为受限原库配置；仓库外 joukir-runtime 保存运行配置和无密钥内容的验证报告；更新 docs/LOCAL_STARTUP_20260909.md，新增 docs/DATABASE_RESTORE_20260909.md。应用业务源码未修改。
- 验证：前端 build、config:check、i18n:check 通过；浏览器从企业 SSO 入口进入 Casdoor 账号密码页；12 个活跃数字员工服务身份 client credentials 和 JWT 校验全部通过；仓库 PostgreSQL production gate 返回 ok=true。
- 最终状态：Web 健康 status=ok，OIDC enabled=true，页面和 Casdoor 健康接口 HTTP 200；独立 Casdoor/PostgreSQL 容器 healthy，分别仅监听本机 18000/55433；应用仅监听 5173。
- 清理：复核原密文 SHA-256 后删除本次临时明文 tar、解包及恢复日志目录；删除 PostgreSQL 容器中四个临时 dump。原密文、原恢复密钥、已恢复数据库及运行必需 Secret 保留。运行目录、后端 .env、恢复密钥共 48 个路径 ACL 验证仅允许 Administrator/SYSTEM。
- 版本控制：git diff --check 通过；后端 .env 与前端 .env.local 已被现有规则忽略；仅两份交付说明为新增未跟踪文件，未提交代码。
- 仍待验收：原人工账号完整登录、真实模型对话、第三方连接器和具体业务流程；MinIO 对象数据未随备份提供，Redis/Superset 未恢复。当前角色为 api，外部业务写入和自动执行关闭。
- 下一步：用户使用交接的原 Casdoor 账号登录，验证已恢复模型的一次对话，再选择具体业务流程验收。

## 2026-09-10：重新启动本机服务（开始）
- 目标：按用户要求重新启动现有 Joukir 原库环境。范围：本项目 PostgreSQL、Casdoor 和 Web/API；保留现有数据卷与配置。
- 当前阻碍：Docker Linux 引擎管道不存在，5173 无监听；先启动 Docker Desktop，再启动依赖及 Web。

- 启动诊断：PostgreSQL 日志显示上次运行被中断，正在启动恢复及 fsync；临时健康检查 unhealthy。等待原生恢复完成；暂时停止 Casdoor 重试，避免重复登录连接，不修改数据库或持久性参数。


## 2026-09-10：重新启动本机服务（完成）
- Docker Desktop 已启动。PostgreSQL 完成上次中断后的原生恢复，日志显示 ready to accept connections；PostgreSQL 和 Casdoor 均为 healthy。
- Web 隐藏后台启动 PID 39436，PID 文件已更新；日志位于 joukir-runtime/logs/web-20260910-161746.log 和 .err.log，原日志保留。
- 验证：应用健康 status=ok、OIDC enabled=true，应用入口与 Casdoor 健康接口均 HTTP 200。数据库、配置及业务源码未改动。

## 2026-09-11：建立 GitHub 工作流与长期项目记忆（开始）

- 目标：让新的 `joukir` 根仓库具备可审查的 GitHub Flow、与迁移后目录一致的 CI，以及可跨会话维护的项目记忆和交接入口。
- 范围：CI 路径和门禁、PR/贡献约定、项目记忆、当前会话交接、ADR、文档索引、Agent 规则及中英文 README 的迁移后指引。
- 约束：保留现有 CodeQL、发布和 Dependabot 文件内容；不配置占位远程；不记录凭据、连接串、Cookie、私钥或外部授权载荷；旧 Web、数据库容器和备份保持不动。
- 验证计划：解析工作流 YAML，执行 CI 对应的后端专项与前端门禁，审计内部 Markdown 链接和过时路径，检查 Git diff、Secret 模式及暂存产物。

## 2026-09-11：建立 GitHub 工作流与长期项目记忆（完成）

- 变更：CI 已切换到根级 backend/frontend/tests 路径并加入测试布局、前端配置、国际化和测试类型检查；新增 PR 模板、GitHub Flow 贡献指南、稳定项目记忆、当前会话交接、文档索引、ADR 0001 及 Agent 文档规则；更新 AGENTS 与中英文 README 的当前路径和安全说明。
- 后端验证：根测试布局检查通过；FastAPI 源码编译通过；CI 的 TikTok Ruff 路径通过；12 个回归模块共 61 项测试通过。
- 前端验证：`config:check`、4209 条英文翻译覆盖、测试 TypeScript 检查通过；64 个测试文件共 271 项测试通过；生产构建完成 2163 个模块，保留已知大分块提示。
- 文档与工作流：4 个工作流/Dependabot YAML 可解析；当前文档过时路径检查为 0；121 个 Markdown 文件的内部文件链接审计仅发现 PRD 对缺失交接文档 `lan-multiuser-codex-memory-2026.md` 的 4 处既有引用，该缺口已在文档索引明确说明。CodeQL、release、Dependabot 的 SHA-256 未变化。
- 剩余工作：Task 8 仍需执行全量后端对照、数据库生产门禁、最终来源/Secret 审计以及新目录 Web 切换和浏览器 SSO 验证；旧 Web 与 PostgreSQL/Casdoor 当前保持运行。

## 2026-09-11：新主目录最终验证与运行切换（开始）

- 目标：证明交接标签的 1,152 个 tracked 路径及迁移快照新增的设计/计划两份文档（合计 1,154 个索引路径）完整映射到新仓库，执行后端、前端、数据库和运行时门禁，并在全部切换前检查通过后让 `joukir` 接管本机 5173 端口。
- 范围：Git/来源映射、安全扫描、隔离测试、PostgreSQL 只读生产门禁、Web 进程精确切换、HTTP 与 OIDC/PKCE 浏览器烟测，以及最终验证和会话交接证据。
- 安全边界：pytest 仅使用仓库内忽略的 SQLite/临时目录；Secret、连接串和完整授权 URL 不写入输出；不停止 Docker，不修改备份，不执行 DesignKit 或第三方生产写入。
- 回滚条件：任何切换前门禁失败都保留旧 Web；切换后新 Web 若未通过健康检查，只停止已验证的新进程树并按原参数恢复旧 Web，PostgreSQL、Casdoor 和数据卷始终不动。

## 2026-09-12：新主目录最终验证与运行切换（完成）

- 源码完整性：`handover-20260909` 标签保留原 44 个提交；迁移快照 1,154 个路径全部映射到 `fc1dd45` 功能源码提交，大小写冲突、缺失、无法解释的内容和 mode 变化均为 0。1,056 个 blob 未变，98 项内容修改有复审提交依据，3 个 Shell 执行位修正经复审。映射表和复现工具位于 `docs/migration/`、`scripts/migration/`。
- 开发工作流预审修复：前端测试只接收实际会被收集和类型检查的 `*.test.ts(x)`；校正后端 README、启动健康地址及 3 个 Unix 脚本执行位。独立复审通过，定向后端测试 20/20 通过，前端测试类型检查、Ruff、布局守卫和 Bash 语法通过。
- 后端全量对照：新旧迁移基线均为 2,241 项、2,211 passed、21 failed、9 skipped、0 errors；失败、错误和跳过节点集合逐项一致，新目录独有失败为 0。两套环境 Python 分别为 3.12.13/3.11.15，Windows 临时目录绝对路径长度也不同；这些现存失败没有修复或被写成全绿。
- 其他门禁：前端配置/i18n（4,209 条英文覆盖）/测试类型检查、64 文件 271 测试及 2,163 模块生产构建均通过；TikTok mock SOP replay 5/5 且外部写入关闭；PostgreSQL production gate `ok=true`；新引入敏感文本候选和跟踪运行产物违规均为 0。
- 本机切换：精确验证旧 5173 进程身份后启动新目录 Web，PID 40608（启动器）/37160（监听），健康、数字员工广场、Casdoor 健康、OIDC 配置及 PKCE 重定向均通过；PostgreSQL/Casdoor 仍 `healthy`。浏览器确认已登录的数字员工广场和 Casdoor Password 页；既有 Admin 会话使本次未观察未登录 SSO 按钮，也未输入凭据。
- 备份和保留：外置加密包 SHA-256 与交接值一致，独立 key 存在且 ACL 仅 Administrator/SYSTEM；未读取 key 内容。交接仓库、备份、容器卷及外置 runtime 保留；新仓库未配置 GitHub remote。
- 详细命令、计数、比较边界及未验收功能见 `docs/migration/VERIFICATION_20260911.md`；当前后续工作接力以 `docs/SESSION_HANDOFF.md` 为准。
- 本地 Git 集成：Task 8 与整分支独立复审通过后，以 `--ff-only` 将 `main` 从 `9cc0327` 快进至 `df310e5`；随后只更新最终仓库状态说明，保留迁移功能分支并使其与 `main` 保持同一最新提交。未添加远程或执行 push。

## 2026-09-12 — 项目全功能审计与现状报告（开始）

- 目标：在当前 Windows 本地恢复环境中执行仓库可安全运行的后端、前端、集成、数据库、权限和 UI 验证，并生成根目录 报告.md。
- 范围：只读或 Mock/隔离测试；核对源码模块、SOP、运行服务、业务数据、测试证据和 Git 状态。
- 已知阻塞：真人 Casdoor 最终验收、真实第三方授权/写入、缺失的 MinIO/Redis/Superset 数据、macOS/Linux 打包和签名不在当前自动验收能力内；既有后端基线含 21 个失败。
- 安全边界：不打印或写入密码、Token、密钥、完整连接串、Cookie、个人敏感数据或原始授权载荷；不停止或删除恢复数据库。

## 2026-09-12 — 项目功能审计与现状报告（完成）

- 文件：新增根目录 `报告.md`，更新 `docs/README.md` 索引及 `docs/SESSION_HANDOFF.md`，并在本日志追加本条完成记录；未修改业务源码、迁移、恢复卷、备份或 Secret。
- 源码与前端：`scripts/migration/verify_source_map.py` 为 1,154/1,154 路径、无缺失或无法解释改动；`tests/check_test_layout.py` 通过。前端 `config:check`、`i18n:check`、`test:typecheck`、64 文件 271 项 Vitest 和 2,163 模块构建通过。
- 后端：`pytest -c pytest.ini tests/backend` 收集 2,244 项，2,200 passed、35 failed、9 skipped、0 errors；21 个历史稳定失败重现，另外 14 个在隔离复跑时 13 个通过、微信恢复用例表现为间歇性。`ruff check backend` 退出 1，有 1,844 项存量问题。原始 JUnit/摘要存于被忽略的 `.dev/functional-audit-20260912/`。
- 集成与数据：Web、Casdoor、PostgreSQL 恢复并健康，OIDC/PKCE 跳转、PostgreSQL 生产门禁、跨租户读写拒绝、12/12 M2M 身份（回环绕过系统代理）、真实默认模型最小文本请求、TikTok Mock SOP 5/5 与异常 30/30 通过。M2M 的默认 HTTPX 受 Windows 系统代理影响返回 502，属于待修的本机运行风险。
- 数据快照：2026-09-12 16:34 北京时间只读事务中有 149 张 public 表、74 张非空、4,863 行；10 个已发布、14 个草稿员工。TikTok Shadow 有 1 条 `running` 记录，但 0 次观测且无后续心跳，本地开关关闭；不构成 14 天真实业务验收。数据在审计期间变化，操作者/进程未核实。
- 限制：浏览器自动化连接失败，未完成真人登录、多角色页面与端到端交互；真实第三方授权/写入、MinIO 对象、完整模型对话、macOS/Linux 包和签名仍未验收。报告只写实测与缺口，不作为生产发布批准。
- 文档复核：独立审阅核对测试统计、主要数据、12 个内部文件链接与敏感文本；修正了变化中的数据库计数和报告标题。`git diff --check` 与安全扫描通过；本地分支经审阅后纳入 `main`，无 GitHub remote 与远端 PR。
- 下一步：按 `报告.md` 的优先级先解决稳定后端失败和本机代理/M2M，补真人与真实数据的业务闭环，再由维护者提供真实 GitHub 地址以建立远端 CI/PR。

## 2026-09-12 — 归类项目文档（开始）

- 目标：把本轮功能审计报告和根目录的历史设计、备份范围及开发记录归入 `docs/` 下的对应分类，保持根目录为项目入口。
- 范围：仅移动 Markdown 文档并修正索引、相对链接和会话交接；不修改功能源码、测试、备份或运行配置。
- 已知风险：审计报告从根目录移动后其相对链接必须重新计算；历史文档路径已被索引引用，需同步更新并验证。

## 2026-09-12 — 归类项目文档（完成）

- 文件：将审计报告移至 `docs/reports/报告.md`，备份范围移至 `docs/operations/`，三份设计文档移至 `docs/design/`，飞书开发记录移至 `docs/development-branches/`；同步更新报告内相对链接、`docs/README.md` 索引、`docs/SESSION_HANDOFF.md` 和 `AGENTS.md`/`docs/PROJECT_MEMORY.md` 的后续文档归类约定。根目录现仅保留 README、AGENTS 和 CONTRIBUTING 四份入口 Markdown。
- 验证：分类后的 7 份文档共检查到 0 个失效相对文件链接；`tests/check_test_layout.py` 通过（1,185 个 tracked 路径）；`scripts/migration/verify_source_map.py` 仍为 1,154/1,154 且无无法解释改动；`git diff --check` 通过。业务源码和数据库未变，不重跑与文档路径无关的完整功能套件。
- 仍需关注：历史迁移索引和旧实施计划保留原路径作为当时快照，不随本次分类改写。后续新增叙述性文档应按类别放入 `docs/` 并登记索引。
- 下一步：继续按 `docs/reports/报告.md` 的功能缺口开展专项开发和真实业务验收。

## 2026-09-12 — 补充归档历史 Agent 报告（开始）

- 目标与范围：将 `.agent/reports/` 中仅作历史证据的三份生成报告移至 `docs/reports/`，更新文档索引；这些文件没有 Markdown 相对链接，也未被运行代码引用。
- 已知风险：迁移来源索引保留旧路径，属于历史快照；实际文档索引需指向新路径。

## 2026-09-12 — 补充归档历史 Agent 报告（完成）

- 文件：三份历史 Agent 报告原文从 `.agent/reports/` 移至 `docs/reports/`；`docs/README.md` 的三处索引链接已更新。原文未改，业务源码及运行配置未改。
- 验证：原文无相对 Markdown 链接；归档索引指向的新文件均存在。与上一归档步骤一起执行路径、链接、Git 差异及敏感信息门禁。
- 后续：新生成的项目报告统一放 `docs/reports/` 并在 `docs/README.md` 登记。

## 2026-09-12 — 归档最新总 PRD 与 TikTok 模块 PRD（开始）

- 目标：保存用户提供的跨境数字员工总 PRD V1.8 和 TikTok 事业部模块 PRD V1.8，并基于当前项目代码梳理 TikTok 负责人的下一步。
- 范围：仅更新 `docs/prd/` 中的当前产品需求、`docs/README.md` 索引及本次文档交接记录；对 TikTok 代码、测试和现有审计做只读核验。
- 已知阻塞：真实 TikTok 授权、生产数据、第三方写入和真人验收尚无本次可确认的证据；当前后端全量测试存在已记录的失败基线。
- 安全边界：不读取或记录运行时凭据、原始授权载荷、完整个人信息，也不触发第三方写入或改动恢复中的服务和数据。

## 2026-09-12 — 归档最新总 PRD 与 TikTok 模块 PRD（完成）

- 文件：将用户提供的总 PRD V1.8 原样更新到 `docs/prd/crossborder-digital-workforce-prd-2026.md`，原样新增 `docs/prd/tiktok-business-unit-module-prd-v1.8.md`；更新 `docs/README.md` 索引和 `docs/SESSION_HANDOFF.md` 的分阶段接力事项。本日志仅追加本次起止记录，未改业务源码、迁移、测试或运行配置。
- 验证：两份归档文件与各自桌面原件的 SHA-256 完全一致；针对常见密钥、凭据、邮箱和手机号形态的扫描各有 0 个候选；`backend\.venv\Scripts\python.exe tests\check_test_layout.py` 通过（1,185 个 tracked 路径）；`git diff --check` 通过。新增及更新索引的相对链接可解析；两处未解析引用均指向仓库原本缺失且已在索引说明的 `lan-multiuser-codex-memory-2026.md`。本次是文档变更，没有重跑无关的后端或前端全量功能套件。
- 代码核查：P3-A 目前主要是组织、权限、只读 Seller 权限摘要、六 Tab 页面及确定性 Mock 回放；P3-B 看板/履约/指标接口尚未实现。静态检查提示租户无关的初始化主键及官方授权就绪误判风险，需要通过聚焦回归测试复现并修正，不能把该检查当作已完成真实授权验收。
- 剩余风险：总 PRD 的广义 12-SOP/逐岗位样本要求与其 P3-A 优先章节及模块 PRD 的五条主 SOP/30 条人工对照口径需产品确认；样品七天按自然日还是工作日也有待决项。真实授权、30 条人工对照、连续 14 天影子运行和外部写放行均缺证据。
- 下一步：先推进 P3-B0 的试点店铺/字段 Owner/接口能力矩阵与只读证据，同时补双租户和不可用授权回归；随后按 E01/E02/E07 开发 P3-B1，并独立完成 P3-A 人工影子验收。

## 2026-09-14 — TikTok P3-B0 接入阻塞核对（开始）

- 目标：核实美国跨境试点前的 App 类别、只读 API 范围、Development Shop、真实店授权证据和 Joukir 回调条件。
- 范围：Partner Center 与本地源码、运行状态只读核对；仅更新现有交接与开发日志，不修改外部权限、店铺授权、密钥、业务代码或恢复环境。
- 已知阻塞：联盟读取范围未在当前 App 列表显示；真实店授权状态未获证实；本机运行配置受 ACL 保护，无法检查其值。

## 2026-09-14 — TikTok P3-B0 接入阻塞核对（完成）

- 文件：更新 `docs/SESSION_HANDOFF.md`，记录已登录 Partner Center、Development Shop、本地源码与运行端口的分层证据；本日志仅追加本次起止记录。未修改 API 范围、App 类别、OAuth 回调、店铺授权、运行凭据或业务代码。
- 平台事实：`joukir` 为启用中的美国跨境自定义商家 App，Manage API 为 27 个可见范围、0 个生效；店铺及订单读取开关关闭，联盟包名和样品 API 名未检索到。`tkw api` 同为自定义商家 App，页面显示 0 个生效范围且没有回调地址；它不是已验证的替代方案。美国 Development Shop 有两个活跃的本地类型测试账号，不构成跨境真实店验证。授权商家统计为不适用，无法确认实际授权。
- 本地事实：已登记的 `joukir` 回调指向本机 5173 端口；本次端口查询未见 5173、8000、55433、18000 监听。受 ACL 限制，未读取忽略的 `.env`；Docker API 查询被拒绝，未改动或重建任何恢复服务。源码官方 OAuth 只读 Scope 白名单未包含联盟读取，现有 live Connector 仅读取 Seller 权限摘要。
- 验证：只读浏览器检查和源码核查完成；`git diff --check` 通过。未执行接口请求或真实数据对账，因此 P3-B0 能力等级与生产授权均未提升。自动审批审查拒绝点击测试店铺 `Authorize app`，理由是该入口可能直接扩展 App 对店铺数据的持续访问；未尝试绕过。
- 剩余风险与下一步：需确认试点 App、向 Partner Center/Partner Manager 核实联盟读取准入，明确最小权限并取得授权后再修改 App；提供可达 HTTPS 回调及受控运行环境；随后先测 Development Shop 契约、再测真实美国跨境店，只读对账需指定达人 BD 与数据口径 Owner。

## 2026-09-14 — joukir 店铺只读范围发布核对（开始）

- 目标：按用户对 `seller.shop.info` 完整范围的明确授权，在 Partner Center 为 `joukir` 开启并发布该范围，核实最终生效状态。
- 范围：仅处理 `seller.shop.info`，其页面展开项包含 Seller 权限、活跃店铺列表及全球仓库读取；不启用订单、联盟或任何写入范围，不授权测试店铺或真实店铺。
- 已知阻塞：浏览器连接可能中断；发布和生效必须以平台返回状态核实，单纯切换开关不能视为完成。

## 2026-09-14 — joukir 店铺只读范围发布核对（未完成）

- 文件：仅追加本日志并更新 `docs/SESSION_HANDOFF.md`；未修改业务源码、配置或凭据。
- 平台动作与证据：在用户明确授权完整范围后，Partner Center 的 `joukir` Manage API 中将 `seller.shop.info` 开关切到开启，随后页面显示 `生效 1 / 未生效 26`。尚未看到 `发布更改` 操作成功，也未重载复核持久状态，不能宣称权限已发布或实际可调用。
- 阻塞核查：计算机浏览器桥接连续返回 `nodeRepl.fetch request failed`；重置后仍无法连接。TTS Open Toolkit `auth status --json` 返回 `authenticated: false`，固定 DevAPI 清单没有权限发布方法；未尝试借用浏览器凭据或绕过工具允许范围。
- 验证：`git diff --check`；本轮无代码或数据测试。订单、联盟、写入范围及店铺授权均未操作。
- 下一步：浏览器恢复后在 `joukir` Manage API 复查该开关和待发布状态，按现有用户授权仅发布 `seller.shop.info`，刷新页面验证；如用户先手工发布，需读取页面结果再更新证据。其余平台及数据合同阻塞仍按交接文件推进。

## 2026-09-14 — 接收店铺只读范围页面证据（开始）

- 目标与范围：核对用户提供的 Partner Center 截图，更新 `seller.shop.info` 状态证据；仅修改交接与日志，不操作外部权限。
- 已知限制：截图为页面局部，未包含刷新过程、发布操作结果或实际 API 响应。

## 2026-09-14 — 接收店铺只读范围页面证据（完成）

- 文件：更新 `docs/SESSION_HANDOFF.md` 并追加本日志；没有改动业务代码、配置或外部权限。
- 截图事实：`seller.shop.info`（Global Shop Information，Scope ID 431300）显示在“生效 1”列表中，开关为开启；“未生效 26”“审核中 0”“未获批准 0”。这覆盖此前“生效 0”的旧页面状态。
- 证据边界：截图没有显示刷新前后对比、`发布更改` 提交结果、店铺 OAuth 授权或成功 API 响应，因此只确认页面展示的范围状态，不确认持久性或真实数据可读。浏览器桥接仍无法连通，未进行独立页面复核。
- 验证：`git diff --check`；文档修改不涉及功能测试。下一步请刷新 Manage API 并核对该范围仍在“生效”，再继续店铺授权和只读接口验证。

## 2026-09-14 — 确认刷新后店铺只读范围状态（开始）

- 目标与范围：根据用户对截图拍摄时机的补充，修正 `seller.shop.info` 的页面持久状态判断；仅更新交接和开发日志。
- 已知限制：未收到店铺 OAuth 授权或成功只读 API 响应；“生效”页面状态不能替代数据验证。

## 2026-09-14 — 确认刷新后店铺只读范围状态（完成）

- 用户确认前述截图是在 Manage API 页面刷新后取得。结合截图的“生效 1”、`seller.shop.info` 开关开启，确认该权限包在刷新后仍显示为生效；无需再把发布状态列为待确认。未观察到具体发布点击事件，不能据此推断店铺已授权或接口已返回数据。
- 文件：仅更新 `docs/SESSION_HANDOFF.md` 并追加本日志；没有改动其他权限、店铺授权、配置或业务代码。
- 验证：`git diff --check`；本轮没有接口请求或功能测试。下一步核对授权店铺与只读 API 数据，再解决联盟/样品读取权限的准入问题。

## 2026-09-14 — 美国跨境真实店授权核对（开始）

- 目标：依据用户“美国跨境真实店铺授权已完成”的反馈，核查 Joukir 是否收到官方 OAuth 回调、是否有可用的店铺授权记录及只读接口验证条件。
- 范围：只读检查 Partner Center 可用状态、本地服务端口和项目授权/Connector 代码；仅更新交接与日志，不读取或记录任何令牌、授权码、密钥、Cookie 或原始授权载荷。
- 已知阻塞：浏览器桥接此前不可用；项目运行端口和 OAuth 回调环境可能不在线；用户口述授权完成不能单独证明 Joukir 已存储有效凭据。

## 2026-09-14 — staging OAuth 重定向地址准备（开始）

- 目标：为 `joukir` 准备真实美国跨境店授权使用的 HTTPS 回调，并在可验证的部署和 Partner Center 环境中完成一致配置。
- 范围：核对用户提供的 `staging.overselfx.com`、现有回调代码路径、DNS/HTTPS 健康状态、部署入口和平台修改能力；不打印或存储授权码、令牌、密钥或完整授权 URL。
- 已知阻塞：该域名的 `/api/health` 在用户浏览器中无法连接；当前主机对 443 的连接超时，远程服务器无预置连接；Partner Center 浏览器桥接仍报错。先验证入口再切换正式 OAuth 回调，避免把授权导向不可用地址。

## 2026-09-14 — 本机官方只读授权运行配置（开始）

- 目标：按用户选择的本机路径，使已登记的 `127.0.0.1:5173` 官方 OAuth 回调具备真实授权与只读验证条件。
- 范围：先启动本机单端口应用和健康检查，再仅设置现有受保护 `backend/.env` 中 `TIKTOK_OFFICIAL_ENABLED`、`TIKTOK_CONNECTOR_MODE`、`TIKTOK_SERVICE_ID` 三个非密钥字段；不读取或输出 App Secret、Token、完整授权 URL，也不修改外部写入权限。
- 已知阻塞：当前配置官方授权关闭、Connector 为 Mock、Service ID 缺失；Token Store 文件及父目录尚不存在，授权兑换时需验证可创建。用户此前所述“成功回跳”不能归因于此时的本机运行实例。

## 2026-09-14 — 美国跨境真实店授权核对（未完成）

- 用户先报告已完成真实美国跨境店授权并跳回 Joukir 显示成功；随后提出需要设置重定向地址。由于当时本机 Joukir 未运行且官方授权配置关闭，无法把这一报告归因于当前本机实例，也未独立读到授权记录。
- 源码核查：官方回调会交换授权码、读取授权店铺并提交授权记录后才返回成功；`GET /api/enterprise/tiktok/overview` 包含当前租户的授权摘要，`GET /api/enterprise/tiktok/connector/read` 在 live 模式下只读 Seller 权限摘要。本次未取得授权摘要或真实 API 响应。
- 验证：浏览器桥接持续失败；当时 5173、8000、55433、18000 无监听。未读取或记录任何 OAuth 敏感值。后续以当前本机实例的新授权流程为准。

## 2026-09-14 — staging OAuth 重定向地址准备（暂缓）

- 候选 URL：`https://staging.overselfx.com/api/enterprise/tiktok/authorizations/official/callback`，路径与项目后端路由一致。DNS 可解析，但本机到 443 超时，用户在浏览器访问 `/api/health` 也无法连接。
- 用户确认该域名指向另一台尚未部署 Joukir 的服务器，并选择先用本机回调验证数据；因此未把 Partner Center 或本地运行配置切换到 staging。没有远程服务器预配置连接，也未更改 DNS、证书或远程服务。
- 下一步：待 staging 上部署 Joukir、443/TLS 与 `/api` 路由可达，再将 Partner Center Redirect URL 和该环境 `TIKTOK_REDIRECT_URI` 同时设为候选 URL，重新走 OAuth。不能将未部署域名作为当前有效回调。

## 2026-09-14 — 本机官方只读授权运行配置（完成，待 OAuth）

- 本机运行：复核启动脚本后启动单端口 Joukir；已存在的 PostgreSQL 和 Casdoor 容器经只读检查均 healthy，没有重建或删除数据。前端构建通过（2,163 个模块）。重启后 5173 监听，`/api/health` 返回 HTTP 200 和 `九骥 Joukir`。
- 配置：仅在已有的受保护、Git 忽略的 `backend/.env` 中设置 `TIKTOK_OFFICIAL_ENABLED=true`、`TIKTOK_CONNECTOR_MODE=live`、`TIKTOK_SERVICE_ID=7681639610544228117`。App Key/Secret 已存在且未输出或改动；本机回调与 Partner Center 登记值一致。重启后官方客户端配置校验通过；未带认证访问回调返回 401。Token Store 路径已配置，其文件和父目录在 OAuth 前尚不存在。
- 文件：更新 `docs/SESSION_HANDOFF.md` 并追加本日志；业务源码、迁移和测试未变。运行配置及构建产物保持被 Git 忽略。
- 剩余风险：浏览器桥接仍不可用，无法代用户完成带身份的官方 OAuth，也未验证授权记录或只读 API；用户需在当前本机 Joukir 管理员会话点击“连接 TikTok 官方店铺”并批准真实店铺，随后再核对授权和只读数据。当前权限仅支持 Seller 权限摘要，尚不能验证样品/联盟订单/GMV/视频数据。

## 2026-09-14 — 按用户要求暂停并关闭本机 Joukir（开始）

- 目标：停止本轮启动的本机 Joukir，保存目前核验边界，待用户日后部署 staging 后继续。
- 范围：仅停止 `scripts/dev.py` 管理的本机应用/监督进程并更新交接与日志；保留 PostgreSQL/Casdoor 恢复容器、数据库和受保护运行配置。
- 已知限制：用户报告成功回跳和页面存在 `seller · active`，但尚无本机 Token Store 或成功回调/API 读的独立证据；不能据此宣布真实数据接通。

## 2026-09-14 — 按用户要求暂停并关闭本机 Joukir（完成）

- OAuth 核验边界：本机配置的 Token Store 文件在最后检查时仍不存在。当前应用启动后的官方授权启动请求有 4 次（状态 503、503、503、200）；官方回调日志只有本轮未登录探测的一次 401，未观察到成功回调。没有输出带 code/state 的原始日志，也未读取令牌。用户所见 `seller · active` 可能是旧记录或其他实例，原因待部署后再查。
- 关闭验证：执行 `scripts/dev.py down` 后，`scripts/dev.py status` 显示 supervisor/app 均未运行、5173 可用、健康接口不可达；没有停止或修改现有 PostgreSQL/Casdoor 容器。
- 文件：更新 `docs/SESSION_HANDOFF.md` 并追加本日志；Git 跟踪文件仅这两份文档改动。本机忽略的 `backend/.env` 保留本轮设置的三个非密钥 TikTok 字段，应用已停止。
- 下一步：待用户部署 staging、HTTPS 443 与 `/api/health` 可达后，同步设置该环境和 Partner Center 的精确 HTTPS 回调，再从部署后的 Joukir 重新授权并验证授权记录与只读接口。暂停期间不再执行平台或本机操作。

## 2026-09-17 — 将可执行项目区域迁入 `src/`（开始）

- 目标：按用户确认的范围，把 `backend`、`frontend-enterprise`、`scripts`、`tests`、`skills`、`deploy`、`packaging` 迁入根级 `src/`，保持开发、测试、打包和单端口运行能力，并在验证后合并当前功能分支到 `main`。
- 范围：迁移完整目录及其被忽略的本地依赖/运行配置；修正根配置、CI、发布、生命周期脚本、测试和当前文档中的有效路径；历史证据文件只在影响当前工具执行时调整。
- 已知基线：当前分支为 `codex/prd-tiktok-v1-8`；此前 TikTok PRD 与本机授权核验记录已分别提交。应用当前处于停止状态；`backend/.env`、后端虚拟环境和前端依赖均为 Git 忽略内容，迁移期间不得输出配置值或加入版本控制。
- 设计与计划：`docs/superpowers/specs/2026-09-17-src-layout-migration-design.md`、`docs/superpowers/plans/2026-09-17-src-layout-migration.md`。

## 2026-09-17 — `src/` 目录迁移与路径修复（完成）

- 目录：完整移动 `backend`、`frontend-enterprise`、`scripts`、`tests`、`skills`、`deploy`、`packaging` 到 `src/`；根目录保留文档、治理、CI 元数据和仓库级配置。被忽略的 `src/backend/.env`、虚拟环境、前端依赖和构建输出随所属模块移动，未读取配置值。
- 路径：更新根级 pytest/Ruff/Git ignore 配置、GitHub CI/发布/Dependabot、生命周期 `.dev` 位置、测试布局门禁、迁移证据工具、部署回滚脚本、当前开发文档和用户可见命令。源代码内部以 `src/` 作为共同源根，保留后端、前端、测试、打包之间原有的兄弟目录关系。
- 安全检查：移动前确认七个源目录和目标均位于仓库内且目标不存在；移动后 `src/backend/.env`、`src/backend/.venv`、`src/frontend-enterprise/node_modules`、`src/frontend-enterprise/.env.local` 仍由 Git ignore 规则覆盖。
- 下一步：暂存迁移以让基于 `git ls-files` 的布局门禁观察新路径，然后运行静态、后端、前端和真实启动验证；对发现的路径回归逐项修复。

## 2026-09-17 — `src/` 迁移验证（开始）

- 目标：证明新路径下的 Python 导入、测试布局、后端回归、前端检查/构建、打包路径和单端口启动均可用。
- 范围：只运行本地构建、测试、只读健康检查和生命周期启停；不执行外部 TikTok 写入、OAuth 授权、数据库重建或平台发布。
- 已知限制：完整后端套件在迁移前的项目交接中存在已记录的环境相关失败；本轮首先检查目录迁移引入的新失败，并以实际启动/健康结果验证主要运行链路。

## 2026-09-17 — `src/` 迁移验证（完成）

- 布局与静态检查：新门禁检查 1,188 个 Git 跟踪路径并通过，禁止七个旧根目录重新出现项目文件；Python `compileall -f` 通过；GitHub YAML 和全部 PowerShell 脚本可解析；CI 使用的 Ruff 专项检查通过。全树 Ruff 仍报告 2,203 项存量问题（本次扫描还包含测试与脚本），未把该存量债务描述成迁移回归或全绿。
- 后端：目录/生命周期/路径/打包专项 36 项通过；TikTok CI 回归 61 项通过。完整套件收集 2,244 项，约 12% 后遇到既有长耗时用例而停止；此前出现的 4 项失败为 3 项已有广告执行门禁失败和 1 项 Windows 符号链接权限失败，与现有审计分类一致。本轮没有以未完成的全量运行宣称全绿。
- 前端：配置检查、4,209 条英文翻译覆盖、测试类型检查、64 个 Vitest 文件/271 项测试和 2,163 模块生产构建全部通过。受 ACL 保护的 `.env.local` 只由授权的本机构建进程读取，没有输出内容。
- 运行：通过 `src/scripts/dev_up.ps1 --detach` 成功启动；监督进程和应用进程运行，5173 监听，`/api/health` 返回 `status=ok`/`九骥 Joukir`，`/chat/` 与 `/enterprise/dashboard` 均为 HTTP 200。随后执行 `src/scripts/dev_down.ps1`，最终监督进程和应用进程均停止、5173 可用、健康接口不可达，符合停止状态。
- 证据与安全：历史迁移源映射仍为 1,154/1,154、无缺失/碰撞/未解释编辑；工作树安全扫描新增敏感候选 0、跟踪运行产物 0。Windows Sandbox Runtime smoke 在受限宿主仅 network-deny/artifact 通过，其余网络或文件隔离检查失败，不作为本次目录迁移的通过证据；Linux/macOS 打包仍需目标平台。
- 剩余风险：完整后端套件和全树 Ruff 仍有已记录的存量失败/债务；平台专属安装包未在非本机平台构建。新目录的核心构建、专项回归和真实单端口启动均已验证。
- 下一步：复核 staged diff 和忽略文件边界，提交 `src/` 迁移，将 `codex/prd-tiktok-v1-8` 快进合并到本地 `main`，再刷新最终分支交接状态。

## 2026-09-17 — 提交、合并与最终交接（完成）

- 目标与范围：提交已验证的 `src/` 迁移并按用户要求整合到本地 `main`；仅更新 Git 分支和最终交接状态，不推送远程、不执行外部发布。
- 提交：`8e2e6b3 refactor: move project code under src`，包含 1,129 个 Git 重命名、17 个路径/文档修改和 2 个设计/计划文档新增。提交前 `git diff --cached --check` 通过，旧根项目路径为 0，暂存的受保护运行文件为 0，安全扫描新增敏感候选为 0。
- 合并：确认 `main` 是当前功能分支祖先后，将 `main` 快进到 `8e2e6b3` 并切换到 `main`；历史保持线性，没有合并提交或强制重写已合并提交。
- 最终状态：本地 `main` 已包含 V1.8 PRD、TikTok 核验记录和 `src/` 迁移。Joukir 应用保持停止，5173 可用；没有配置远程，因此没有推送、PR 或外部部署。

## 2026-09-17 — 启动完整本地项目（开始）

- 目标：按用户要求启动 `src/` 迁移后的完整 Joukir 单端口开发运行环境，并验证进程、端口、健康接口和主要页面。
- 范围：使用现有本地运行配置执行 `src/scripts/dev_up.ps1 --detach`；不修改数据库结构、外部平台权限或受保护配置内容。
- 已知限制：启动会读取 Git 忽略的本地环境配置；验证过程不得输出其中的密钥或令牌。

## 2026-09-17 — 启动完整本地项目（完成）

- 运行结果：`src/scripts/dev_up.ps1 --detach` 完成前端生产构建（2,163 个模块），监督进程 PID 54852、应用进程 PID 69388 均运行，端口 5173 正在监听。
- 验证结果：`src/scripts/dev_status.ps1` 报告健康状态为 `ok`；`GET /api/health` 返回 `status=ok` 和 `九骥 Joukir`，`/chat/` 与 `/enterprise/dashboard` 均返回 HTTP 200。
- 变更与风险：没有修改业务代码、数据库结构或外部平台权限；仅追加本运行记录。构建存在既有的大分块性能警告，不影响本次启动。服务按用户要求保持运行。
- 下一步：本地访问 `http://127.0.0.1:5173/chat/` 或 `http://127.0.0.1:5173/enterprise/dashboard`；不再需要时执行 `src/scripts/dev_down.ps1`。

## 2026-09-18 — Casdoor 生产认证加固设计（开始）

- 目标：按用户确认的最小方案设计现有标准 OIDC 集成的单点退出、生产 HTTPS 门禁和安全管理员初始化；不引入 Casdoor React/Python SDK。
- 范围：仅新增设计文档并更新文档索引；保留本机开发环境的 `admin / admin`，生产环境禁止默认密码和不安全 OIDC 配置；本步骤不修改生产代码、运行配置、数据库账号或 Casdoor 状态。
- 已知约束：当前 Joukir 仅清除本地会话，尚未执行 Casdoor RP-Initiated Logout；Casdoor access token 未持久化，设计应避免新增敏感令牌存储；生产域名和管理员密码由部署时安全注入，不能写入仓库。

## 2026-09-18 — Casdoor 生产认证加固设计（完成）

- 文件：新增 `docs/superpowers/specs/2026-09-18-casdoor-production-auth-hardening-design.md`，并在 `docs/README.md` 的当前设计区建立索引；生产代码、运行配置、数据库和 Casdoor 状态均未修改。
- 设计结论：采用浏览器前通道 RP-Initiated Logout、显式 `development`/`production` 配置门禁和独立紧急管理员初始化命令；不持久化 Casdoor token，不引入 Casdoor SDK，开发环境继续允许现有默认账号，生产环境拒绝不安全 HTTPS/Cookie/密钥/演示种子配置。
- 验证：设计文档 180 行，目标、非目标、测试策略和验收条件均存在；占位符扫描为 0；文档索引命中；`git diff --check` 未报告内容错误，仅提示现有 Windows 行尾转换策略。
- 剩余步骤：等待用户审阅书面设计；确认后再编写逐步实施计划并进入红绿 TDD，不在设计确认前修改认证代码。

## 2026-09-18 — Casdoor 生产认证加固实施计划（开始）

- 目标：把已批准的生产认证加固设计拆解为逐项可验证的 TDD 实施计划，覆盖运行时生产门禁、OIDC 单点退出、前端统一退出、Casdoor 应用配置和紧急管理员初始化。
- 范围：仅新增实施计划并更新文档索引/开发日志；不修改生产代码、运行配置、数据库账号或外部 Casdoor 状态。
- 已知约束：计划必须保留本机开发默认账号，不持久化 Casdoor token，不引入 Casdoor SDK；每个行为变更先写失败测试并观察预期失败，最终验证需包含后端、前端、配置、构建与本机启动检查。

## 2026-09-18 — Casdoor 生产认证加固实施计划（完成）

- 文件：新增 `docs/superpowers/plans/2026-09-18-casdoor-production-auth-hardening.md`，并在 `docs/README.md` 当前设计区建立索引；未修改认证生产代码、受保护配置、数据库账号或 Casdoor 状态。
- 计划结构：共 7 个按依赖排序的红绿 TDD 任务，依次覆盖生产启动门禁、后端 OIDC 注销准备、前端统一退出、Casdoor 公网地址配置、紧急管理员初始化、运维文档和集成验证；每项都列出精确文件、失败/通过命令、预期结果和独立提交边界。
- 自检：核对了现有 Settings、启动顺序、OIDC 路由、前端 `auth_mode`/API 客户端、Vitest 路径、部署脚本和 SQLModel 用户字段；修正了实际测试文件名、Vitest 过滤参数和一次性生产负向探测的工作目录。计划未包含 `TODO`、`TBD` 或省略号占位符，`git diff --check` 未报告内容错误，仅提示现有 Windows 行尾转换策略。
- 下一步：等待用户选择在当前任务内逐项执行，或显式要求使用独立代理/任务执行；若在当前任务执行，应从 Task 1 开始并严格在每步前后追加开发日志。

## 2026-09-18 — Casdoor 生产认证加固隔离工作树（开始）

- 目标：按用户批准，为认证实现创建 `.worktrees/casdoor-auth-hardening` 隔离工作树和 `codex/casdoor-auth-hardening` 分支，避免直接在 `main` 修改生产代码。
- 范围：仅新增 `.worktrees/` Git 忽略规则并创建 Git 工作树；不修改认证代码、运行配置、数据库账号或 Casdoor 状态。
- 已知约束：当前仓库位于干净的 `main` 普通检出，尚无项目内工作树目录；必须先提交忽略规则，防止工作树内容被误纳入版本控制。

## 2026-09-18 — Casdoor 生产认证加固隔离工作树（完成）

- 结果：已创建 `.worktrees/casdoor-auth-hardening`，分支为 `codex/casdoor-auth-hardening`，起点包含已批准设计、实施计划及 `.worktrees/` 忽略规则；`main` 不承载后续认证代码修改。
- 安全边界：未复制或读取 Git 忽略的后端 `.env`、数据库、令牌或账号密码；新工作树需要独立确认依赖可用性并运行基线测试。
- 下一步：在隔离工作树完成依赖检查和认证相关基线测试，然后从实施计划 Task 1 的失败测试开始。

## 2026-09-18 — Casdoor 认证实现基线验证（开始）

- 目标：确认隔离工作树分支、依赖和当前认证相关测试基线，避免把既有失败误判为本轮回归。
- 范围：只检查 Git 隔离状态、依赖目录和运行认证相关后端/前端测试；不读取受保护 `.env`，不启动服务，不修改数据库或 Casdoor。
- 已知限制：工作树不会复制主检出中被忽略的虚拟环境和 `node_modules`；如本机缓存不足，依赖安装可能需要网络授权。

## 2026-09-18 — Casdoor 认证实现基线验证（完成）

- 隔离状态：工作树 Git 目录为主仓库 `.git/worktrees/casdoor-auth-hardening`，公共 Git 目录为主仓库 `.git`，当前分支 `codex/casdoor-auth-hardening`；确认不是 `main` 普通检出。
- 依赖：`uv sync --project src/backend --locked --extra dev` 按锁文件创建工作树后端虚拟环境；`npm --prefix src/frontend-enterprise ci --no-audit --no-fund` 安装 561 个锁定前端包。未复制或读取主检出的 `.env`。
- 基线：后端 `test_oidc_auth.py`、`test_auth_roles.py`、`test_auth_password_hashing.py` 共 17 项通过；前端 `auth.test.ts` 与 `App.test.tsx` 共 5 项通过。
- 下一步：实施 Task 1，先写生产认证配置门禁失败测试，再添加最小实现并运行专项回归。

## 2026-09-18 — Task 1 生产认证配置门禁（开始）

- 目标：新增纯配置生产门禁，并确保它在任何数据库初始化之前执行；开发环境继续兼容现有回环 HTTP 和演示种子配置。
- 范围：`src/backend/app/config.py`、新建 `src/backend/app/security/runtime_config.py`、`src/backend/app/main.py`、新建 `src/tests/backend/test_runtime_config.py`。
- 已知约束：校验不得联网、不得输出配置值；错误只列出无效设置键。严格遵循红绿 TDD，先观察缺少模块导致的预期失败。

## 2026-09-18 — Task 1 生产认证配置门禁（完成）

- 文件：在 `app/config.py` 新增 `DEPLOYMENT_ENVIRONMENT` 与 `OIDC_POST_LOGOUT_REDIRECT_URI` 设置；新增纯函数 `app/security/runtime_config.py`；`app/main.py` 在 `init_db()` 前执行生产门禁；新增 `test_runtime_config.py` 25 项覆盖。
- 红绿证据：首次运行因 `app.security.runtime_config` 不存在而在收集阶段预期失败；最小实现后专项 25 项通过。随后联合 OIDC/本地认证回归共 42 项通过。
- 静态检查：Ruff 检查全部变更 Python 文件和新测试，结果 `All checks passed!`。pytest 的 4 条 FastAPI `on_event` 弃用警告来自既有启动钩子，本任务未迁移生命周期机制。
- 安全性质：开发配置直接放行；生产要求完整 OIDC 值、全部 OIDC URL 使用 HTTPS、Secure Cookie、至少 32 字符且非默认的 `APP_SECRET`、禁用演示种子；错误只输出设置键，不输出密钥值。
- 下一步：Task 2 为 OIDC Cookie 会话新增服务器控制的 Casdoor 注销准备端点，并保持本地 204 注销兼容。

## 2026-09-18 — Task 2 Casdoor 单点退出准备端点（开始）

- 目标：为 OIDC Cookie 会话新增 `POST /api/auth/oidc/logout`，先清除 Joukir 会话并返回服务器配置的 Casdoor 注销 URL；保留本地/承载令牌注销的 204 合约。
- 范围：仅修改 `src/backend/app/api/oidc.py` 与 `src/tests/backend/test_oidc_auth.py`，复用现有账号审计事件和会话 Cookie。
- 已知约束：不存储或发送 Casdoor token，不接受调用方返回地址；开发环境缺少注销配置时安全回退 `/login`。先添加 URL、审计、Cookie 和兼容性失败测试。

## 2026-09-18 — Task 2 Casdoor 单点退出准备端点（完成）

- 文件：`app/api/oidc.py` 新增 `OIDCLogoutRead`、服务器配置 URL 构造器和 `POST /api/auth/oidc/logout`；现有本地注销与新端点共用注销审计及 Cookie 删除函数；`test_oidc_auth.py` 新增 4 项回归。
- 红绿证据：新增测试首次运行 3 项按预期失败，原因分别是 `_oidc_logout_url` 与 `oidc_logout` 不存在，原有 10 项通过；实现后 OIDC 文件 13 项全部通过。
- 回归与静态检查：生产门禁、OIDC、本地角色和密码哈希联合回归 46 项通过；Ruff 对路由与测试结果 `All checks passed!`。既有 FastAPI `on_event` 弃用警告仍为 4 条。
- 安全性质：注销 URL 只使用服务器端 `OIDC_END_SESSION_ENDPOINT`、`OIDC_CLIENT_ID` 和 `OIDC_POST_LOGOUT_REDIRECT_URI`；不接收调用方重定向、不保存或发送 Casdoor token；缺失配置回退 `/login`，无效本地 token 仍删除 Cookie。
- 下一步：Task 3 新增共享前端退出助手，仅显式退出触发 Casdoor，401 会话失效仍只返回本地登录页。

## 2026-09-18 — Task 3 前端统一退出行为（开始）

- 目标：新增一个共享退出助手，根据 `auth_mode` 区分 OIDC Cookie 与本地承载令牌会话，并让企业控制台和聊天页的显式退出复用它。
- 范围：新建 `src/frontend-enterprise/src/authLogout.ts` 与 `src/tests/frontend/authLogout.test.ts`，修改 `App.tsx` 和 `pages/chat/useChatSession.ts`。
- 已知约束：网络失败也必须清除本地状态；仅显式退出触发 Casdoor，普通 401 只返回 `/login`；导航地址需拒绝危险协议。先编写共享助手失败测试。

## 2026-09-18 — Task 3 前端统一退出行为（完成）

- 文件：新增 `authLogout.ts` 共享助手和 `authLogout.test.ts` 6 项行为测试；`App.tsx` 企业退出与 `useChatSession.ts` 聊天显式退出均调用共享助手；聊天 401 路径仍仅清理状态并跳转 `/login`；`App.test.tsx` 新增两条界面集成测试。
- 红绿证据：助手测试首次因模块不存在预期失败；实现后 6 项通过。企业与聊天集成测试随后均因助手调用次数为 0 预期失败；替换两条旧路径后，两个文件共 10 项通过。
- 调试记录：首次类型检查和构建均稳定复现 `HeadersInit` 联合类型错误，根因为三元表达式将空对象推断为可选 `Authorization: undefined`；以显式 `Record<string, string>` 单点修复后类型检查通过。
- 验证：聚焦 Vitest 10 项通过，测试 TypeScript 类型检查通过，Vite 配置检查通过，生产构建转换 2,164 个模块并成功完成。构建仍有既有的大分块与 SVGR 性能警告，不属于认证回归。
- 安全性质：本地存储在请求前清除；OIDC 只调用新端点，本地承载令牌只调用原端点；拒绝危险协议，仅允许相对路径、HTTPS 和开发回环 HTTP；请求失败或非成功响应均返回 `/login`。
- 下一步：Task 4 为 Casdoor 应用配置增加经过验证的 `--public-url`，并让迁移脚本写入回调和注销后地址。

## 2026-09-18 — Task 4 Casdoor 公网地址配置（开始）

- 目标：让 Casdoor 应用配置脚本接收安全的公网源地址，并让平台迁移脚本从同一地址写入 OIDC 回调及注销后地址。
- 范围：`configure-casdoor-oidc.py`、`migrate-staffdeck.ps1` 与新建 `test_casdoor_oidc_provisioning.py`；测试只加载纯函数和检查脚本文本。
- 已知约束：不连接或修改实时 Casdoor/PostgreSQL，不读取部署 `.env`；非回环地址必须 HTTPS，且禁止凭据、路径、查询和片段。先添加失败测试。

## 2026-09-18 — Task 4 Casdoor 公网地址配置（完成）

- 文件：`configure-casdoor-oidc.py` 新增 `DEFAULT_PUBLIC_URL`、源地址规范化、重定向列表和 `--public-url`；Casdoor homepage/redirect URIs 从验证后的地址生成。`migrate-staffdeck.ps1` 新增同规则的 `PublicUrl` 参数并写入 OIDC 回调及注销后 URI；新增 12 项部署脚本测试。
- 红绿证据：首次运行 12 项全部按预期失败，原因是两个 URL 辅助函数和 PowerShell 合约不存在；实现后 12 项全部通过。
- 调试记录：首次 Ruff 唯一失败为端口校验属性访问未绑定（B018）；根因确认后以 `_ = parsed.port` 保留异常触发语义，重新运行通过。
- 验证：部署脚本测试 12 项通过；Ruff 结果 `All checks passed!`；PowerShell AST 解析通过并识别 1,335 个 token。测试未连接数据库、未读取部署 `.env`、未修改实时 Casdoor。
- 安全性质：公网地址禁止用户信息、非根路径、查询、片段和非法端口；HTTP 仅允许 `localhost`/`127.0.0.1`；默认本机配置保留两个原回调别名并新增 `/login`。
- 下一步：Task 5 新增只从进程环境读取密码、需要显式旋转开关的紧急本地管理员初始化命令。

## 2026-09-18 — Task 5 紧急本地管理员初始化（开始）

- 目标：新增手动命令创建或显式旋转生产紧急管理员，密码只来自进程环境，旋转时递增 `session_version`。
- 范围：新建 `src/backend/scripts/initialize_local_admin.py` 与 `src/tests/backend/test_initialize_local_admin.py`；只使用内存测试数据库，不运行命令连接实时数据库。
- 已知约束：必须存在活动租户；默认拒绝覆盖现有账号；命令行不接受密码参数；stdout/stderr 不得包含密码、哈希或数据库 URL。先添加服务和 CLI 失败测试。

## 2026-09-18 — Task 5 紧急本地管理员初始化（完成）

- 文件：新增 `src/backend/scripts/initialize_local_admin.py`，提供可测试的创建/旋转事务函数与安全 CLI；新增 `test_initialize_local_admin.py` 12 项，覆盖创建、活动租户、密码策略、拒绝隐式覆盖、显式旋转、会话撤销和输出保密。
- 红绿证据：首次运行因目标脚本不存在在收集阶段预期失败；实现后专项 12 项通过，连同本地认证与账号生命周期相邻回归共 30 项通过。
- 调试记录：首次 Ruff 唯一失败为顶层宽异常捕获 BLE001。该捕获是防止未知数据库异常 traceback 泄露连接细节的 CLI 安全边界，添加限定抑制及意图说明后 Ruff 通过；内部事务在异常时显式回滚。
- 安全性质：密码仅从 `JOUKIR_BOOTSTRAP_ADMIN_PASSWORD` 读取；`--password`/`--password=` 在 argparse 前无值回显拒绝；现有账号必须 `--rotate-existing`，旋转恢复本地平台管理员字段并递增 `session_version`；成功输出只含 tenant、username 和 action。
- 验证：30 项相邻后端测试通过，Ruff 结果 `All checks passed!`；全部使用内存 SQLite，未对实时数据库执行初始化或旋转。
- 下一步：Task 6 更新认证端点参考、部署运行手册和稳定项目记忆，不写入任何真实秘密。

## 2026-09-18 — Task 6 认证运维文档（开始）

- 目标：记录本地与 OIDC 注销合约、生产 Casdoor/HTTPS 上线顺序、紧急管理员初始化命令和长期架构边界。
- 范围：部署 README、认证端点参考、`docs/PROJECT_MEMORY.md`、文档索引与本日志；不修改代码、配置文件、数据库或 Casdoor。
- 已知约束：所有域名和账号示例均为合成值；不记录密码、Secret、完整数据库 URL 或外部授权载荷，不提供内联秘密赋值示例。

## 2026-09-18 — Task 6 认证运维文档（完成）

- 文件：认证端点参考新增本地 204 注销与 OIDC 注销准备合约；平台部署 README 新增生产 HTTPS/Casdoor/紧急管理员上线步骤；`PROJECT_MEMORY.md` 记录双入口、前通道单点退出、无 token 持久化和生产门禁；文档索引标题明确同时包含实施计划。
- 计划维护：修正实施计划中的秘密赋值扫描正则为 `[=]` 写法，避免命令文本自命中；未改变实施范围或验收标准。
- 验证：`git diff --check` 未报告内容错误，仅有 Windows 行尾提示；密码/客户端 Secret/应用 Secret 赋值扫描结果为 0；设计、计划、部署指南和端点参考四个索引目标均存在。
- 安全边界：文档仅使用 `identity.example.com`、`joukir.example.com` 和 `emergency-admin` 等合成示例；没有真实密码、Secret、DSN、token 或外部授权载荷。
- 下一步：Task 7 运行聚焦后端、完整前端、布局门禁、Ruff、生产负向门禁和开发健康检查，并记录仍需人工执行的浏览器 OIDC 验收。

## 2026-09-18 — Task 7 Casdoor 认证加固集成验证（开始）

- 目标：对全部认证加固切片运行新鲜的聚焦后端回归、完整前端测试/类型/配置/i18n/构建、测试布局门禁、Ruff、生产负向门禁和开发健康检查。
- 范围：只使用隔离工作树依赖、合成生产环境变量和工作树本地开发数据库；不读取受保护 `.env`，不登录真实 Casdoor，不初始化或旋转真实账号。
- 已知限制：Casdoor 浏览器登录、角色页面、前通道注销和重新登录需要部署运营者持有的真实浏览器会话，本轮自动化只能验证 URL/端点/前端路由和启动门禁，不能替代人工生产验收。

## 2026-09-18 — Task 7 Casdoor 认证加固集成验证（完成）

- 后端：生产门禁、OIDC、本地角色/密码、紧急管理员和 Casdoor 配置聚焦回归 70 项通过；测试布局门禁确认 1,197 个跟踪路径均符合 `src/tests` 边界；全部变更 Python 文件 Ruff 检查通过。仅有 4 条既有 FastAPI `on_event` 弃用警告。
- 前端：完整 Vitest 65 个文件、279 项通过；测试 TypeScript 类型检查通过；Vite 配置检查通过；i18n 检查覆盖 4,209 条英文翻译；生产构建转换 2,164 个模块并成功。保留既有大分块构建警告。
- 生产负向探测：在隔离一次性进程中仅设置合成的 `DEPLOYMENT_ENVIRONMENT`、`DATABASE_SEED_DEMO_DATA` 和 `OIDC_ENABLED`，校验以退出码 1 拒绝配置，输出包含预期无效键且不含合成秘密；未加载受保护 `.env`。
- 真实开发启动：因原 5173 已被健康实例占用，工作树自动选择 5175；应用完成启动且 `/api/health` 返回 `ok`。真实 HTTP `POST /api/auth/oidc/logout` 返回 200、`{"redirect_url":"/login"}` 并发送删除 `staffdeck_session` 的 Cookie。随后关闭工作树实例，5175 已释放，原 5173 服务仍为 `ok`。
- 仓库状态：六个实现/文档切片均为独立提交；最终仅本条开发日志待提交，`git diff --check` 无内容错误。未修改 `SESSION_HANDOFF.md`，因为实现与自动化验证已完成。
- 剩余人工验收：在实际生产域名和运营者拥有的 Casdoor 浏览器会话中验证 OIDC 登录、业务角色页面、Casdoor 前通道注销、回到 Joukir `/login` 和再次登录；在完成该步骤前不得宣称生产 SSO 已验收。
- 生产上线顺序：先以精确 HTTPS 公网地址配置 Casdoor 并注册管理员，再经受保护交付设置生产 OIDC/Secret/Secure Cookie/禁用演示种子，按需初始化紧急管理员，启动通过门禁后执行上述人工验收。

## 2026-09-18 — Casdoor 认证加固分支收尾核验（开始）

- 目标：在聚焦验收之外运行完整后端测试门禁，确认功能分支是否满足合并前的全库绿色条件。
- 范围：仅运行测试、对照原始 `main` 的同节点结果并刷新交接记录；不修改认证实现，不连接真实 Casdoor，不读取秘密配置。
- 已知基线：项目记忆已记录完整后端套件长期非绿色；本步骤仍以新鲜执行结果为准，不把既有失败隐去或误报为本次功能回归。

## 2026-09-18 — Casdoor 认证加固分支收尾核验（未通过全库门禁）

- 完整后端执行：`python -m pytest -c pytest.ini src/tests/backend -q` 运行到 100%，但多项非认证测试失败；pytest 在会话清理阶段访问系统临时目录 `pytest-current` 时又触发 Windows `PermissionError`，因此没有生成可信的最终通过/失败汇总行，退出码为 1。
- 失败缓存证据：`.pytest_cache/v/cache/lastfailed` 记录 37 个失败节点，集中于 Harness v2、通用技能、广告治理、进程/运行时锁、附件、渠道和工具 API；本次新增及修改的认证、OIDC、管理员初始化和 Casdoor 配置测试均不在该名单中。
- 复现与基线对照：在工作树内指定全新 `--basetemp` 后仍复现失败；单独运行广告治理节点得到 `manual_resolution_required != queued`。同一节点在原始 `main` 工作目录得到完全相同断言，证明该代表性失败不是本认证分支引入。
- 已通过门禁仍有效：认证相关后端 70 项、测试布局、变更 Python Ruff、前端 65 文件/279 项、类型检查、配置、i18n、生产构建、生产负向门禁和开发 HTTP 注销探测均已通过。完整后端套件非绿色，因此本分支不宣称全库测试通过，也不自动合并。
- 剩余风险与下一步：若要求严格绿色合并，需另行修复或批准基线化仓库既有的完整后端失败，并解决 Windows pytest 临时目录权限问题；随后重新运行完整后端套件。认证功能本身还需部署后的人工 Casdoor 浏览器登录、角色页面和前通道注销验收。

## 2026-09-18 — Casdoor 认证加固合并与启动（开始）

- 目标：按用户明确指示将 `codex/casdoor-auth-hardening` 本地合并到 `main`，重启主工作目录的单端口应用，并验证健康与认证入口。
- 范围：仅进行本地 Git 合并、主目录 Joukir 进程重启和无凭据 HTTP 健康/入口检查；不推送远端、不连接真实 Casdoor 账号、不初始化或旋转任何真实用户。
- 已知阻塞：完整后端套件仍有已记录的非认证基线失败和 Windows pytest 临时目录权限问题。用户在收到该结果后明确要求继续合并；因此保留功能分支和工作树，不把本次合并记录为全库绿色，也不执行分支清理。

## 2026-09-18 — Casdoor 认证加固合并与启动（完成）

- 合并结果：确认 `main` 与 `codex/casdoor-auth-hardening` 均无未提交变更且前者为后者祖先；在无远端配置的本地仓库中以 `git merge --ff-only` 将 `main` 从 `73068c5` 快进到 `016a485`，无冲突、未推送。因完整后端门禁仍非绿色，功能分支和隔离工作树继续保留。
- 启动调试：PowerShell 包装器按原样转发参数，正确后台参数为 `--detach`。非提升沙箱无法读取仅 Administrator/SYSTEM 可访问的 `.env.local`，因此在不修改 ACL、不输出内容的前提下以管理员上下文执行官方启动脚本；前端生产构建转换 2,164 个模块并成功。
- Windows 运行限制：官方 supervisor 在本机将虚拟环境 Python 包装 PID 与实际 Uvicorn 子 PID分离，导致健康子进程存在时仍反复重启并产生端口冲突。经两轮父子进程和命令行核验后停止 supervisor，清理已确认的旧 Joukir 进程树，并将唯一稳定包装进程 PID 66924 写入忽略的 `.dev/app.pid`；未修改源码、配置内容或 ACL。`dev_down.ps1` 可据此停止整棵应用进程树，但当前运行态不提供自动重启。
- 在线验证：`dev_status.ps1` 显示 `app running (66924)`、5173 listening、health ok；`GET /api/health` 返回 `{"status":"ok","app":"九骥 Joukir"}`，`GET /chat/`、`GET /enterprise/dashboard`、`GET /login` 均为 200，`POST /api/auth/oidc/logout` 为 200 且返回 `{"redirect_url":"/login"}`。实际监听子进程为 PID 58288，命令行为本仓库 `single_port_app:app --host 127.0.0.1 --port 5173`。
- 剩余风险与下一步：完整后端基线和 Windows supervisor PID 跟踪仍需单独修复；本次只保证当前单实例稳定运行。生产 SSO 仍需运营者使用真实 Casdoor 会话完成登录、角色页面、前通道注销和再次登录验收。
## 2026-09-22 — TikTok P3-B0 数据验证工作台设计（开始）

- 目标：将 TikTok 模块 PRD V1.8 的 P3-B0 落成可运行、可审计的数据验证工作台，为 P3-B1 的看板、样品履约和指标字典提供明确输入门禁。
- 范围：本步骤仅形成设计规格并核对现有 TikTok 专项基线；规划租户试点范围、字段契约、动作级能力证据、Mock 验证运行、工作台 API/UI、权限、RLS 与退出条件，尚不修改业务源码或数据库结构。
- 已知阻塞：真实美国店铺部署与可调用授权尚未独立验收；Creator、Affiliate、Ads、LIVE 和消息能力不能由 Seller 权限或 Mock 结果推定。当前完整后端套件存在已记录的非绿色基线。
- 隔离：工作在 `.worktrees/tiktok-p3b0-validation` 的 `codex/tiktok-p3b0-validation` 分支，保留主工作区未提交的认证、M2M 和监督器改动不动。
- 安全边界：工作台不保存 Token、Cookie、原始 OAuth 载荷、原始第三方响应、达人地址或明文联系方式；Mock/文档/沙箱证据不得标记为真实账号数据就绪。

## 2026-09-22 — TikTok P3-B0 数据验证工作台设计复核（开始）

- 目标：对已批准方向形成的书面规格执行一致性、范围、链接和仓库差异复核，并记录现有 TikTok 专项测试基线。
- 范围：检查设计规格与 PRD 19.1、现有租户/RLS/管理员权限约定、文档索引和 Mock/真实数据门禁是否一致；不修改业务源码或数据库结构。
- 已知约束：书面规格尚待用户复核；按设计流程，本步骤通过后只提交设计文档，不提前进入实现计划或实现。

## 2026-09-22 — TikTok P3-B0 数据验证工作台设计复核（完成）

- 变更：新增 `docs/superpowers/specs/2026-09-22-tiktok-p3b0-data-validation-workbench-design.md`，并在 `docs/README.md` 建立索引；业务源码、数据库结构和运行配置未改动。
- 规格结论：采用四张租户表承载 US 试点范围、字段契约、动作级能力证据和追加写验证运行；管理员可编辑和运行，成员只读；目录幂等初始化，编辑使用 revision；PostgreSQL 强制 RLS。
- 关键门禁：`workbench_ready` 与 `real_data_ready` 独立计算；被阻塞能力允许形成如实盘点结论，但 Mock、文档、沙箱、登录成功或其他动作证据均不能把目标动作提升到 E3。首版缺少真实或脱敏录制回放入口，因此真实数据状态必须保持 false。
- 基线验证：使用现有锁定虚拟环境运行 13 个 TikTok 专项测试文件，68 项在 49.30 秒内通过。文档结构检查确认要求章节齐全、无 TODO/TBD/FIXME，索引目标存在且只有一条索引；`git diff --check` 无内容错误，仅报告仓库既有的 Windows 换行转换提示。
- 剩余风险：真实 US 店铺、Affiliate、Creator/Partner、Ads、LIVE、消息与客服动作尚无完整 E3；完整后端套件仍有已记录的其他基线失败。设计规格尚待用户书面复核，尚未形成实施计划或修改业务代码。
- 下一步：用户复核本规格后，按写计划流程拆分红绿 TDD、migration/RLS、API、前端和双角色浏览器验收任务，再开始实现。

## 2026-09-22 — TikTok P3-B0 数据验证工作台实施计划（开始）

- 目标：在用户批准书面规格后，将四张租户表、目录/bootstrap、就绪算法、Mock 运行、API、前端工作台和验证门禁拆成可逐项执行的红绿 TDD 计划。
- 范围：本步骤只新增实施计划和文档索引/记录，不修改业务源码、数据库结构或运行配置。
- 约束：计划必须固定精确文件、接口、失败测试、最小实现、验证命令和分步提交；延续隔离分支 `codex/tiktok-p3b0-validation`，不混入主工作区未提交改动。
- 已知风险：真实账号 E3 和录制回放不在首版；完整后端套件存在已记录的其他基线失败，计划需区分聚焦回归和全库基线。

## 2026-09-22 — TikTok P3-B0 数据验证工作台实施计划（完成）

- 变更：新增 `docs/superpowers/plans/2026-09-22-tiktok-p3b0-data-validation-workbench.md`，更新 `docs/README.md` 索引，并刷新 `docs/SESSION_HANDOFF.md` 的当前分支、门禁和下一步；业务源码和数据库结构仍未修改。
- 任务结构：计划含 7 个可独立提交的 TDD 切片、54 个可勾选步骤，依次覆盖四表与 FORCE RLS、30 个字段/31 个能力与供应商目录、revision 和就绪算法、确定性 Mock、六个 API、前端第七页签、双角色浏览器与最终门禁。
- 自检：计划与规格的四表、六路由、FastMoss/领星/达密/飞书、管理员/成员权限、E0-E3、Mock/真实门禁和追加写运行要求逐项对齐；无 TODO、TBD、FIXME、代码省略号或模糊“稍后实现”步骤，接口名称在前后任务中一致。
- 评审重点：重复来源优先级/拒绝来源、revision 冲突、过期或主体/scope/资产不匹配 E3、双租户同键、重复 Mock 摘要与原值泄漏五类风险均有明确失败测试归属。
- 下一步：用户评审计划并选择 Native 或 Subagent-driven 执行；收到选择前不开始 Task 1。

## 2026-09-22 — TikTok P3-B0 数据验证持久化（开始）

- 目标：建立 `tiktok_data_validation_scopes`、`tiktok_field_contracts`、`tiktok_capability_evidence`、`tiktok_data_validation_runs` 四张租户表及 SQLModel 映射。
- 范围：新增 PostgreSQL 正向/回滚迁移、FORCE RLS、同租户复合外键、运行记录追加写保护，并补充模型、迁移静态检查和可选 PostgreSQL 验收。
- 安全边界：数据库只保存范围、契约、证据元数据与验证摘要；不保存 Mock 原始 fixture、外部响应载荷、Token、Cookie 或 OAuth 原始数据。
- 已知风险：本步骤只验证结构和数据库边界，不实现目录初始化、业务就绪算法或真实外部调用。

## 2026-09-22 — TikTok P3-B0 数据验证持久化（完成）

- 变更：新增四个 SQLModel、四表 PostgreSQL 正向/回滚迁移、租户复合外键、FORCE RLS、运行记录追加写触发器，以及模型/迁移静态测试和可选 PostgreSQL 验收用例。
- 验证：新测试先因四个模型不存在而在收集阶段失败；实现后 `test_postgres_tiktok_data_validation_migration.py` 2 项通过。新增测试文件和 PostgreSQL 验收文件通过 Ruff；`models.py` 在忽略仓库既有的 `UP045` 与 `FURB157` 后通过 Ruff。
- 基线偏差：计划中的全文件 Ruff 命令会报告 `models.py` 既有的 384 个 `UP045` 和 2 个 `FURB157`，这些告警位于本次改动之前的代码。未批量重写该共享模型文件，以免扩大 TikTok 任务范围；本次新增类型已使用 `X | None`，未增加同类告警。
- 剩余风险：未配置真实 PostgreSQL 验收环境时，RLS、复合外键和追加写触发器只能由迁移静态检查覆盖；部署前仍需在迁移测试库执行可选验收。
- 下一步：实现版本化目录、幂等 bootstrap 和只读工作区聚合。

## 2026-09-22 — TikTok P3-B0 验证目录与工作区读取（开始）

- 目标：实现版本 `p3-b0.v1` 的固定目录、管理员幂等 bootstrap 和任意同租户成员可读的安全工作区聚合。
- 固定规模：目录包含 30 个字段契约、27 个动作级能力条目和 4 个供应商决策条目，共 31 个能力/供应商条目。
- 初始化边界：bootstrap 只补齐缺失代码，不覆盖租户编辑；字段仅创建一个 `mock_fixture` 来源，能力证据只以 E0 / unverified 初始化，不填检查人或检查时间。
- 安全边界：工作区响应只返回安全的店铺/Owner 选项和证据元数据，不暴露授权凭据引用、Token 指纹或授权原始 metadata。

## 2026-09-22 — TikTok P3-B0 验证目录与工作区读取（完成）

- 变更：新增 30 个字段、27 个动作能力和 4 个供应商决策的不可变目录；实现管理员幂等 bootstrap、同租户安全工作区读取、目录顺序排序、20 条最近运行上限，以及不含秘密字段的响应模型。
- 验证：新测试先因 `app.tiktok.data_validation` 不存在而在收集阶段失败；实现后 3 项通过，覆盖重复 bootstrap 不覆盖租户编辑、双租户同代码隔离、Mock-only 来源和 E0 初始化。相关模块与测试 Ruff 通过。
- 实施裁决：Task 2 的工作区读取依赖 Task 3 才正式产出的就绪评估器。为保持本任务可运行，先提供始终保守为 false 的最小评估器；Task 3 将在相同公共签名上补全规则。若该排序判断错误，影响仅为 Task 3 提交前工作区显示额外保守阻塞，不会误报就绪。
- 剩余风险：当前就绪判断尚未区分配置就绪与真实数据就绪，编辑、revision 和证据组合规则也未实现。
- 下一步：实现管理员受控编辑、乐观并发、同租户引用校验和完整双门禁算法。

## 2026-09-22 — TikTok P3-B0 受控编辑与双门禁（开始）

- 目标：实现范围、字段和能力证据的管理员写入，使用 revision 防止覆盖，并实时计算 `workbench_ready` 与 `real_data_ready`。
- 权限与引用：所有变更仅限租户管理员；店铺、Owner、检查人必须为同租户有效对象，跨租户引用统一按未找到处理。
- 证据边界：E3 仅接受 `real_account`，E2 仅接受 Mock、沙箱或批准导出，E0 仅接受 unverified；不同动作之间不继承证据。
- 风险控制：被明确标记 blocked 的能力可完成 P3-B0 盘点，但始终阻止真实数据就绪；Mock、登录或其他动作证据不能替代目标动作 E3。

## 2026-09-22 — TikTok P3-B0 受控编辑与双门禁（完成）

- 变更：新增范围、字段和能力证据更新请求模型及交叉字段校验；实现管理员权限、revision 冲突、固定目录代码、同租户有效店铺/用户引用校验，以及 404/409 可映射的稳定领域异常。
- 门禁：`workbench_ready` 逐项检查 active US 范围、30 个字段契约、27 个动作结论、4 个供应商决定和当前版本 Mock 运行；`real_data_ready` 另行检查字段真实来源、每个读取动作独立 E3、未过期证据、主体/店铺/scope 匹配的有效授权和真实/录制验证。
- 验证：新增测试先因领域异常和更新接口缺失而在收集阶段失败；实现后 16 项通过，覆盖重复来源优先级、拒绝来源、revision 冲突、跨租户引用、成员写入、未知代码、证据等级组合、blocked 盘点、动作不继承、过期 E3 以及主体/资产/scope/授权不匹配。相关模块和测试 Ruff 通过。
- 安全结论：Mock 或其他动作证据不会将目标能力升级到 E3；首版固定加入 `recorded_or_real_validation_missing`，因此未提供真实/录制输入时真实数据状态保持 false。
- 下一步：实现确定性内置 Mock fixture、纯校验函数和追加写运行摘要。

## 2026-09-22 — TikTok P3-B0 确定性 Mock 验证（开始）

- 目标：以固定时钟 `2026-09-22T00:00:00Z` 和内置规范 fixture 实现纯数据质量校验，并将每次运行作为不可变摘要追加保存。
- 确定性：摘要哈希由当前目录版本与规范化 fixture 的排序键、紧凑 JSON 计算；同输入必须得到同 digest、检查项和问题列表。
- 隐私边界：数据库只保存检查代码、布尔结果、计数和问题元数据；检查详情不得包含订单号、达人号或任何 fixture 原值。
- 门禁：Mock 运行可使完整配置达到 `workbench_ready`，但 `real_data_ready_snapshot` 永远为 false，且运行接口不访问外部网络。

## 2026-09-22 — TikTok P3-B0 确定性 Mock 验证（完成）

- 变更：新增固定目录版本 fixture、固定校验时钟、安全结果模型、规范 JSON SHA-256 摘要、纯校验器和管理员运行事务；每次运行只追加一条摘要记录。
- 校验范围：按稳定顺序检查必需字段/类型、业务键唯一性、跨对象关联、金额/币种、时间窗口、新鲜度、PID/商品一致性和选定来源授权，并按 `(code, field_code)` 排序问题。
- 验证：新测试先因 Mock 常量和运行函数缺失而在收集阶段失败；实现后 27 项通过，覆盖确定性、重复键、缺字段、陈旧数据、非法金额、非大写币种、反向归因窗口、断链、缺业务键、被拒来源、无原值泄漏、追加写两次和成员 403。相关模块与测试 Ruff 通过。
- 安全结论：digest 可复算但不可逆推出 fixture；`checks_json`/`issues_json` 不含原始订单号或达人号，且每条 Mock 运行的真实数据快照被强制设为 false。
- 下一步：接入六个认证 API 路由及 404/409/422/403 错误映射。

## 2026-09-22 — TikTok P3-B0 工作台 API（开始）

- 目标：在 `/api/enterprise/tiktok/data-validation` 下提供读取、bootstrap、范围更新、字段更新、证据更新和 Mock 运行六个路由。
- 权限：同租户已登录成员可读；bootstrap、三类编辑和运行仅管理员可用，沿用现有权限助手的 403。
- 错误策略：目录或同租户引用不存在映射 404，revision/领域冲突映射 409，请求模型错误由 FastAPI/Pydantic 返回 422；跨租户存在性不进入错误详情。
- 响应边界：工作台响应不包含 `credential_ref`、`token_fingerprint`、授权 metadata、fixture 原始标识或其他秘密。

## 2026-09-22 — TikTok P3-B0 工作台 API（完成）

- 变更：新增六个 FastAPI 路由和统一领域错误映射；写入异常先回滚事务，未捕获权限错误继续由既有助手返回 403，请求模型校验继续由 FastAPI 返回 422。
- 安全门禁：新增路由和 `data_validation.py` 首次触发 P3-A 冻结写入面审计。核验这些路由仅操作本地租户数据且模块无外部 HTTP 写入后，将 6 个路由和 1 个 Python 文件加入受审清单，并同步冻结面计数为 29 路由、13 文件。
- 验证：API 测试先因路由缺失而在收集阶段失败；实现后 3 项通过，覆盖成员读/写分离、404、409 和秘密字段/fixture 原值不出响应。使用工作树本地 `--basetemp` 运行 API 加既有 TikTok 后端回归共 71 项通过，相关 API、门禁和测试 Ruff 通过。
- 环境说明：首次全量命令除两个冻结面预期失败外，还命中 Windows 全局 pytest 临时目录权限问题；修复冻结清单后改用工作树根下临时目录，真实失败与环境噪声均已分离验证。
- 下一步：实现前端第七个“数据验证”页签、五区工作台和管理员/成员交互差异。

## 2026-09-22 — TikTok P3-B0 前端数据验证工作台（开始）

- 目标：新增第七个“数据验证”页签，提供就绪状态、US 试点范围、字段契约、能力/供应商证据和 Mock 运行五个可定位区域。
- 角色差异：管理员可初始化、编辑和运行；成员读取同一租户工作区但只显示只读模式，不渲染任何写按钮。
- 可访问性与错误：表单控件使用明确 label/aria-label，状态不只依赖颜色；409/422 等 API 错误保留当前表单并显示可读通知。
- 展示边界：前端只显示摘要、检查代码和问题元数据，不定义或渲染原始 Mock 行、授权 metadata、凭据引用、Token 指纹或秘密字段。

## 2026-09-22 — TikTok P3-B0 前端数据验证工作台（完成）

- 变更：新增第七个“数据验证”页签和五区工作台；管理员可初始化目录、维护 US 试点范围、字段契约、动作能力/供应商证据并运行 Mock，成员获得同租户只读视图。
- 表单覆盖：字段契约可编辑 Owner、业务键、新鲜度、缺失处理和状态并显示来源摘要；证据矩阵可编辑等级、类型、状态、供应商决定、摘要、检查人和检查时间。每行使用独立 busy key、携带 revision，失败时保留草稿并同时显示页内错误与 toast。
- 接口对齐：运行记录 API 使用 Pydantic validation alias 将数据库字段 `checks_json`/`issues_json` 映射为前端语义字段 `checks`/`issues`，未改变持久化列；此前不存在该外部路由，未形成兼容性破坏。
- 国际化与安全：补齐新增中文文案的英文目录；界面只渲染安全摘要和问题代码，不显示 Mock 原始记录、授权 metadata、凭据或 token。
- 验证：前端组件 7 项测试通过；前端测试类型检查、i18n 覆盖和 Vite 配置检查通过；后端数据验证服务/API 30 项测试通过。
- 剩余风险：当前工作台只验证内置确定性 Mock；真实或脱敏录制回放仍未接入，因此 `real_data_ready` 按设计保持 false。
- 下一步：运行仓库门禁，启动隔离单端口环境执行管理员/成员双角色浏览器验收，并更新项目记忆、交接和文档索引。

## 2026-09-22 — TikTok P3-B0 最终门禁与双角色验收（开始）

- 目标：对 P3-B0 全部增量执行后端、前端、迁移、类型、国际化、构建和安全门禁，并在隔离单端口环境完成管理员/成员双角色浏览器验收。
- 范围：只验证和记录本分支已有功能；必要时修复本次功能缺陷，更新项目记忆、交接、文档索引与安全截图，不接入真实 TikTok 数据源或外部写入。
- 浏览器边界：验收管理员可编辑/运行、成员只读、五区布局、两种就绪状态和无原始 Mock/凭据暴露；截图不得包含密码、token、cookie 或真实个人数据。
- 已知阻塞：PostgreSQL 可选验收取决于本地测试数据库环境；若未配置，将明确记录静态迁移测试范围，不把它描述为生产数据库验收。

## 2026-09-22 — TikTok P3-B0 最终门禁与双角色验收（完成）

- 后端门禁：计划列出的 TikTok/数据验证矩阵使用工作树本地 `--basetemp` 运行；完成前修正后的最终复跑为 101 项通过。测试布局最终确认 1,209 个跟踪路径符合 `src/tests` 边界。数据验证服务/API 新增测试最终共 31 项通过。
- 数据库门禁：迁移/RLS 静态测试通过；`STAFFDECK_RUN_POSTGRES_ACCEPTANCE` 未配置，因此可选的独立 PostgreSQL 验收用例未运行。为执行真实浏览器链路，已通过既有迁移角色把新迁移应用到恢复的本地 PostgreSQL 开发库；不记录连接值、密码或原始数据。
- Python 风格：除 `models.py` 外的全部本次 Python/测试文件 Ruff 通过；`models.py` 使用 `--ignore UP045,FURB157` 后通过。无忽略项的计划命令仍只报告该共享文件本次之前已有的 372 个 `UP045`，未借本功能批量改写历史类型标注。
- 前端门禁：默认并行 Vitest 首次因主机资源争用出现 3 个旧用例超时，其余 283 项通过；三个文件单独串行 5/5 通过。完成前修正后的最终完整串行复跑为 66 个文件、287 项全部通过。类型检查、4,275 条 i18n 覆盖、Vite 配置检查和 2,165 模块生产构建均通过；构建仍有既有的插件计时与大 chunk 非阻塞警告。
- 管理员浏览器验收：隔离单端口环境运行于 `http://127.0.0.1:5176`。在 `/enterprise/tiktok` 初始化并读取 30 个字段、27 个动作能力和 4 个供应商决定；保存 US 试点范围、`order.order_id` 契约和 `seller.orders.read` Mock 证据后刷新确认持久化；Mock 校验返回 6 条记录，8 类检查均通过，页面未展示原始 fixture 值。
- 成员浏览器验收：既有成员账号可打开同一路由并看到安全摘要和 `只读模式`；工作台可编辑控件启用数为 0，初始化、范围保存、字段保存、能力/供应商保存和 Mock 运行按钮均为 0。安全截图已保存为 `docs/screenshots/tiktok-p3b0/admin-mock-run.jpg` 与 `member-read-only.jpg`。
- 就绪结论：Mock 运行去除了 `mock_run_missing`，但工作台配置尚未填写完整，`workbench_ready` 仍为 false；没有匹配的 E3 真实账号证据和真实/批准录制回放，`real_data_ready` 明确保持 false。这是预期门禁，不是功能失败。
- 运行清理：隔离服务已停止，5176 端口可用；工作树临时 `.env` 副本和 pytest 临时目录已删除。主工作区 5173 服务未被停止或修改。
- 剩余风险与下一步：完整后端套件仍有仓库既有非绿基线，本次未据此声称全量通过。下一阶段应先取得逐动作 E3 `real_account` 证据并接入真实或批准的脱敏录制回放验证，再评估 P3-B1。

## 2026-09-22 — TikTok P3-B0 完成前自审修正（开始）

- 目标：按批准规格和仓库规范复核整分支，重点检查租户边界、证据门禁、时间语义、UI/API 字段对齐和秘密数据边界。
- 已发现问题：能力证据的 `checked_at` 从 API 返回 UTC ISO 字符串后直接截取，`datetime-local` 会把 UTC 时刻误显示成本地墙上时间；再次保存会造成时区漂移。
- 修正策略：先增加带模拟时区偏移的失败用例，再以浏览器本地偏移格式化输入值；不改变 API 的 UTC ISO 存储格式。

## 2026-09-22 — TikTok P3-B0 完成前自审修正（完成）

- 规格轴修正：增加 E0 与结论状态的一致性约束，禁止 `evidence_level='E0'`、`evidence_type='unverified'` 同时声称 `status='verified'`；仍允许用 E0 明确记录 `blocked` 或 `not_applicable`，保持事实盘点能力。
- 标准轴修正：新增 `formatDateTimeLocal`，把 API 的 UTC ISO 时刻按浏览器偏移转换为 `datetime-local` 值，再由既有保存逻辑转回 UTC，避免非 UTC 时区重复保存漂移。
- TDD 证据：时区用例先收到 `2026-09-22T00:00` 而不是模拟 UTC+8 的 `2026-09-22T08:00`；E0 用例先未抛出 `ValidationError`。实现后前端组件 8 项通过，后端数据验证服务 28 项通过。
- 最终验证：TikTok 后端矩阵 101 项通过；Ruff 覆盖全部本次 Python/测试改动（共享 `models.py` 仅忽略既有 `UP045,FURB157`）并通过；测试布局 1,209 路径通过；完整前端 66 文件/287 项、类型检查、i18n、配置检查和生产构建通过。
- 自审结论：未发现未修复的 Critical/Important 规格或仓库规范问题。UI 首版按批准计划只展示字段来源摘要和动作证据的基础审计字段；真实来源编辑、逐动作 E3 采集与录制回放仍属于下一阶段明确边界。

## 2026-09-22 — TikTok P3-B0 脱敏录制回放设计（开始）

- 目标：在已合并的数据验证工作台上补齐经审批的脱敏录制回放入口，使系统能够验证真实业务形态的数据而不持久化原始记录。
- 范围：本步骤只编写设计规格、文档索引和交接记录；不修改产品代码、数据库结构、运行配置或外部平台状态。
- 已确认约束：浏览器选择 JSON；后端限量内存校验；数据库仅保存摘要、检查结果、范围/契约快照和审批元数据；审批人与上传执行人分离；录制回放不自动升级 E3。
- 已知阻塞：真实 TikTok 逐动作 E3、有效资产授权和真实接口调用仍需独立取得；P3-B1 的 30 条对照退出条件不作为 P3-B0 录制入口的隐含门槛。

## 2026-09-22 — TikTok P3-B0 脱敏录制回放设计（完成）

- 变更：新增书面规格 `docs/superpowers/specs/2026-09-22-tiktok-p3b0-recorded-validation-design.md`，并更新文档索引与当前交接。
- 规格固定：2 MiB 流式限制、六集合/30 字段白名单、敏感键拒绝、稳定假名声明、独立同租户审批人、历史回放时钟、追加写 recorded 摘要、scope/contract/catalog/审批失效和 E3/授权独立门禁。
- PRD 边界：P3-B0 不隐含 30 条门槛；30 条真实或脱敏历史记录逐条对照仍属于 P3-B1 退出条件。本阶段不实现看板、事实表、真实 Connector 或外部写入。
- 自审：未发现 TODO/TBD/FIXME、相互矛盾或未定义的完成条件；数据库、API、前端、安全、错误和测试边界均有确定行为。
- 下一步：等待用户复核书面规格；批准后使用 writing-plans 技能形成逐步 TDD 实施计划，产品代码在计划获批前不修改。

## 2026-09-22 — TikTok P3-B0 脱敏录制回放实施计划（开始）

- 目标：把已批准的书面规格拆成数据库、输入安全、录制运行、API、前端和验收六个可独立提交的红绿 TDD 任务。
- 范围：本步骤只新增实施计划并更新索引与交接；不修改产品代码、数据库结构、运行配置或外部平台状态。
- 计划约束：所有任务使用精确文件、接口、失败断言、验证命令和提交边界；原始录制数据不得写入数据库、日志、测试产物或截图。
- 已知限制：隔离工作树尚未连接忽略的 Python/Node 依赖；执行开始时再建立本地依赖连接并验证基线。真实 E3 与外部授权仍是独立业务阻塞。

## 2026-09-22 — TikTok P3-B0 脱敏录制回放实施计划（完成）

- 变更：新增 `docs/superpowers/plans/2026-09-22-tiktok-p3b0-recorded-validation.md`，更新文档索引和交接；产品代码与数据库结构未修改。
- 任务结构：六个可独立提交的 TDD 切片依次覆盖追加写持久化、有限且无秘密的输入、录制运行与 readiness、API、管理员 UI、完整门禁与双角色浏览器验收。
- 接口锁定：计划固定 2 MiB 流式读取、六集合/30 字段结构、独立审批人、`replay_as_of`、scope revision、contract digest、最新运行优先和六类 recorded 缺失/失效 blocker。
- 自审：规格各节均映射到任务；接口签名和字段名在相邻任务一致；五个高风险输入均有归属测试；未发现占位步骤、遗漏完成条件或跨阶段引入 P3-B1 的内容。
- 下一步：用户复核计划并选择 Subagent-driven 或 Native 执行方式；选择和计划确认前不修改产品代码。

## 2026-09-22 — TikTok P3-B0 录制回放持久化（开始）

- 目标：扩展追加写数据验证运行，使其能记录 Mock 或经审批的录制回放摘要。
- 范围：新增正向/回滚迁移、SQLModel 字段、条件约束、同租户审批人/范围外键和聚焦迁移测试。
- 安全边界：数据库不增加原始 dataset、文件名、请求体或值级错误字段；运行记录继续 FORCE RLS 且禁止更新、删除。
- 已知限制：本步骤不实现请求解析、录制运行服务、API 或界面；真实 PostgreSQL 验收仍取决于可选环境门禁。

## 2026-09-22 — TikTok P3-B0 录制回放持久化（完成）

- 变更：扩展 `TikTokDataValidationRun` 的 12 个 nullable 录制审计字段；新增正向/回滚迁移、recorded/mock 条件约束、同租户审批人和范围外键、索引与 RLS 重申。
- 红绿证据：新测试首次以迁移文件不存在和模型缺少全部 recorded 字段失败；修正测试仓库根后仍保持 3 项预期失败。最小实现后迁移新旧测试 5 项通过。
- 回滚策略：存在 recorded 审计行时 down migration 明确失败；无 recorded 行时才删除新列并恢复 Mock-only 约束，避免静默丢失证据。
- 验收补充：可选 PostgreSQL 测试新增有效 recorded 行、审批人与执行人相同拒绝以及追加写保护；未配置环境时只记录为未运行。
- Ruling：计划正文误写 11 个 recorded 字段，批准规格和字段清单实际为 12 个；实现以规格为准，包含固定声明版本字段。
- 下一步：实现 2 MiB 有限读取、严格六集合结构、敏感键拒绝和契约摘要。

## 2026-09-22 — TikTok P3-B0 有限且无秘密的录制输入（开始）

- 目标：实现 2 MiB 实际字节限制、严格六集合结构、敏感键归一化拒绝、审批时间结构和确定性契约摘要。
- 范围：新增 recorded 输入模块、严格 Pydantic 请求模型和聚焦测试；本步骤不写数据库、不改变 readiness、不新增 API 路由。
- 安全边界：原始 JSON 只存在请求处理内存；异常仅包含稳定代码，不包含键路径、值或解析片段；业务 ID 必须由输入方预先稳定假名化。
- Ruling：30 个业务字段不含现有新鲜度检查必需的 `observed_at`；将其作为每个集合允许的保留验证时间元数据，不纳入业务字段目录。

## 2026-09-22 — TikTok P3-B0 有限且无秘密的录制输入（完成）

- 变更：新增录制输入流式读取器、严格六集合请求模型、大小/集合/总量/字符串/深度限制、敏感键归一化拒绝、时区与时间顺序校验、内存规范化及确定性契约摘要。
- 红绿证据：入口测试先因模块不存在失败；深层嵌套用例随后稳定复现 `RecursionError`，加入显式深度门禁后全部通过。
- 安全结果：2 MiB 限制按实际流字节执行且不依赖 `Content-Length`；拒绝错误只返回稳定代码，不包含原始键、值、解析片段或请求体。
- 验证：`src/tests/backend/test_tiktok_recorded_validation.py` 20 项通过；Ruff 覆盖输入模块、请求模型和测试并通过。
- 下一步：复用现有字段校验器实现 recorded 运行事务，并让 readiness 独立评估最新 Mock 与最新 recorded 证据。

## 2026-09-22 — TikTok P3-B0 录制运行与就绪度（开始）

- 目标：复用同一字段校验器执行经审批录制回放，并使 readiness 分别依据最新 Mock 与最新 recorded 运行。
- 范围：实现单事务录制运行、历史回放时钟、严格范围/契约/目录/审批复核和 recorded blocker；不新增 API 或界面。
- 事务边界：服务在写入前重新读取当前范围、完整字段目录、审批人与契约摘要；任何冲突均不产生运行记录。
- 证据规则：运行只保存摘要与审批元数据；最新运行按 `created_at DESC, id DESC` 决定；recorded 通过不升级能力证据等级，真实 E3 与授权门禁保持独立。

## 2026-09-22 — TikTok P3-B0 录制运行与就绪度（完成）

- 变更：泛化数据校验器并保留 Mock 兼容包装；新增必需集合空值检查、经审批 recorded 单事务运行、独立最新 Mock/recorded 选择及六类 recorded 失效 blocker。
- 红绿证据：服务测试先因 `run_recorded_data_validation` 不存在而在收集阶段失败；实现后又发现录制白名单误含目录外第 31 字段及测试误匹配 `dataset_digest`，按批准的 30 字段规格修正后通过。
- 安全与隔离：recorded 行只保存摘要、检查结果、范围/契约快照和审批元数据；测试覆盖同租户有效独立审批人、跨租户/停用/自审批拒绝、范围 revision 冲突零写入、目录缺失零写入、租户隔离及能力证据零变更。
- 就绪度：最新 recorded 按 `created_at DESC, id DESC` 稳定选择；失败、范围变化、契约变化、审批过期和目录版本变化均重新阻断，Mock 仍不能产生真实数据就绪。
- 验证：录制入口与数据验证服务矩阵 60 项通过；Ruff 覆盖本步骤全部 Python 与测试文件并通过。
- 下一步：增加管理员 recorded 运行 API，并把输入错误映射为稳定、无原始内容的 HTTP 响应。

## 2026-09-22 — TikTok P3-B0 录制验证 API（开始）

- 目标：新增仅租户管理员可调用的本地 recorded 运行路由，把入口与服务的稳定错误映射为无原始内容的 HTTP 响应。
- 范围：新增一个 POST 路由、路由级流式输入/权限/租户/冲突/质量失败测试，并精确更新 TikTok 路由与 Python 文件冻结审计。
- 安全边界：FastAPI 依赖先完成身份认证，路由随后按实际字节流读取再解析；输入异常只返回 `code` 和固定 `message`，服务异常统一回滚。
- 外部副作用：该路由只写本地追加式摘要，不调用外部 HTTP，不加入任何外部写能力清单。

## 2026-09-22 — TikTok P3-B0 录制验证 API（完成）

- 变更：新增 `POST /api/enterprise/tiktok/data-validation/runs/recorded`；路由在依赖认证后流式读取 JSON，并把输入、缺失和冲突异常映射为稳定状态码及 `{code,message}`。
- 红绿证据：API 测试先因路由不存在而在收集阶段失败；实现后完整矩阵发现冻结路由/文件计数的下游生产就绪断言仍为旧值，更新为 30 条路由和 14 个 TikTok Python 文件后通过。
- 安全结果：覆盖管理员成功、质量失败仍返回 200、成员 403、租户引用 404、scope revision 409、2 MiB 超限 413、类型 415、畸形/敏感键 422；响应不含原始标记或文件名。
- 外部写门禁：静态审计已显式纳入 recorded 路由和输入模块，仍无外部 HTTP 写调用、未审计网络依赖或外部写 Skill。
- 验证：Task 4 后端矩阵 40 项通过；Ruff 覆盖 API、输入、冻结门禁及相关测试并通过。
- 下一步：在管理员数据验证工作台增加本地 JSON 选择、审批元数据表单、运行结果与 blocker 展示。

## 2026-09-22 — TikTok P3-B0 管理员录制回放界面（开始）

- 目标：在数据验证工作台增加管理员专用的脱敏 JSON 录制回放表单，并展示安全的 recorded 运行摘要和 blocker。
- 范围：提取共享类型、新增录制表单、接入工作台、补齐中英文文案和组件/集成测试；成员继续只读且不看到文件或提交控件。
- 客户端边界：File 仅保存在组件 state，解析后的 dataset 只在提交期间存在；先按 `file.size` 拒绝超限，不使用浏览器存储，不记录控制台，不发送文件名。
- 语义边界：recorded 成功或质量失败均刷新工作台；通过只代表回放验证通过，不宣称逐动作 E3、真实授权或 `real_data_ready` 已满足。

## 2026-09-22 — TikTok P3-B0 管理员录制回放界面（完成）

- 变更：提取数据验证共享类型；新增管理员录制回放表单并接入工作台；运行区统一为“验证运行”，区分 Mock/录制回放并仅展示安全审批引用与有效期。
- 红绿证据：组件测试先因文件不存在失败，面板测试同时证明录制控件和摘要尚未接入；实现后 15 项组件/集成测试通过。
- 客户端安全：选择时先拒绝超过 2 MiB 的文件；文件只驻留组件 state，JSON 只在提交局部变量中解析；请求不含文件名，异常不回显解析内容，不写控制台，成功或失败均清空文件。
- 权限与审批：仅管理员挂载文件和提交控件；当前用户从审批人列表排除；active scope、文件、完整元数据、独立审批人和脱敏声明缺一时提交禁用；本地时间统一转 UTC。
- 验证：聚焦 Vitest 2 文件/15 项通过；前端测试类型检查、i18n（4,297 条英文映射）和 Vite 配置检查通过。
- 下一步：运行完整后端/前端门禁，并用管理员和成员角色在浏览器验证真实页面交互与只读边界。

## 2026-09-22 — TikTok P3-B0 录制回放最终验收（开始）

- 目标：对完整 recorded 增量执行后端矩阵、静态检查、全量前端门禁、管理员/成员浏览器验收和整分支规格自审。
- 范围：仅为验收发现的缺陷修改 Tasks 1–5 文件；随后更新项目记忆、文档索引、会话交接与安全截图。
- 环境规则：PostgreSQL 验收仅在显式环境门禁存在时运行；完整后端基线不作为本功能新增门禁，使用批准计划列出的 TikTok 聚焦矩阵和测试布局守卫。
- 截图规则：只保存不含原始 dataset、浏览器文件名、凭据、授权载荷或个人数据的结果摘要；任何不安全或无法取得的截图均省略并精确记录原因。

## 2026-09-22 — TikTok P3-B0 录制回放最终验收（完成）

- 整分支自审：按 `5a34f63...HEAD` 对照批准规格、租户/RLS、追加写、2 MiB 实际字节、严格 schema、审批分离、回放时钟、失效规则、最新运行、E3 隔离和成员只读边界。Native 模式未使用子代理，最终审查为本代理自审。
- 审查修复：发现 Python JSON 默认接受 `NaN`/`Infinity`，以及审批审计身份字段接受纯空白。新增 6 个回归用例先全部失败；实现 finite JSON 拒绝、首尾空白归一化和空白值拒绝后 6 项通过，修复提交为 `aa7f433`。
- 后端最终证据：完整 TikTok 聚焦矩阵 148 项通过；测试布局守卫确认 1,219 个 tracked 路径合规；本次 Python 静态检查通过，共享 `models.py` 仅沿用既有 `UP045,FURB157` 忽略。首次矩阵因隐藏 `basetemp` 的 Windows 权限错误出现 15 个 setup error；改用系统临时目录后同一矩阵全绿。
- PostgreSQL 边界：`STAFFDECK_RUN_POSTGRES_ACCEPTANCE` 不存在，因此只执行了静态迁移/RLS/约束测试；未对真实 PostgreSQL 应用迁移，也不宣称生产数据库验收。
- 前端最终证据：完整 Vitest 67 文件/294 项通过；测试 TypeScript 检查、i18n（4,297 条英文映射）、Vite 配置检查和 2,166 模块生产构建通过。构建缓存首次因宿主权限无法写入，清理生成缓存并在获准上下文重跑后通过；仅保留既有大 chunk 警告。
- 浏览器限制：重置后再次读取 computer-use inventory，仍返回空 browser 列表和 `nodeRepl.fetch request failed`。因此管理员/成员 recorded 可视化验收与新截图未执行；旧 Mock 截图未冒充本功能证据。
- 安全清理：原始 dataset、文件名、凭据或外部授权载荷未写入日志、数据库、截图或测试产物。系统临时 pytest 目录在验证后删除；构建输出保持为项目既有 ignored 产物。
- 剩余风险：当前运行保存 scope revision 和 contract digest，工作台后续读取会把并发变更后的记录判 stale，但服务未将所有并发 scope/contract/evidence 更新串行化为单一锁定快照。当前授权判断必须读取最新 workspace readiness，不能只依赖历史 `real_data_ready_snapshot`。
- 下一步：浏览器控制恢复后补做管理员成功/质量失败及成员只读验收；随后独立取得逐动作 E3 `real_account` 与有效资产授权。P3-B1 的 30 条历史记录业务对照仍未完成。

## 2026-09-22 — TikTok P3-B0 本地整合尝试（开始）

- 目标：按用户选择将 `codex/tiktok-p3b0-recorded-validation` 线性整合回目标分支 `main`，随后开始 recorded 浏览器验收。
- 范围：只检查目标分支、工作树状态和分叉关系；不暂存、提交、移动、重置或覆盖主工作树中的既有改动。
- 已知阻塞：合并前必须确认 `main` 无会被功能分支覆盖的未提交内容，并保持无 merge commit 的线性历史。

## 2026-09-22 — TikTok P3-B0 本地整合尝试（阻塞）

- 结果：未执行 merge、rebase、stash、reset 或主工作树文件修改。`main` 仍在 `5a34f63`，功能分支在 `4ab6383`，共同基点为 `5a34f63`。
- 阻塞：主工作树已有未提交的 `AGENTS.md`、`docs/DEVELOPMENT_LOG.md`、`src/deploy/staffdeck-platform/scripts/provision-agent-m2m.py`、`src/scripts/dev_supervisor.py`、`src/tests/backend/test_dev_scripts.py`，以及未跟踪的 `src/tests/backend/test_agent_m2m_provisioning.py`。其中 `docs/DEVELOPMENT_LOG.md` 也被功能分支修改，无法在不处理用户改动的情况下安全线性整合。
- 下一步：由用户先提交、转移或明确授权处理上述主工作树改动；随后重新检查状态，线性整合功能分支并在合并结果上复验，再开始 recorded 管理员/成员浏览器验收。

## 2026-09-22 — TikTok P3-B0 本地整合恢复（完成）

- 用户授权保留主工作树改动后继续合并。六个既有改动文件已原样保存到安全分支 `codex/preserve-main-before-tiktok-merge-20260922` 的提交 `33e6ef7`，未丢弃、覆盖或推送。
- 集成方式：回到干净的 `main@5a34f63`，以 squash 方式整合 `codex/tiktok-p3b0-recorded-validation@96dccdc`，保持主干线性且不产生 merge commit。
- 合并树验证：TikTok 后端矩阵 148 项通过；测试布局 1,219 路径通过；Ruff 通过；完整前端 67 文件/294 项、测试类型检查、i18n 4,297 条、配置检查和 2,166 模块生产构建通过。`STAFFDECK_RUN_POSTGRES_ACCEPTANCE` 仍未配置，未宣称真实 PostgreSQL 验收。
- 下一步：提交 squash 结果后，将 `33e6ef7` 中的六个原主工作树改动恢复为未提交状态并保留安全分支；随后开始 recorded 管理员/成员浏览器验收。

## 2026-09-22 — TikTok recorded 并发一致性加固（开始）

- 目标：确保 recorded 回放从读取 scope/契约/审批/能力证据/有效授权到追加运行摘要期间使用一个可串行化的租户内快照，消除已知的并发陈旧提交窗口。
- 范围：仅修改 TikTok 数据验证服务及聚焦后端测试；不新增表、迁移、API、界面、外部调用或外部写能力。
- 设计：PostgreSQL 以固定顺序对当前 scope、30 个字段契约、独立审批人、能力证据和有效授权获取共享行锁，并在同一事务内完成校验、就绪计算与 append-only 运行提交；SQLite 保持兼容。
- 验证：先写 PostgreSQL 锁意图、并发 scope/contract、审批失效和双租户隔离的失败用例，观察 RED 后再实现；最终运行完整 TikTok 聚焦矩阵、Ruff 和真实本地 PostgreSQL 验收。
- 已知限制：主工作区保留用户未提交改动，因此本步骤在 `codex/tiktok-recorded-concurrency` 独立工作树执行；浏览器桥此前不可用，视觉验收在后端门禁通过后再试。


## 2026-09-22 — TikTok recorded 并发一致性加固（完成）

- 实现：`run_recorded_data_validation` 在同一事务内按 scope、字段契约、独立审批人、能力证据、有效授权的固定顺序获取 PostgreSQL `FOR SHARE` 锁；字段契约按 `field_code`、能力证据按 `entry_code/subject_key`、授权按 `id` 排序。校验、就绪快照和 append-only run 提交保持同一事务，SQLite 路径保持兼容。
- RED→GREEN：新增行为测试实际调用 recorded 服务并捕获其 SQL。修复前预期 5 类共享锁、实际为 0，测试按预期失败；实现后识别 5 类锁并验证租户过滤和稳定顺序，单项测试通过且无警告。
- 聚焦验证：recorded/数据验证 67 项通过；完整 TikTok 后端矩阵 149 项通过；测试布局守卫确认 1,219 个 tracked 路径；Ruff 对生产文件和测试通过。
- 真实 PostgreSQL：使用受保护本地配置执行两个并发事务，scope、字段契约、独立审批人、能力证据的无值 UPDATE 均在 300 ms `lock_timeout` 内被 recorded 快照锁阻塞；探针事务全部回滚，新增持久验收记录为 0。当前租户没有 active authorization 行，因此授权锁由 SQL 行为测试覆盖，未伪造真实授权。
- 仓库级基线：完整后端收集 2,381 项，结果为 2,334 passed、31 failed、11 skipped、5 errors；失败/错误集中在既有 advertising、channel、Feishu、general skills、Harness、runtime、tool 路径，没有 TikTok 节点。本次 149 项必需 TikTok 门禁保持全绿，未修改无关基线模块。
- 自审：无 Critical 或 Important 发现。锁住当前 active authorization 可防止撤销导致错误正向快照；并发新增/激活授权仍可能让历史快照暂时偏保守，但不会产生错误的 `real_data_ready=true`，当前 workspace 读取会重新计算。
- 下一步：提交并按仓库线性历史规则合入 `main`；浏览器桥恢复后补做管理员/成员视觉验收。P3-B1 仍需真实 E3、有效资产授权和 30 条业务记录对照。

## 2026-09-22 — TikTok recorded 并发一致性线性整合（完成）

- 整合：`codex/tiktok-recorded-concurrency@608ccce` 已以 squash 方式应用到 `main@c13dc9d` 的后继提交，未产生 merge commit；源分支与本地安全分支均保留且未推送。
- 合并树验证：完整 TikTok 后端矩阵 149 项通过；测试布局守卫确认 1,219 个 tracked 路径；本次生产与测试 Python 文件 Ruff 通过；暂存差异检查通过。Pytest 仅提示无法写入项目 `.pytest_cache`，系统临时 `basetemp` 中的测试本身全部成功。
- 范围：合并只包含 recorded 事务共享锁、稳定查询顺序、对应行为测试及开发记录；没有迁移、API、前端或外部调用变化。
- 主工作区保护：合并前的七个未提交路径已保存到 `codex/preserve-main-before-concurrency-merge-20260922@bb9c9f2`；提交合并结果后将原样恢复为未提交状态。
- 剩余风险与下一步：完整后端既有非 TikTok 基线仍非全绿；浏览器视觉验收、真实 E3/有效资产授权和 P3-B1 的 30 条业务记录对照仍待完成。


## 2026-09-22 — 任务会话删除外键冲突修复（开始）

- 目标：修复任务会话因 `work_task_runs_session_fk` 阻止物理删除而返回 HTTP 500 的问题。
- 范围：普通会话保持物理删除；存在工作任务运行记录的会话改为用户侧软删除并从聊天入口隐藏，同时保留执行记录与审计数据。
- 测试策略：先添加覆盖任务会话删除、普通会话删除和已删除会话不可见性的回归测试并确认失败，再进行最小实现。
- 已知阻塞：隔离工作树不包含被忽略的虚拟环境和前端依赖；验证复用主工作区已安装的 Python 环境，并为 pytest 使用独立临时目录。

## 2026-09-22 — 任务会话删除基线检查（完成）

- 变更文件：仅追加本开发日志；尚未修改产品代码或测试。
- 验证：会话清理、工作任务执行和快照聚焦矩阵共 12 项，11 项通过；`test_workspace_cleanup_unlinks_exact_symlink_without_following_target` 因当前 Windows 账户缺少创建符号链接权限失败。
- 判断：失败点发生在测试准备阶段的 `Path.symlink_to`，与会话删除、工作任务外键和本次拟修改路径无关，按仓库已记录的平台基线保留。
- 下一步：添加任务会话软删除回归测试，确认现有实现会把受保护会话物理删除并产生预期红灯。

## 2026-09-22 — 任务会话软删除 TDD 红阶段（开始）

- 目标：用真实 `ChatSession`、`WorkTaskRun`、消息和 Harness 工作区证明任务会话删除必须保留审计数据，同时从用户聊天列表隐藏。
- 范围：仅修改 `src/tests/backend/test_harness_session_cleanup.py`；本步骤不改模型、迁移或生产逻辑。
- 预期红灯：当前实现会物理删除会话及消息，因此断言数据库会话仍存在时失败。

## 2026-09-22 — 任务会话软删除 TDD 红阶段（完成）

- 变更文件：`src/tests/backend/test_harness_session_cleanup.py` 新增任务会话删除回归场景。
- 红灯证据：聚焦用例稳定失败于 `assert preserved_session is not None`；现有实现已物理删除被 `WorkTaskRun` 引用的会话，和真实 PostgreSQL 外键失败的根因一致。
- 覆盖目标：响应成功、会话软删除时间、工作任务运行/消息/Harness 工作区保留，以及用户聊天列表隐藏。
- 下一步：添加最小软删除模型与服务逻辑，使该用例转绿，同时维持普通会话物理删除测试。

## 2026-09-22 — 任务会话软删除 TDD 绿阶段（开始）

- 目标：当同租户 `WorkTaskRun` 引用会话时设置删除时间并保留审计数据；无引用时继续执行现有物理清理。
- 范围：修改 `ChatSession` 模型、会话清理服务和聊天 API 查询/删除入口；本步骤暂不添加生产迁移文件。
- 隔离规则：任务运行保护判断同时匹配 `tenant_id` 与 `session_id`；软删除会话对用户列表、读取、重命名和继续对话均表现为不存在，后台审计记录仍可按主键访问。

## 2026-09-22 — 任务会话软删除核心路径（完成）

- 变更：`ChatSession` 新增可空删除时间；会话清理服务在发现同租户工作任务运行记录时保留会话、消息和工作区，否则沿用物理删除；聊天列表过滤删除标记。
- 绿灯证据：任务会话软删除和普通会话物理删除两个聚焦用例均通过。
- 剩余风险：读取、重命名和继续对话的集中访问守卫虽已设计，但尚未用红灯证明；生产迁移也尚未添加。
- 下一步：先移除未被测试锁定的访问守卫改动，增加软删除会话访问拒绝断言并确认红灯，再恢复最小守卫实现。

## 2026-09-22 — 软删除会话访问守卫 TDD 红阶段（开始）

- 目标：证明软删除会话不能通过所有集中聊天访问守卫再次读取、修改、删除或继续对话。
- 范围：扩展现有任务会话回归测试；暂时撤回三个尚未被红灯证明的删除标记判断，保留已通过测试的软删除和列表过滤逻辑。
- 预期红灯：第一个集中访问守卫仍会返回软删除会话，而不是抛出 404。

## 2026-09-22 — 软删除会话访问守卫 TDD 红阶段（完成）

- 红灯证据：软删除和列表隐藏断言均已通过，但第一个集中访问守卫没有抛出 `HTTPException`，聚焦用例以 `Failed: DID NOT RAISE HTTPException` 失败。
- 结论：仅过滤列表不足以完成用户侧删除语义，必须在集中所有者读取、可读性检查和继续对话检查中统一拒绝删除标记。
- 下一步：恢复三个最小删除标记判断，并重跑任务会话与普通会话删除用例。

## 2026-09-22 — 软删除会话访问守卫 TDD 绿阶段（开始）

- 目标：三个集中访问守卫对 `deleted_at` 非空会话统一返回 404。
- 范围：仅修改 `src/backend/app/api/chat.py` 的既有守卫条件，不改变权限、团队或交接访问规则。
- 验证：任务会话软删除用例必须转绿，普通会话物理删除用例必须保持通过。

## 2026-09-22 — 软删除会话访问守卫 TDD 绿阶段（完成）

- 变更：所有者访问、可读性检查和继续对话三个集中守卫统一把软删除会话视为不存在，保留原租户、所有者、团队和交接权限逻辑。
- 验证：任务会话软删除与普通会话物理删除共 2 项通过。
- 剩余工作：真实 PostgreSQL 仍缺 `sessions.deleted_at` 列，当前实现仅能在由 SQLModel 新建的测试数据库中运行。
- 下一步：以静态迁移契约测试驱动可逆生产迁移。

## 2026-09-22 — 会话软删除迁移 TDD 红阶段（开始）

- 目标：为 `public.sessions.deleted_at` 和查询索引建立幂等、可回滚的 PostgreSQL 迁移契约。
- 范围：先新增静态迁移测试，不创建迁移文件，不连接或修改本地 PostgreSQL。
- 预期红灯：上行和回滚迁移文件不存在。

## 2026-09-22 — 会话软删除迁移 TDD 红阶段（完成）

- 红灯证据：静态迁移测试失败于 `assert UP.is_file()`，确认测试会阻止模型字段在缺少生产迁移时交付。
- 下一步：添加仅包含删除时间列和索引的幂等上行迁移，以及反序移除索引和列的回滚迁移。

## 2026-09-22 — 会话软删除迁移 TDD 绿阶段（开始）

- 目标：让现有 PostgreSQL `sessions` 表具备与 SQLModel 一致的可空时区时间列和索引。
- 范围：新增一对 SQL 迁移；不改变 `work_task_runs_session_fk` 的 `ON DELETE RESTRICT` 审计保护。
- 回滚顺序：先删除索引，再删除列；两步均使用 `IF EXISTS`，上行使用 `IF NOT EXISTS`。

## 2026-09-22 — 会话软删除迁移 TDD 绿阶段（完成）

- 变更：新增 `20260922_chat_session_soft_delete_v1.sql` 与对应回滚迁移，为 `public.sessions` 添加可空 `TIMESTAMPTZ deleted_at` 和 `ix_sessions_deleted_at`。
- 约束保持：`work_task_runs_session_fk ON DELETE RESTRICT` 未修改，任务执行审计仍由数据库阻止意外物理删除。
- 验证：静态迁移契约、任务会话软删除、普通会话物理删除共 3 项通过；首次组合运行因长临时路径触发 Windows `WinError 206`，改用短 basetemp 后原样通过。
- 下一步：用跨租户同会话标识的回归测试锁定工作任务保护查询的租户边界。

## 2026-09-22 — 任务运行保护租户边界 TDD 红阶段（开始）

- 目标：其他租户恰好使用相同 `session_id` 的工作任务运行不得阻止目标租户普通会话物理删除。
- 范围：新增一个隔离回归用例；暂时移除保护查询中的租户条件以证明测试能捕获跨租户误判。
- 预期红灯：错误软删除目标会话，导致物理删除断言失败。

## 2026-09-22 — 任务运行保护租户边界 TDD 红阶段（完成）

- 红灯证据：移除租户条件后，其他租户的同名 `WorkTaskRun` 导致目标普通会话被错误软删除，测试失败于会话仍存在。
- 结论：保护查询必须以 `tenant_id + session_id` 共同限定，不能把会话 ID 当作跨租户授权或生命周期边界。
- 下一步：恢复租户条件并运行完整会话清理聚焦矩阵（排除已知 Windows 符号链接权限用例）。

## 2026-09-22 — 任务运行保护租户边界 TDD 绿阶段（开始）

- 目标：恢复同租户保护判断，使目标租户普通会话维持物理删除，其他租户运行记录保持不变。
- 范围：仅恢复 `WorkTaskRun.tenant_id == session.tenant_id` 条件。
- 验证：跨租户、任务软删除、普通物理删除和迁移契约必须共同通过。

## 2026-09-22 — 任务运行保护租户边界 TDD 绿阶段（完成）

- 变更：恢复同租户工作任务运行保护条件；其他租户同名运行记录不再影响目标会话生命周期。
- 验证：会话清理、工作任务执行/快照和迁移契约矩阵 14 项通过，已知 Windows 符号链接权限用例单独排除；聊天绑定、附件和追踪 65 项通过；团队工作区除既有挂起的 orphan 清理用例外 10 项通过。
- 静态检查：新清理服务与测试 Ruff 通过；大型共享 `chat.py`/`models.py` 的关键错误规则通过；测试布局守卫确认当前 1,219 个已跟踪路径合规。
- 已知基线：完整默认 Ruff 仍报告共享文件中的存量 `B008`、`UP045` 等债务；未将其混入本修复。扩展组合测试确认既有 orphan 清理用例会挂起，已拆分并记录。
- 下一步：记录任务执行审计与聊天删除语义的长期 ADR，并更新项目记忆和文档索引。

## 2026-09-22 — 任务会话删除保留策略 ADR（开始）

- 目标：记录任务运行审计不可随用户删除聊天级联丢失，以及任务会话使用用户侧软删除的长期边界。
- 范围：新增 ADR 0002，并更新 ADR 索引、文档总索引和稳定项目记忆；不改变实现。
- 关键取舍：保留 `ON DELETE RESTRICT`；拒绝级联删除执行记录、解除外键或只返回 409；普通会话仍物理删除。

## 2026-09-22 — 任务会话删除保留策略 ADR（完成）

- 变更：新增 ADR 0002，记录任务会话用户侧软删除、普通会话物理删除、企业审计/后台继续保留内部访问及跨租户保护边界。
- 文档同步：更新 `docs/adr/README.md`、`docs/README.md` 和 `docs/PROJECT_MEMORY.md`，没有创建并行状态文档。
- 回滚风险：回滚 `deleted_at` 迁移会使保留的任务会话重新可见，ADR 明确要求应用与迁移协调回滚。
- 下一步：执行最终聚焦矩阵、静态检查、暂存后测试布局守卫和独立代码审查。

## 2026-09-22 — 任务会话删除修复最终验证（开始）

- 目标：对最终代码、迁移、测试和文档执行新鲜验证，随后提交隔离分支并请求独立代码审查。
- 范围：聊天绑定/附件/追踪、会话清理、团队会话、工作任务执行/快照、迁移契约、Ruff、diff 与测试布局。
- 基线排除：当前 Windows 无符号链接权限；`test_purge_orphaned_chat_sessions_cleans_pre_fix_leftovers` 在未修改路径中稳定挂起。二者单独记录，不用于掩盖本修复失败。

## 2026-09-22 — 任务会话删除修复最终验证（完成）

- 最终后端矩阵：聊天绑定、附件、追踪、会话清理、团队工作区、工作任务执行/快照和迁移契约共 89 项通过，2 项按已确认基线排除（Windows 符号链接权限、既有 orphan 清理挂起）。
- 静态检查：新清理服务和测试的完整 Ruff 检查通过；共享 `chat.py`、`models.py` 的 `E9,F63,F7,F82,I001` 关键门禁通过；暂存差异 `git diff --cached --check` 通过。
- 布局：新增测试暂存后，测试目录守卫确认 1,223 个 tracked 路径全部符合 `src/tests` 边界。
- 数据库边界：上行/回滚迁移静态契约通过；本步骤未读取受保护 `.env`、未连接或修改恢复的 PostgreSQL，因此不宣称真实迁移或 PostgreSQL 运行验收。
- 下一步：提交隔离分支，执行独立代码审查；无 Critical/Important 问题后尝试按仓库规则线性整合回 `main`。

## 2026-09-22 — 独立评审问题验证与补强（开始）

- 目标：逐项验证独立评审指出的隐藏会话访问面、任务运行外键租户语义和删除时间类型问题，并以回归测试驱动修复。
- 已确认问题：人工接管列表/回复和消息反馈入口未检查 `sessions.deleted_at`；生产 `work_task_runs_session_fk` 仅引用 `session_id`，与应用按 `tenant_id + session_id` 判断保护关系的语义不一致，SQLite 测试未覆盖该 PostgreSQL 约束。
- 时间约定：项目主模型统一使用 `utc_now()` 生成无时区 UTC，任务执行迁移也使用 `timestamp without time zone`；本修复将让 `deleted_at` 沿用该约定，不单独引入 `TIMESTAMPTZ`。
- 范围：先添加会失败的接口与迁移/模型契约测试，再做最小实现；不连接或修改真实 PostgreSQL。

## 2026-09-22 — 独立评审补强 TDD 红阶段（完成）

- 红灯证据：4 项聚焦测试全部按预期失败；反馈目标仍接受已删除会话，人工接管列表仍返回已删除会话请求，迁移仍使用 `TIMESTAMPTZ`，模型也缺少租户复合唯一键/外键。
- 测试纠偏：原“其他租户运行可引用目标租户会话”的 SQLite 用例描述了生产复合外键应禁止的非法状态，将由模型与迁移约束测试取代。
- 下一步：在共享访问入口统一拒绝 `deleted_at`，为任务运行引用加入 `(tenant_id, session_id)` 复合外键，并让迁移时间类型匹配现有无时区 UTC 约定。

## 2026-09-22 — 独立评审补强 TDD 绿阶段（开始）

- 目标：以最小代码和可逆迁移修复上述 4 个红灯，不改变普通会话物理删除与任务会话审计保留的既定行为。
- 数据库安全：上行迁移在同一事务中先建立会话租户复合唯一键，再替换任务运行外键；已有跨租户错配数据会使新外键建立失败并整体回滚，不静默放宽约束。

## 2026-09-22 — 独立评审补强 TDD 绿阶段（完成）

- 入口修复：人工接管列表排除 `deleted_at` 非空的会话，人工回复和消息反馈共享校验拒绝已删除会话；接管与反馈审计记录本身仍保留。
- 数据库修复：`sessions` 模型加入 `(tenant_id, id)` 唯一约束，`work_task_runs` 模型及生产迁移使用 `(tenant_id, session_id)` 复合限制外键；回滚迁移恢复原单列外键。
- 时间一致性：`deleted_at` 迁移改为 `TIMESTAMP WITHOUT TIME ZONE`，与 `utc_now()` 和现有任务执行时间列一致。
- 测试纠偏：移除会构造生产数据库非法跨租户引用的 SQLite 用例，改由模型元数据和可逆迁移契约直接锁定租户关系。
- 验证：此前 4 个失败断言现全部通过（反馈、人工接管、迁移、模型约束）。

## 2026-09-22 — 评审补强扩大回归（开始）

- 目标：覆盖完整人工接管、会话清理、工作任务执行/快照及迁移契约，并执行聚焦 Ruff、测试布局和差异检查。
- 基线排除保持不变：Windows 符号链接权限用例不运行；既有 orphan 清理挂起用例单独排除并如实记录。

## 2026-09-23 — 评审后领域文档同步（开始）

- 目标：让 ADR 0002、稳定项目记忆和会话交接准确反映租户复合外键、隐藏入口覆盖与无时区 UTC 迁移类型。
- 范围：只修正文档中“外键不变”“TIMESTAMPTZ”“尚未评审/提交”等已经过时的描述，不扩大功能范围或宣称真实 PostgreSQL 验收。

## 2026-09-23 — 评审后领域文档同步（完成）

- ADR/记忆：明确任务运行使用 `(tenant_id, session_id)` 引用会话 `(tenant_id, id)`，并记录跨租户错配会让迁移失败回滚。
- 用户边界：补充人工接管列表/回复与消息反馈均遵守用户侧删除标记，内部执行和企业审计仍保留记录。
- 交接：更新初始提交、独立评审、修复状态与迁移时间类型；继续明确尚无真实 PostgreSQL 验收。

## 2026-09-23 — 评审补强最终验证（开始）

- 目标：对当前完整差异执行新鲜测试、Ruff、测试布局、暂存差异和工作树状态检查；只有全部所需门禁有当前证据后才提交并请求复审。
- 范围：100 项会话/接管/任务聚焦矩阵、10 项团队工作区矩阵、聚焦静态检查、`check_test_layout.py` 与 `git diff --cached --check`。

## 2026-09-23 — 评审补强最终验证（完成）

- 后端矩阵：人工接管、会话清理、工作任务执行/快照、迁移契约、聊天绑定/附件/追踪共 100 项通过，Windows 符号链接权限用例 1 项按已知基线排除。
- 团队工作区：10 项通过，既有 orphan 清理挂起用例 1 项按已确认基线排除。
- 静态与布局：聚焦 Ruff 两组均通过；测试布局守卫确认 1,223 个已跟踪路径合规；暂存差异空白检查通过。
- 数据库边界：仅验证模型元数据与可逆 SQL 契约，未连接或修改真实 PostgreSQL，不宣称迁移运行验收。
- 下一步：提交本轮评审修复并由原独立评审复核；无 Critical/Important 后再检查 `main` 的脏工作树是否允许安全线性整合。

## 2026-09-23 — 独立复审与分支收尾（开始）

- 提交：评审修复已提交为 `52d92fe`，工作树在提交后无未暂存代码变更。
- 复审结果：原评审复查 `c13dc9d..52d92fe`，确认先前两项 Important 均已解决；Standards 与 Spec 均无 Critical、Important 或 Minor，结论为 Ready to merge。
- 范围限制：复审未执行真实 PostgreSQL 上行/回滚；该项仍保持为部署前必做的运行验收，不伪装成已完成证据。
- 下一步：刷新最终交接记录并检查目标 `main` 的脏工作树与重叠文件，依据仓库自动线性整合规则执行或报告精确阻塞。

## 2026-09-23 — 独立复审与分支收尾（完成）

- 最新 HEAD 门禁：100 项会话/接管/任务矩阵与 10 项团队矩阵再次通过；聚焦 Ruff、1,223 路径布局守卫、空工作树差异检查均通过。
- 文档复核：评审发现交接中一处“暂存验证仍待执行”的过时 Minor 描述，已改为已通过的真实结果；无 Critical 或 Important。
- 整合阻塞：`main` 已从分叉点 `c13dc9d` 前进到 `67f3e42`，且主工作树有 6 个已修改文件和 1 个未跟踪测试；其中 `docs/DEVELOPMENT_LOG.md` 与 `docs/SESSION_HANDOFF.md` 和本分支重叠。
- 处置：未擅自暂存、提交、变基、覆盖或清理主工作树。需要先获得该批用户工作如何保存的明确决定，再把本分支变基到当前 `main`、复验并快进整合。

## 2026-09-23 — 会话删除修复整合（开始）

- 目标：按用户批准，将主工作树现有未提交改动完整保存到独立保护分支，再把已评审的会话删除修复线性整合回当前 `main`。
- 范围：`main@67f3e42` 当前有 7 个已修改文件与 2 个未跟踪文件；本轮新增的 `docs/README.md` 和架构文档也纳入保护快照。修复分支当前为 `5b782f3`。
- 已知风险：主工作树的开发日志与交接文档和修复分支重叠，变基时需要保留两边事实；真实 PostgreSQL 迁移与浏览器删除验收仍未执行。

## 2026-09-23 — 主工作树保护快照（完成）

- 保护分支：`codex/preserve-main-before-session-merge-20260923@722977f` 从 `main@67f3e42` 保存全部 7 个已修改文件和 2 个未跟踪文件；提交前 `git diff --cached --check` 通过，提交后该分支工作树干净。
- `main` 已切回 `67f3e42`，准备将修复分支变基到这一提交。保护分支不推送也不删除。
- 下一步：在隔离工作树里变基并解决日志、交接文档与 TikTok 代码变化的交叉；复验后快进整合。

## 2026-09-23 — 修复分支变基（开始）

- 目标：将已评审的会话删除修复线性移植到 `main@67f3e42`，同时保留主线提交的 TikTok 串行化修复与历史文档。
- 范围：仅修复分支四个既有提交和本轮整合记录；冲突以两边完整事实为准，不覆盖已保护的原始工作。

## 2026-09-23 — 修复分支变基（完成）

- 结果：修复分支已从 `c13dc9d` 变基到 `main@67f3e42`；`git merge-base main HEAD` 指向 `67f3e42`，当前变基后 HEAD 为 `21a1221`。
- 冲突：首个提交中的 `docs/DEVELOPMENT_LOG.md` 与 `docs/SESSION_HANDOFF.md` 和 TikTok 主线提交的新增章节相邻；逐段保留两边事实后，余下四个提交顺利重放，代码文件没有冲突。
- 验证前状态：主工作树又出现一段未提交架构调研日志；此记录已包含在保护提交 `722977f` 中，需要合并前重新确认主工作树边界。
- 下一步：对变基后的完整树重跑会话、人工接管、工作任务和 TikTok 相邻路径的测试及静态检查。

## 2026-09-23 — 变基后验证（开始）

- 目标：确认线性移植没有改变原修复的删除语义，且主线 TikTok 并发加固仍通过相关测试。
- 范围：会话/接管/工作任务/团队工作区聚焦测试、迁移契约、TikTok 数据验证测试、Ruff、测试布局与差异检查。

## 2026-09-23 — 变基后验证（完成）

- 后端：会话/人工接管/任务矩阵 100 项通过，Windows 符号链接权限用例 1 项按既有基线排除；团队工作区 10 项通过，既有 orphan 清理挂起用例 1 项排除；主线相邻的 TikTok 数据验证 40 项通过。
- 静态：聚焦 Ruff 两组通过；测试布局守卫确认 1,223 个已跟踪路径合规；`git diff main..HEAD --check` 通过；文档无冲突标记。
- 主工作树状态：独立架构调研正在 `main` 工作树追加新日志、README 索引和报告文件；合并前需对其最新状态再做保护快照。
- 下一步：更新交接状态、提交变基后验证记录，保存最新主工作树文档改动，完成最终评审并快进 `main`。

## 2026-09-23 — 变基后独立评审与交接修正（开始）

- 保护状态：合并期间新增的三份架构文档改动已保存到 `codex/preserve-main-active-before-session-merge-20260923@cfb5f5a`，当前 `main@67f3e42` 工作树干净。
- 独立评审：确认会话修复代码、迁移与测试和已批准版本逐字节一致，TikTok 主线文档也完整保留；无 Critical 或 Important，仅交接文档仍使用变基前的提交号及过时保护状态。
- 本步骤：修正交接中的基线、提交与保护快照描述，复查文档差异后执行线性快进。

## 2026-09-23 — TikTok P3-B1 最小看板与逐条对照（开始）

- 目标：实施已批准的 E01/E02/E07 首个切片，形成规范化历史事实、指标口径和人工逐条对照的可运行链路。
- 范围：仅处理已批准的脱敏历史数据、租户内只读查询和人工审核；外部读取与外部写入不在本轮。
- 已知阻塞：主干存在与本功能无关的未提交改动；真实 E3、授权及 30 条业务样本尚未取得，浏览器桥不可用。

## 2026-09-23 — TikTok P3-B1 历史事实与对照实现（阶段记录）

- 数据边界：新增批次、六领域规范化事实、v1 指标定义、追加式逐条核对及 Owner 快照五张租户表；上/下迁移包含组合外键、FORCE RLS、SELECT/INSERT 最小授权与 UPDATE/DELETE 拒绝触发器。P3-B0 recorded 摘要仍不保存业务值。
- 服务/API：仅从当前 active 试点、未过期且摘要一致的 recorded 数据集导入；按真实字节限制 2 MiB，并拒绝敏感字段、重复身份冲突和跨租户引用。支持筛选、分页、同业务键最新观测聚合、混合币种/缺失不可计算、被分配 BD 的追加核对，以及 30 条非合成记录的 Owner 确认；后续核对或 scope revision 变化使确认失效。
- 页面：TikTok 页新增历史事实标签，展示来源、口径版本、核对进度、筛选和分页；管理员导入、分配 BD 核对与业务 Owner 确认按权限显示。来源类别是管理员申报，不把录制回放成功或 Mock 视为 E3/真实来源证明。
- 冻结写门禁：经代码检查，新服务不引入外部网络或业务执行调用；四条仅作用于租户内工作台的路由及一个服务文件已加入显式审计白名单，冻结门禁仍检查任何未审新路由/模块或外部 HTTP 写。
- 红绿证据：后端最初因缺少事实模型/迁移失败，前端最初因缺少面板失败；聚焦修复后导入/对照/签署/权限/迁移测试通过。初次完整 TikTok 矩阵的两项失败均定位到冻结清单旧数量，白名单和期望值已同步，正在复跑。
- 已完成门禁：前端完整 Vitest 68 文件/297 项、测试类型检查、Vite 配置检查和 2,167 模块生产构建通过；i18n 4,352 条映射通过；测试布局守卫确认 1,219 个 tracked 路径；本次 Python 文件 Ruff 通过（共享模型仅忽略既有 UP045/FURB157）。
- 未完成验收：浏览器控制再次返回空 inventory 和 `nodeRepl.fetch request failed`，因此管理员/成员真实页面视觉验收未执行；PostgreSQL 真实迁移门禁标志未配置，暂仅有静态迁移测试。真实 E3、有效授权与 30 条业务历史样本亦未取得。

## 2026-09-23 — TikTok P3-B1 核对身份修正（完成）

- 自审发现同一业务键的多次观测可被误算为多条退出样本；改为按来源、领域和业务键选择最新事实参与 30 条核对门槛。新增 30 次观测同一业务键的回归用例，确认只计 6 条不同业务事实。
- 权限及语义修正：仅被分配 BD 能写核对，普通成员不能读试点数据；非管理员业务 Owner 也可见确认入口；导入选项只列 active BD；“已签收记录数”不再暗示平台签收真实性。
- 前端最终 68 文件/297 项、类型检查、生产构建与 i18n 检查通过；后端完整 TikTok 聚焦矩阵和分支整体验收结果记于后续完成记录。

## 2026-09-23 — TikTok P3-B1 分支静态与自动化验收（完成）

- 最终后端 TikTok 聚焦矩阵 161 项通过，包含冻结外部写门禁、新增角色/核对/导入测试和迁移静态检查；本次 Python Ruff 与共享模型既有规则豁免后均通过。
- 前端完整 Vitest 68 文件/297 项、测试类型检查、i18n 4,352 条、配置检查及 2,167 模块生产构建通过，构建仅保留既有大 chunk 警告；测试布局守卫通过。
- 固定风险：浏览器桥无法连接，未验证真实路由四种角色的视觉/操作路径；进程环境缺少 PostgreSQL 验收门禁和数据库 URL，新迁移尚未在真实 PostgreSQL 应用。30 条测试事实及 Owner 确认只是门槛测试，不是业务验收或生产批准。
- 下一步：固定 `main@67f3e42` 做代码/规格审查并修复发现，提交功能分支；待浏览器和安全的 PostgreSQL 验收环境可用后补验，满足仓库合并条件时再线性合入 `main`，保留主工作区七个既有改动。

## 2026-09-23 — TikTok P3-B1 固定基线审查修正（完成）

- 目标与范围：对 `main@67f3e42` 的 P3-B1 分支做规范及规格审查，修正路由授权、逐条对照证据、Owner 来源确认和指标口径。已知阻塞为主干并发推进且有无关未提交改动，浏览器桥及真实 PostgreSQL 验收环境不可用。
- 改动路径：`src/backend/app/api/tiktok.py`、`src/backend/app/db/models.py`、`src/backend/app/security/casbin_policy.csv`、`src/backend/app/tiktok/p3b1_history.py`、`src/backend/migrations/20260923_tiktok_p3b1_history_v1.sql`、`src/frontend-enterprise/src/i18n/en.json`、`src/frontend-enterprise/src/pages/tiktok/TikTokHistoryPanel.tsx`、`src/tests/backend/test_tiktok_p3b1_history.py`、`src/tests/backend/test_tiktok_p3b1_history_api.py`、`src/tests/frontend/TikTokHistoryPanel.test.tsx`、`docs/adr/0002-tiktok-recorded-validation-and-history-facts.md`、`docs/SESSION_HANDOFF.md`、本开发日志。
- 结果：Casbin 明确授权分配 BD 的逐条核对和所有潜在试点 Owner 的确认入口，服务仍要求精确活跃 Owner 身份；普通 BD 仅见本人分配事实。BD 每条结论需填写脱敏对照证据编号；Owner 对候选历史来源单独声明并登记证据编号。确认摘要绑定批次、recorded run、事实和对照引用，recorded 审批过期会撤销就绪显示。指标要求显式 UTC 时段，最新定义版本不会套算旧批次。页面把计数标为“候选历史已核对”，避免把管理员申报当作已证实来源。
- 验证命令与结果：`python -m pytest -q -p no:cacheprovider -c pytest.ini --basetemp=<系统临时目录> <src/tests/backend/test_tiktok* 与 test_postgres_tiktok* 文件>` 为 165 passed；`npm --prefix src/frontend-enterprise test` 为 68 files/297 passed；`npm --prefix src/frontend-enterprise run test:typecheck`、`run i18n:check`（4,359 映射）、`run config:check`、`run build`（2,167 模块）均通过；`python -m ruff check --no-cache` 对本次 Python 文件通过，共享 `models.py` 用仓库既有 `--ignore UP045,FURB157` 通过；`git diff --check` 通过。构建保留既有大 chunk 提示。
- 未验证与下一步：浏览器 inventory 再次返回 `nodeRepl.fetch request failed`，没有执行真实角色/路由视觉验收；未获得安全的 PostgreSQL 连接与验收门禁，因此迁移/RLS 仅为静态测试。当前通过的是功能测试与合成样本，非 E3、真实授权、30 条业务历史核对或生产批准。提交分支后运行 tracked 测试布局守卫；恢复浏览器和 PostgreSQL 验收后再考虑安全线性合并。主干已前进至 `ed6d4c7` 并有无关改动，不在本步修改。

## 2026-09-23 — TikTok P3-B1 审查修正提交与布局验收（完成）

- 审查修正已提交到独立分支 `codex/tiktok-p3b1-dashboard-reconciliation@b371dd5`，主工作树没有被修改或合并。
- 提交后执行 `python src/tests/check_test_layout.py`，1,230 个 tracked 路径符合 `src/tests` 边界；分支工作区干净。真实浏览器与 PostgreSQL 验收仍为下一步的必要条件。

## 2026-09-23 — TikTok P3-B1 主干集成准备（开始）

- 目标：响应用户的合并请求，将 P3-B1 功能适配到当前 `main@ed6d4c7`，核对合并树并推进下一阶段的可独立切片。
- 范围：仅在隔离分支解决主干并发修改带来的冲突，保留主工作树未提交文件；不推送、不删除源分支。
- 已知阻塞：主工作树有与本功能无关的未提交文件；浏览器桥无法连接，真实 PostgreSQL 迁移/RLS 验收配置缺失。P3-B2 属新的达人池/提醒领域，须先以 PRD 和现有领域模型限定首个交付切片。

## 2026-09-23 — TikTok P3-B2 内部达人认领首切片（开始）

- 目标：在 P3-B1 合入主干后，实施 P3-B2 的 E03 首个内部草稿切片：同租户 TikTok 达人入池、单一 BD 认领、有效跟进和回流候选，禁止对外发送及付款。
- 范围：复用已有 `SocialCreator` 与经核验 TikTok 身份，新增独立归属状态/事件、服务、租户接口和聚焦测试；E09 消息和 E10 素材包留待后续切片。
- 已知阻塞：P3-B1 的浏览器角色验收和真实 PostgreSQL/RLS 验收仍未完成；真实 E3、30 条业务对照及外部消息能力均未获证实。新功能仅运行内部草稿，不以这些模拟结果宣称业务退出。

## 2026-09-23 — TikTok P3-B2 内部达人认领首切片（实现与自动化验证）

- 改动文件：`src/backend/app/db/models.py`、`src/backend/migrations/20260923_tiktok_p3b2_creator_pool_v1*.sql`、`src/backend/app/tiktok/creator_pool.py`、`src/backend/app/api/tiktok.py`、`src/backend/app/security/casbin_policy.csv`、`src/backend/app/tiktok/release_gate.py`、`src/frontend-enterprise/src/pages/TikTokBusinessUnitPage.tsx`、`src/frontend-enterprise/src/pages/tiktok/TikTokCreatorPoolPanel.tsx`、`src/frontend-enterprise/src/i18n/en.json`，对应 `src/tests/backend/test_tiktok_creator_pool*.py`、`test_postgres_tiktok_p3b2_creator_pool_migration.py`、`test_tiktok_business_unit.py`、`test_tiktok_live_write_release_gate.py` 与 `src/tests/frontend/TikTokCreatorPoolPanel.test.tsx`；设计、计划、ADR 0004、项目记忆及文档索引同步更新。
- 结果：租户内经核验且最新证据有效的 TikTok 达人可由主管从目录选入内部池；BD 以版本比较认领、用证据编号记录有效跟进；逾期后主管提出并确认回流。状态迁移有追加式事件和 PostgreSQL 强制 RLS/最小授权。没有对外消息、平台写入、分佣或付款。两会话旧版本竞态、租户隔离、无效身份/过期证据、重复入池、非 Owner 跟进和回流竞态均有回归覆盖。
- 验证命令与结果：`python -m pytest -p no:cacheprovider -c pytest.ini src/tests/backend -k tiktok --basetemp=<系统临时目录> -q` 为 174 passed、2 skipped；`npm --prefix src/frontend-enterprise test` 为 69 文件/300 项；`run test:typecheck`、`run i18n:check`（4,390 映射）、`run config:check`、`run build`（2,168 模块）通过；聚焦 Ruff 通过，共享模型沿用现有 `--ignore UP045,FURB157`；`git diff --check` 和已跟踪测试布局守卫通过。新增文件提交后需复跑布局守卫。
- 未完成验收与下一步：浏览器 inventory 再次返回 `nodeRepl.fetch request failed`，无法完成真实角色/路由视觉验收；未获得隔离 PostgreSQL 迁移/RLS 验收连接，静态迁移检查不代表实库通过。分支代码审查和提交仍在进行。合成达人测试不构成 E03/业务批准；待审查修正、实库与浏览器门禁完成后再决定合并，E09 提醒及 E10 素材包另列后续切片。

## 2026-09-23 — TikTok P3-B2 独立审查修正（完成）

- 审查指出自由文本证据引用可能进入追加式事件、事件前后 Owner 缺乏同租户外键，以及已有租户发布版 Casbin 策略会优先于仓库 CSV。修正 `creator_pool.py`：入池来源必须等于该身份的当前 SocialCreatorEvidence ID；跟进引用只接受 `evidence:` 加 32 位小写十六进制编号。同步调整目录选择器和帮助文案，防止自由文本通过工作台进入事件。`models.py` 与正向迁移新增前后 Owner 的 `(tenant_id, user_id)` 外键；静态迁移和负向行为测试先红后绿。已有租户发布版策略不自动覆盖，部署前需审阅并发布包含两条 BD 授权的新策略版本，此项保留为上线门禁。
- 修正文件：`src/backend/app/tiktok/creator_pool.py`、`src/backend/app/db/models.py`、`src/backend/migrations/20260923_tiktok_p3b2_creator_pool_v1.sql`、`src/frontend-enterprise/src/pages/tiktok/TikTokCreatorPoolPanel.tsx`、`src/frontend-enterprise/src/pages/TikTokBusinessUnitPage.tsx`、`src/frontend-enterprise/src/i18n/en.json`、`src/tests/backend/test_tiktok_creator_pool.py`、`src/tests/backend/test_postgres_tiktok_p3b2_creator_pool_migration.py`、`src/tests/frontend/TikTokCreatorPoolPanel.test.tsx`，并更新设计、ADR 0004 与交接。
- 复验：`python -m pytest -p no:cacheprovider -c pytest.ini src/tests/backend -k tiktok --basetemp=<系统临时目录> -q` 为 174 passed、2 skipped；前端完整 `npm --prefix src/frontend-enterprise test` 为 69 文件/300 项，类型检查、i18n（4,392 映射）、生产构建（2,168 模块）通过；聚焦 Ruff 和 `git diff --check` 通过。浏览器、真实 PostgreSQL 与已发布租户策略更新仍未完成，不能把自动化绿色结果当作上线批准。

## 2026-09-23 — TikTok P3-B2 独立分支提交（完成）

- 将上述 24 个代码、迁移、测试和文档路径提交于 `codex/tiktok-p3b2-creator-pool@91490b5`；提交前 `git diff --cached --check` 通过，`python src/tests/check_test_layout.py` 检查 1,245 个已跟踪路径通过。无推送、无源分支删除、无对主工作树既有九个未提交路径的修改。
- 下一步仍是隔离 PostgreSQL 迁移/RLS、已发布租户策略版本和真实浏览器角色验收；这些门禁未通过前不将本切片合入主干。

## 2026-09-23 — TikTok P3-B2 验收门禁与集成（开始）

- 目标：按用户“实施下一步”的指示，验证 P3-B2 首切片的 PostgreSQL 正向迁移与租户 RLS、已发布 Casbin 策略下的 BD 授权和真实页面角色行为；门禁通过后按仓库规则线性合并。
- 范围：仅使用隔离验收数据库或其他可回滚的测试环境，不改动已恢复生产/开发数据；保留主工作树九个未提交路径，禁止对外消息和付款，未授权不发布租户策略或推送分支。
- 已知阻塞：此前浏览器桥报 `nodeRepl.fetch request failed`；隔离 PostgreSQL 连接未配置；既有租户发布版策略可能屏蔽 CSV 新权限。先核实当前可用环境和仓库验收脚本，不预设这些条件已经解决。

## 2026-09-23 — TikTok P3-B2 隔离验收与角色模拟（完成）

- 改动文件：新增 `src/tests/backend/test_postgres_tiktok_p3b2_creator_pool_live.py`，更新 `src/tests/backend/test_tiktok_creator_pool_api.py`、`docs/SESSION_HANDOFF.md` 及本日志。新 PostgreSQL 测试仅在显式指定一次性本地集群时运行，并校验数据目录标记及端口，避免触碰恢复的 55433 数据库。
- 验证命令与结果：在独立 PostgreSQL 16 集群中运行该 opt-in 测试，正向迁移、租户 A/B/无上下文强制 RLS、跨租户写拒绝、事件外键与追加式触发器、逆向迁移均通过（1 passed）；`pytest -k tiktok` 为 175 passed、3 skipped；新增 Python 测试文件 Ruff 与 `git diff --check` 通过。使用临时 Vite 和 Playwright Edge、模拟 API/三类会话检查 `/enterprise/tiktok`，BD 认领请求、主管入池请求及内容专员入口隐藏均通过；截图仅存系统临时目录。
- 剩余风险：模拟 API/角色不是实际 Casdoor 或已发布租户策略验收；一次性最小前置 schema 不能代替完整目标库迁移门禁。现有租户策略仍需人工审阅继任版本并发布，P3-B1 的实际浏览器/数据库及业务门禁仍未完成。主干有九个无关未提交路径，暂不合并。本步未改变真实租户策略、恢复的数据库、外部平台或付款能力。
- 下一步：提交本分支测试与记录并复跑已跟踪测试布局守卫；关闭临时 Vite/PostgreSQL；在具备真实账号、策略审阅和安全集成条件后完成剩余验收，再按仓库规则线性合并。
- 清理：临时 Vite 会话已停止；隔离 PostgreSQL 先正常停止，再在核对其绝对路径仍位于系统临时目录后删除。恢复的本地 PostgreSQL 服务没有被停止或修改。

## 2026-09-23 — TikTok P3-B2 主管转交与手动释放（开始）

- 目标：在主干已合入内部达人池首切片后，补齐 E03 人员变动时的主管转交和主动释放，避免靠自由文本或直接改库调整 Owner。
- 范围：沿用同租户达人池和版本比较，新增有限原因码、在职 BD 校验、追加式前后 Owner 事件及主管页面操作；不涉及分佣、对外消息或付款。
- 已知阻塞：真实账号、已发布租户策略和目标数据库迁移仍需单独验收；本切片先在隔离分支完成自动化与模拟页面验收。

## 2026-09-23 — TikTok P3-B2 主管转交与手动释放（实现与验证）

- 改动文件：`src/backend/app/tiktok/creator_pool.py`、`src/backend/app/api/tiktok.py`、`src/backend/app/db/models.py`、`src/backend/app/tiktok/release_gate.py`、两份 `20260923_tiktok_p3b2_owner_transfer_v1` 迁移、`TikTokCreatorPoolPanel.tsx` 与英文映射，相关 `src/tests/backend/test_tiktok*`、`test_postgres_tiktok_p3b2_creator_pool*` 和 `src/tests/frontend/TikTokCreatorPoolPanel.test.tsx`；ADR 0004 与交接同步。
- 行为：主管可将已认领或待回流达人交给同租户在职 BD，按当前 SLA 重新计算截止时间；也可手动释放到公海。版本比较阻止旧会话覆盖，固定原因码和追加式事件记录前后 Owner、操作者及时间。非主管、跨租户、非 BD、停用或同一 Owner 目标均被拒绝。新增路由列入冻结外部写清单，只改变内部数据库状态。
- 红绿验证：服务测试先因缺少转交实现失败，迁移测试先因缺少新迁移失败，前端测试先因缺少主管控件失败，随后聚焦测试通过。完整 TikTok 后端为 180 passed、3 skipped；隔离 PostgreSQL 16 的迁移、事件插入与逆向迁移测试 1 passed；前端 69 文件/301 项（限制 4 workers）、测试类型检查、i18n 4,401、配置检查、2,168 模块构建、聚焦 Ruff 和 diff 检查通过。并行全套前端首次出现 13 个分散的 5 秒超时，单独重跑全部通过。
- 浏览器：临时 Vite + 模拟 API 的 Edge 检查通过 BD 认领、主管入池/转交/释放请求及内容专员隐藏入口；截图仅为合成数据。Vite 和隔离数据库均已停止，数据库临时目录已删除。
- 剩余风险与下一步：真实 Casdoor 账号、已发布租户策略与目标验收库尚未验证，本步不构成 P3-B2 退出或生产批准。提交独立分支后复跑测试布局守卫，再在保护主工作树原有改动的前提下按仓库规则线性合并；之后继续 E03 履约/维护负责人和分佣草案冲突校验。
- 独立审查：相对 `main@7ebcad4` 未发现 Critical 或 Important 代码缺陷；指出隔离 PostgreSQL 测试只探测事件约束，没有通过真实 PostgreSQL runtime role 执行完整服务 CAS 更新与持久事件联动。该集成缺口与真实租户门禁一起保留为后续验收，不把 SQLite 服务测试等同于完整 PostgreSQL 服务验收。
- 提交后布局验收：实现提交 `cb78cbb` 后，`python src/tests/check_test_layout.py` 对 1,248 个 tracked 路径检查通过；功能分支工作区干净。无推送或源分支删除。

## 2026-09-23 — 当前员工侧栏可见性修复（开始）

- 目标：修复 Joukir 管理侧栏菜单增多后，当前员工卡片被非滚动导航挤出可视区域的问题。
- 范围：仅调整 `AppSidebar` 布局和对应前端回归测试；保留现有导航、角色权限与员工切换行为，不修改后端或真实数据。
- 已知阻塞：主工作树有两份文档处于未解决的合并冲突状态，暂不可安全合并；隔离 worktree 尚未安装前端依赖，也尚未完成浏览器实测。

## 2026-09-23 — 当前员工侧栏可见性修复（已验证、已审查，待集成）

- 修改文件：`src/frontend-enterprise/src/components/AppSidebar.tsx` 将管理菜单与员工快捷区分为独立滚动区域、为员工区保留可见高度并固定底部入口，覆盖展开与收起布局；`src/tests/frontend/components/AppSidebar.test.tsx` 增加完整管理员菜单回归；`src/frontend-enterprise/src/i18n/en.json` 补充两个无障碍区域名称的英文映射。本日志和 `docs/SESSION_HANDOFF.md` 记录隔离分支状态。产品代码提交于 `codex/sidebar-current-employee@4a33000`，不含真实数据修改。
- 验证：原侧栏测试 7 项通过；新测试修复前因缺少独立导航区而失败、修复后 8 项通过。最终 `npm --prefix src/frontend-enterprise test -- --maxWorkers=4` 为 69 文件/301 项通过，`test:typecheck`、`i18n:check`（4,394 映射）、`build`（2,168 模块）、`python src/tests/check_test_layout.py`（1,246 个跟踪路径）和 `git diff --check` 均通过。首轮不限制并行数的完整测试有 3 个无关用例超过 5 秒，限制为四个 worker 后全绿。
- 页面验收：临时 Vite + 全新无头 Edge 配置仅打开本地合成预览，不使用现有认证窗口或真实 API。按应用 220px 侧栏、953px 内容视口测得展开态导航 410px/内容 809px、员工入口顶/底 555/597px；收起态导航 395px/内容 704px、员工入口顶/底 590/663px；两态入口及底部按钮均在视口内。已目视检查展开态截图；临时预览源码已移除，Vite 已停止。尚未验收用户当前已登录页面。
- 独立审查：对 `7ebcad4..4a33000` 未发现 Critical/Important 代码问题；仅有 Minor 测试缺口——jsdom 与合成预览未证明员工卡片底部链接滚动后可以点击。后续在真实路由/角色浏览器验收中覆盖。
- 剩余风险与下一步：主工作树前进至 `main@31f797f`；两份文档冲突随后被其他工作解决，但仍有九个未提交路径，其中两份文档与本分支记录重叠，主干 `en.json` 也在分叉后变动。为保留这些现有改动，暂不合并或部署到当前页面；待重叠的未提交文档安全落定后，更新隔离分支、复验集成结果，再按仓库规则线性合并。未推送或删除分支。

## 2026-09-23 — 知识图谱 PostgreSQL 分桶读取修复（开始）

- 目标：修复知识库页面读取文档分桶时 PostgreSQL 报 `type "blob" does not exist` 并返回 500 的问题。
- 范围：仅调整分桶及切片读取的数据库方言兼容性，保留 SQLite 对旧编码数据的读取路径；补回归测试，不改变权限、租户过滤或数据结构。
- 已知阻塞：主工作树有九个无关未提交路径；隔离工作树的知识库测试文件 41 项显示通过但整进程退出卡住，单项基线测试可正常通过。合并时必须完整保留主工作树改动。

## 2026-09-23 — 知识图谱 PostgreSQL 分桶读取修复（实现与验证）

- 改动文件：`src/backend/app/api/knowledge.py`、`src/tests/backend/test_knowledge_bucket_dialects.py`、本日志及 `docs/SESSION_HANDOFF.md`。分桶和切片查询仅在 SQLite 使用 `BLOB` 转换，PostgreSQL 原值读取；租户过滤、权限和数据结构未改变。
- 红绿验证：两条 PostgreSQL 投影回归测试先因 `AS BLOB` 失败，SQLite 旧路径测试通过；修复后新测试 3 项通过，合并现有知识库测试共 44 项通过。用当前本地 PostgreSQL 只读执行两条查询，并解码触发故障的同一文档 1 个分桶、6 个切片，未写入或输出内容。
- 其他检查：新测试文件 Ruff 通过；现有 `knowledge.py` 有 29 个未由本次改动引入的 Ruff 问题，改动行无新问题。全量后端首个失败为广告审批测试，未修改的 `main` 单独复跑同样失败（预期 `queued`、实际 `manual_resolution_required`）；因此不能声称全量通过。
- 剩余风险与下一步：独立审查、提交及已跟踪测试布局守卫待完成。主干九个无关未提交路径必须保留；已请用户决定是否将确认的全量基线失败作为合并例外。若不接受则保留分支。当前运行服务仍指向未合并主干，页面需合并后刷新验收。

## 2026-09-23 — 知识图谱 PostgreSQL 修复的基线失败例外

- 用户明确允许将未修改 `main` 同样出现的广告审批测试失败列为本次合并的基线例外，并要求完成后合并；此例外不代表全量后端测试通过，也不扩大本次修改到广告模块。
- 下一步仍需独立审查、提交、跟踪文件布局检查及安全线性合并，然后在合并树上复验知识库路径。

## 2026-09-23 — 知识图谱 PostgreSQL 修复审查与集成准备

- 目标与范围：确认本修复没有引入跨租户读取、类型转换或回归测试缺口，随后仅将已验证的短分支安全合并回 `main`。
- 已知阻塞：主工作树仍有九个无关未提交路径，其中两份文档与本分支修改重叠；全量后端广告测试失败已获用户明确允许作为本次基线例外。
- 审查结果：对 `9156ac7..1519b8c` 的独立只读审查未发现 Critical、Important、Minor 问题，确认两条读取路径保留租户参数和 RLS 上下文；建议合并后在已登录页面复核。提交后测试布局守卫对 1,249 个已跟踪路径通过，隔离分支工作区干净。
- 下一步：保存主工作树未提交状态及校验摘要，执行线性合并并恢复九个原有路径；复跑合并树的知识库测试，保留安全备份直到确认无遗漏。
## 2026-09-23 — Digital employee description AI draft (start)

- Objective: add an AI generation action for the new digital employee role description.
- Scope: tenant-authorized draft generation, create-dialog interaction, and focused regression coverage.
- Known blockers: the isolated worktree has no local frontend dependencies or backend virtual environment; the main checkout contains unrelated uncommitted work and will remain untouched.

### Result

- Changed files: `src/backend/app/agents/schema.py`, `src/backend/app/api/agents.py`, `src/frontend-enterprise/src/App.tsx`, `src/frontend-enterprise/src/i18n/en.json`, `src/tests/backend/test_agent_description_generation.py`, and `src/tests/frontend/App.test.tsx`.
- The create dialog now requests a role-based AI draft from the tenant default model. Existing description text stays intact until the user chooses to replace it. Closing the dialog or changing the position invalidates an in-flight result.
- Automatic approval review rejected forwarding a copied employee description to the configured model because the destination and sensitive payload were not authorized. The accepted implementation sends only the position entered for this request; the request schema rejects copied employee content.
- Validation: focused backend generation and agent-permission tests 23 passed; frontend 69 files and 304 tests passed; frontend test typecheck, i18n check (4,412 translations), config check, production build, and 1,250-path test-layout guard passed. The new backend test file and focused backend lint selectors passed Ruff; whole changed backend-file Ruff still reports 78 pre-existing findings, with none on the new route or schemas. `git diff --check` passed. The enterprise router exposes the new POST path.
- Remaining risks: no real model call or authenticated browser acceptance was possible. The browser connector returned `nodeRepl.fetch request failed`. The full backend run stopped after the documented advertising baseline failure at 14 passed and 1 failed: `test_ad_action_requires_approval_then_creates_7_14_30_day_reviews` expected `queued` but received `manual_resolution_required`.
- Next recommended step: review and commit the isolated branch, then perform administrator browser acceptance and a real default-model generation in the intended environment. Do not merge while main's unrelated changes and the required backend gate remain unresolved.


## 2026-09-23 — 开放广场三类资源创建入口设计（开始）

- 目标：让知识库、SOP、工具广场与 Skill 广场一样提供创建开放内容入口。
- 范围：入口对所有登录用户可见，继续复用现有管理员发布权限和各资源新建流程；普通用户点击时明确提示权限限制，不改后端授权、数据库或资源结构。
- 已知阻塞：当前主工作树有九个既有未提交路径；本工作在独立 worktree 中进行。架构型设计需先形成并经用户审阅书面规范，然后才进入实现计划与代码。

## 2026-09-23 — 开放广场三类资源创建入口设计（书面规范待审）

- 修改文件：新增 `docs/superpowers/specs/2026-09-23-open-plaza-create-entries-design.md`，在 `docs/README.md` 建立索引，并更新本日志及 `docs/SESSION_HANDOFF.md`。产品代码、后端权限和真实数据均未改动。
- 验证：设计核对了四种资源各自现有的新建路由与服务端广场管理员检查；规范完成占位符、内部一致性、范围和歧义自查；`git diff --check` 未发现补丁空白错误，仅提示文档工作区行尾转换。
- 剩余风险与下一步：需要用户审阅并批准书面规范；之后才能编写实现计划、安装隔离工作区依赖、建立基线、按测试驱动方式实现并做角色页面验收。主工作树九个已有未提交路径须完整保留，集成前再次核对。

## 2026-09-23 — 开放广场创建入口实现计划（开始）

- 目标：把已获用户确认的书面规范细化为逐步可测试的实现、验证和集成计划。
- 范围：仅规划前端广场按钮、路由、权限反馈、翻译和回归测试；此阶段不修改产品代码、安装依赖或变更服务端权限。
- 已知阻塞：计划仍需用户审阅并选择执行方式；主工作树九个原有未提交路径继续保持不动。

## 2026-09-23 — 开放广场创建入口实现计划（待审）

- 修改文件：新增 `docs/superpowers/plans/2026-09-23-open-plaza-create-entries.md`、更新 `docs/README.md` 索引，并追加本日志和 `docs/SESSION_HANDOFF.md`。未改产品代码或后端权限。
- 验证：对照已批准规范逐项自查，计划覆盖四类入口、管理员与普通用户、缺失总员工、SOP ID 编码、空列表和员工广场无按钮；占位符扫描未发现待定项。计划包含红绿测试、类型/翻译/构建检查、角色页面验收及安全合并步骤。
- 剩余风险与下一步：等用户确认计划及执行方式后，才运行工作树依赖和测试并实现。主工作树九个原有未提交路径仍需在集成时保留。

## 2026-09-23 — 开放广场创建入口实施 Task 1（开始）

- 目标：建立隔离工作树前端基线，并以红绿测试为可复用广场详情页加入资源专属创建按钮文字。
- 范围：`PlatformKindDetailView` 与对应前端测试；不改权限、后端、数据库或主工作树。
- 已知阻塞：隔离工作树尚无前端依赖与基线结果；主工作树保留九个既有未提交路径。若基线失败须先确认原因。

## 2026-09-23 — 开放广场创建入口实施 Task 1（组件完成）

- 修改文件：`src/frontend-enterprise/src/components/openPlatform/PlatformKindDetailView.tsx` 新增可选创建按钮文字，`src/tests/frontend/components/openPlatform/PlatformKindDetailView.test.tsx` 覆盖四类资源空列表按钮及员工广场无按钮。
- 验证：隔离依赖 `npm ci` 成功，未修改基线前端 69 文件/302 项通过。首次基线运行仅因沙箱拒绝 Vite 缓存目录创建而未收集测试；经批准的文件系统执行后同一命令通过。新测试先出现 3 个预期失败（固定 Skill 文案），最小实现后 5/5 通过；测试类型检查通过；完整前端 70 文件/307 项通过，`git diff --check` 无补丁空白错误。
- 剩余风险与下一步：组件尚待提交；接下来连接四个页面入口并验证跳转、管理员权限、缺失总员工及作用域事件。主工作树未改动。

## 2026-09-23 — 开放广场创建入口实施 Task 2（开始）

- 目标：在四个资源广场接入创建动作，同时使普通用户按钮可见但点击时明确告知开放内容仅管理员可创建。
- 范围：`OpenPlatformPage`、英文文案映射及其页面回归测试；继续复用现有新建路由和总员工作用域，不改服务端权限。
- 已知阻塞：浏览器角色验收尚未进行，主工作树九个原有未提交路径须保持；页面测试需模拟只读目录接口，不产生真实资源。

## 2026-09-23 — 开放广场创建入口实施 Task 2（页面完成）

- 修改文件：`src/frontend-enterprise/src/pages/OpenPlatformPage.tsx` 为知识库、Skill、SOP、工具配置专属按钮与既有新建路由，管理员先切到总员工作用域，普通用户点击只显示权限提示；`src/frontend-enterprise/src/i18n/en.json` 补四条英文映射；`src/tests/frontend/pages/OpenPlatformPage.test.tsx` 验证四路跳转、SOP ID 编码、作用域事件、普通用户不变更作用域、缺失总员工及员工广场无入口。
- 红绿验证：页面测试在修改前 10 项中 8 项按预期失败（新入口缺失或 Skill 对普通用户直接跳转）；最小实现后页面与组件测试合计 15/15 通过。`test:typecheck`、`i18n:check`（4,407 项英文映射）通过，完整前端 71 文件/317 项通过，`git diff --check` 无补丁空白错误。
- 剩余风险与下一步：页面改动尚待提交；随后运行构建、配置及测试布局检查，并在可用的浏览器中验收管理员和普通用户界面。主工作树未改动。

## 2026-09-23 — 开放广场创建入口实施 Task 3（开始）

- 目标：在分支提交后完成完整前端/构建/布局门禁、角色与页面验收、变更审查，并在保护主工作树原有改动的前提下线性合并。
- 范围：只验证与集成本次前端入口和对应文档；不创建真实开放资源、不扩大权限、不推送或删除源分支。
- 已知阻塞：浏览器桥接及真实管理员/普通用户会话可用性待确认；主工作树九个原有未提交路径与文档索引、日志、交接文件可能重叠，合并前须建立可验证保护措施。

## 2026-09-23 — 开放广场创建入口实施 Task 3（验证与审查准备）

- 修改文件：`docs/DEVELOPMENT_LOG.md` 和 `docs/SESSION_HANDOFF.md` 记录本分支的验证、浏览器验收缺口及集成前状态。产品改动已提交于 `35caba4`、`6d06a62`。
- 验证：完整前端测试最新运行 71 文件/317 项通过；`test:typecheck`、`i18n:check`（4,407 映射）、`config:check`、2,168 模块生产构建、1,253 个跟踪路径布局检查及 `git diff --check` 均通过。构建仍有既有大块提示。
- 浏览器验收：浏览器连接两次返回 `nodeRepl.fetch request failed`；Windows Computer Use 因无法可靠确认当前浏览器 URL 中止上一轮操作。没有执行真实角色页面验收或创建资源。临时分支预览 5175 已停止并确认无监听。
- 剩余风险与下一步：用户在获知该缺口后再次明确要求合并；此记录保留页面验收未完成事实，不将自动化测试等同真实会话。仍需独立审查、保护主工作树九个已有未提交路径并核对线性合并结果；不推送或删除源分支。

## 2026-09-23 — 开放广场创建入口审查与主干集成（开始）

- 目标：对照已批准规范与仓库约定完成独立审查，再按用户指示把已验证的短分支线性合并至本地 `main`。
- 范围：仅本分支的前端入口、测试和设计/实施记录；合并前后核验主工作树九个既有未提交路径，不推送远端或删除源分支。
- 已知阻塞：主工作树的 `docs/README.md`、`docs/DEVELOPMENT_LOG.md`、`docs/SESSION_HANDOFF.md` 与分支重叠，须先建立可恢复的保全快照并逐项确认内容；真实管理员/普通用户浏览器验收仍因连接失败而未完成。

## 2026-09-23 — 开放广场创建入口双轴审查完成

- 修改文件：本审查步骤仅追加本日志并更新 `docs/SESSION_HANDOFF.md`；产品代码、权限和测试文件未再更改。
- 验证：两项针对 `6501350..3c28bef` 的独立只读审查分别核对仓库规范和已批准规范，均未发现 Critical、Important 或 Minor 问题；确认四类路由、管理员拦截先于作用域变更、SOP 员工参数编码、缺少总员工反馈、翻译与回归覆盖符合计划。
- 剩余风险与下一步：真实登录角色页面仍未验收。先记录主工作树九个未提交路径校验摘要并保全，完成无合并提交的线性集成，恢复并验证全部原有改动，最后在合并树上复跑检查。

## 2026-09-23 — 开放广场创建入口集成因并行主干冲突暂停

- 修改文件：仅更新本分支的开发日志和会话交接；没有对主工作树执行 stash、合并、冲突解决或任何产品文件修改。
- 验证：合并前发现并行操作已将 `main` 从 `6501350` 推进到 `1b57726`（另一功能分支），且 `docs/DEVELOPMENT_LOG.md`、`docs/SESSION_HANDOFF.md` 处于 `UU` 未解决状态；`stash@{0}` 属于该并行操作。原有九个未提交路径仍列于状态中。本分支保持独立，审查结果无代码问题。
- 剩余风险与下一步：按仓库规则暂停集成，不接管或覆盖他人的冲突。待主工作树冲突由其操作方解决、九个原有路径得到保全后，重新核对目标 HEAD，必要时将本分支重放到新 `main`，复跑门禁并线性合并。真实角色浏览器验收仍待完成；不推送或删除源分支。

## 2026-09-23 — 开放广场创建入口更新基点并恢复集成

- 目标与范围：在并行操作解除主工作树冲突后，将本分支线性重放到 `main@1b57726`，保留其数字员工描述草稿功能及本分支实现和记录。
- 验证：主工作树已无未解决条目或暂存改动；九个原有路径仍在，非重叠文件 SHA-256 与并行操作前一致，保全快照的三份重叠文档每条非空内容均在当前工作文件中。重放已完成；只在开发日志和交接文档发生冲突，逐处保留双方内容，`git diff --check` 未见补丁空白错误。
- 剩余风险与下一步：重放后的完整前端门禁、布局检查及合并树复验尚待执行；真实管理员/普通用户浏览器验收依旧未完成。主工作树九个未提交路径需在最终快进合并前重新保全。

## 2026-09-23 — 开放广场创建入口重放后验证完成

- 修改文件：本步骤只更新 `docs/DEVELOPMENT_LOG.md` 和 `docs/SESSION_HANDOFF.md` 的验证记录；重放未修改本分支的产品实现。
- 验证：先前普通沙箱运行因 Vite 临时缓存写入 `EPERM` 未进入测试收集；按批准的隔离工作树执行权限重跑后，完整前端 71 文件/319 项通过。`test:typecheck`、`i18n:check`（4,416 条映射）、`config:check`、2,168 模块生产构建、1,254 路径测试布局守卫和 `git diff --check` 通过。构建保留既有大块提示。
- 剩余风险与下一步：需对新基点的最终差异和文档冲突解决再审查；然后保全主工作树九个已有未提交路径、快进合并并验证恢复情况。真实登录角色浏览器验收仍未完成，不推送或删除源分支。
## 2026-09-24 — TikTok E03 分责与分佣草案校验（开始）

- 目标：在已合入主干的 P3-B2 达人池基础上，分别记录履约与维护负责人，并提供不触发付款的分佣草案校验。
- 范围：隔离分支 `codex/tiktok-p3b2-commission`；仅修改 TikTok 领域、API、必要的数据库迁移、前端工作台、针对性测试与对应文档。主干现有未提交改动和 5173 本地服务保持原状。
- 已知阻塞：PRD D6 尚未确定业务比例、冲突优先级和财务审批人；因此不内置默认比例，不宣称财务批准或生产就绪。历史订单事实的来源与授权仍需单独验收。

## 2026-09-24 — TikTok E03 分责与分佣草案校验（实现与验证）

- 修改文件：`src/backend/app/db/models.py`、`src/backend/app/tiktok/creator_pool.py`、`commission_preflight.py`、`release_gate.py`、`src/backend/app/api/tiktok.py`、`20260924_tiktok_p3b2_responsibilities_v1` 正反迁移、达人池和预检前端、英语映射、相应后端与前端测试；新增 E03 设计、实施计划和 ADR 0005，并更新项目记忆及文档索引。
- 行为：主管可分别指定履约与维护负责人；修订号 CAS 和不可变事件保留前后责任。释放至公海清空执行责任。分佣输入预检查比例、同一请求的订单重复、输入期限和责任完整性；未获可信批准的规则始终返回 `rule_unapproved`，无提交、冻结、支付或外部发送接口。
- 验证：先红后绿的服务、API、前端测试；TikTok 后端矩阵 187 passed、3 skipped；前端 71 文件/324 项通过；`test:typecheck`、`i18n:check`（4,448 条）、`config:check`、生产构建（2,169 模块）通过；隔离 PostgreSQL 16 的迁移、强制 RLS、跨租户外键和空新事件场景逆向迁移 1 passed；Ruff 对本次模块通过，共享模型按既有 `UP045,FURB157` 豁免通过；测试布局和差异空白检查通过。Edge 模拟 API 的主管与 BD 页面检查分别显示/隐藏分责和预检控件，未使用真实 Casdoor 会话。
- 剩余风险与下一步：PRD D6 的批准规则、审批人、订单授权事实和跨草案订单排他尚未具备，不能提交财务审核或冻结快照；真实数据库部署门禁及已登录角色仍需验收。下一步先确定 D6，再实现批准规则登记、持久草案、跨草案冲突和财务冻结快照。独立 PostgreSQL 测试实例已停止；自动命令策略拒绝递归删除其系统临时目录，目录不含真实租户数据。

## 2026-09-24 — TikTok E03 复审修正（开始）

- 目标：处理独立复审指出的负责人停用竞态、管理员权限契约歧义和预检旧响应覆盖新输入问题。
- 范围：仅修改对应领域逻辑、页面状态、回归测试及设计文字；保留尚未合入的分支提交和主工作树九处并行修改。
- 已知阻塞：生产目标数据库门禁与真实身份浏览器验收仍未通过，本轮只能证明隔离环境行为。

## 2026-09-24 — TikTok E03 复审修正（完成）

- 修改文件：`creator_pool.py` 对履约与维护目标用户按稳定 ID 顺序加 `FOR UPDATE` 行锁，避免在校验与写入之间被并发停用；测试编译 PostgreSQL 查询验证锁语义。`TikTokCommissionPreflight.tsx` 用输入修订号丢弃在途旧响应，新增先红后绿的延迟响应测试。API 测试与设计/ADR 明确租户管理员和运营主管均可管理，普通 BD 不可；页面与设计说明当前 UI 每次只检查一个订单范围，跨持久草案冲突仍未校验。
- 验证：`pytest -k tiktok` 为 188 passed、3 skipped；完整前端 71 文件/325 项通过；测试类型检查、i18n（4,448 条）、配置检查、生产构建（2,169 模块）、本次 Python Ruff（共享模型仅既有规则豁免）、1,262 路径布局守卫及差异检查均通过。隔离 PostgreSQL 迁移/RLS 验证此前为 1 passed，迁移文件未改。
- 剩余风险与下一步：行锁保证指派事务内目标状态核验，不阻止用户未来正常停用后产生待转交责任；停用后的任务再路由需独立规则。生产数据库门禁、已登录角色和 D6 财务规则仍待验收。复审修正后应线性合入本地 `main`，保留并行未提交路径、源分支及安全快照。
