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
