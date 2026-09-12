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
