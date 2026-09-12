# Joukir 主仓库迁移验证（2026-09-11）

本记录验证从交接仓库迁移到 `E:\develop\数字员工\joukir` 后的源码完整性、测试布局、构建、数据库安全门禁和本机运行切换。命令输出经过脱敏；连接串、Secret、OIDC state/nonce/code challenge 和完整授权 URL 均未写入文档或 Git。

## 结论

新目录的源码迁移和 5173 Web 切换已完成。交接快照的 1,154 个路径全部映射到新目录，Git 历史及备份保留；前端、集成、PostgreSQL 门禁、在线健康和无凭据 OIDC/PKCE 检查通过。后端全量套件并非全绿，但新旧仓库在 2,241 项历史基线上得到完全相同的 21 个失败和 9 个跳过，未见迁移独有回归。此证据提交时本地 `main` 快进仍待最终复审，真正的 GitHub remote 和人工账号/业务验收仍需维护者提供条件。

## Git 历史和源码完整性

- 交接基线使用带注释标签 `handover-20260909`，标签剥离后指向 `e0cb8df042b3a5f856c60b45cf7e9c2bafbc23b5`；标签可达的 44 个提交与交接仓库一致。
- 新仓库没有 object alternates，不依赖旧仓库的 `.git/objects`；`git fsck --full` 退出 0。
- 未配置 Git remote。GitHub Flow、PR 模板、CI 工作流、Dependabot 和 CodeQL 已就位；真实 GitHub 地址由维护者提供后再绑定 `origin`。
- `docs/migration/source-index-before-layout.tsv` 记录平铺前的路径和 blob。该快照包含交接标签的 1,152 个 tracked 路径，以及为本次迁移新增并先行提交的设计、计划文档各一份，共 1,154 项。最终映射 `docs/migration/final-source-map.tsv` 固定到功能源码提交 `fc1dd456445a0eccbe053fa0d19987a4b37102d9`：1,154/1,154 路径存在且目标唯一，大小写折叠冲突 0、缺失 0、无法解释的内容或 mode 变化均为 0；1,056 个 blob 完全相同，98 个内容变化对应已复审的目录、测试、CI、文档及开发工作流提交。3 个 `dev_*.sh` 的 `100644 → 100755` 是已复审的 Unix 执行位修正。
- 映射脚本固定了快照、最终功能提交和完整中间提交链，不随之后的证据提交或 `main` 指针移动。它同时报告 19 个到 `fc1dd45` 为止的有意新增文件；本记录、根 Ruff 配置及 `scripts/migration/` 核验工具是在该功能源码快照之后新增的迁移证据，不属于那 1,154 个交接索引路径。预审修复 `fc1dd45` 对齐了前端测试文件名约束、后端启动说明、开发启动输出和 Unix 脚本权限，没有删除业务模块。根 `ruff.toml` 使从仓库根运行的既定 Ruff 命令正确识别 `backend/app` 为 first-party。
- Task 8 的计划示例只暂存 `docs/`。最终提交会显式同时暂存 `ruff.toml`；否则文档中的根级 Ruff 命令在全新 clone 中不可复现。该配置补充是已记录的任务范围调整。
- 旧绝对路径只保留在带日期的交接/开发记录、迁移设计与映射证据、回滚说明、`scripts/migration/` 的一次性旧目录切换默认值，以及原样保存的 `deploy/staffdeck-platform` 来源清单和一次性迁移脚本中；后端、前端、根级日常生命周期脚本、打包、CI、测试和当前运行命令没有旧源码路径。
- 与交接标签对比的脱敏扫描结果：private-key header 0→0、credential URL 候选 4→4、已知服务 token 0→0、敏感赋值候选 296→296，新增候选均为 0；跟踪的环境文件、key、数据库、日志、PID、虚拟环境、`node_modules`、`dist` 等运行产物违规为 0。候选计数仅用于证明迁移没有新引入敏感文本，不把既有候选当作有效凭据。

主要命令：

```powershell
git fsck --full
backend\.venv\Scripts\python.exe tests\check_test_layout.py
backend\.venv\Scripts\python.exe -m compileall -q backend\app
backend\.venv\Scripts\python.exe -m ruff check backend\app\api\tiktok.py backend\app\tiktok\connector.py backend\app\tiktok\official.py backend\app\tiktok\release_evidence.py backend\app\tiktok\release_gate.py backend\app\tiktok\schema.py backend\app\tiktok\service.py backend\app\tiktok\shadow.py tests\backend\test_tiktok_connector_authorization.py tests\backend\test_tiktok_live_write_release_gate.py tests\backend\test_tiktok_release_evidence.py tests\backend\test_tiktok_shadow.py
```

上述命令均退出 0。测试布局守卫检查了 1,184 个最终跟踪路径；可执行测试套件集中在 `tests/backend`、`tests/frontend`、`tests/integration` 和 `tests/packaging`，根 `tests/` 另有布局守卫与配置说明。

来源映射、工作树安全扫描和活动代码旧路径检查使用以下命令；`scripts/migration/` 中的通用核验工具已纳入 Git，输出只含路径、摘要、计数和布尔结果，详细候选位置写在被忽略的 `.dev/`：

```powershell
backend\.venv\Scripts\python.exe scripts\migration\verify_source_map.py
backend\.venv\Scripts\python.exe scripts\migration\security_scan.py --worktree
$active = @('backend', 'frontend-enterprise', 'scripts', 'packaging', '.github', 'tests', 'README.md', 'README.zh.md', 'AGENTS.md', 'CONTRIBUTING.md', ':(exclude)scripts/migration/**')
git grep -n -I -E 'joukir-enterprise[\\/]+source|D:[\\/]saas[\\/]+(third_party|worktrees)[\\/]' -- $active
```

前两条命令退出 0；第三条无匹配并以退出码 1 表示日常活动范围不存在旧源码路径。`scripts/migration/` 明确排除，因为其一次性切换工具保留旧目录作为默认校验对象。对全部 tracked 文件的同模式扫描另行核对并只命中上面列出的历史、回滚、迁移工具和保留部署快照范围；这些内容不作为当前启动命令来源。

## 后端验证

完整命令使用不存在的 dotenv、独立 SQLite URL、独立数据目录、独立 `--basetemp`、禁用 pytest cache，并固定 UTF-8 子进程 I/O 和 localhost 代理旁路。以下是新仓库实际调用和旧仓库调用的已跟踪等价入口：

```powershell
$artifact = Join-Path $PWD '.dev\task8-new-20260911-verify'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:NO_PROXY = 'localhost,127.0.0.1'
$env:no_proxy = 'localhost,127.0.0.1'
$env:ULTRARAG_DOTENV = Join-Path $artifact 'nonexistent-test.env'
$env:DATABASE_URL = 'sqlite:///' + (Join-Path $artifact 'pytest-new.db').Replace('\', '/')
$env:ULTRARAG_DATA_DIR = Join-Path $artifact 'data'
backend\.venv\Scripts\python.exe -m pytest -c pytest.ini tests\backend --basetemp (Join-Path $artifact 'temp') --junitxml (Join-Path $artifact 'pytest-new.xml') -p no:cacheprovider -q --tb=short --durations=20 *> (Join-Path $artifact 'pytest-new.log')

# 在新仓库套件结束后，以旧 pyproject 和旧虚拟环境顺序执行：
& scripts\migration\run_legacy_backend_suite.ps1 -OldRepository 'E:\develop\数字员工\joukir-enterprise' -ArtifactRoot 'E:\develop\数字员工\joukir\.dev\task8-old-20260911-verify-pwsh'
```

- 新仓库：收集 2,241 项；2,211 passed、21 failed、9 skipped、0 errors、120 warnings；pytest 墙钟耗时 11,732.10 秒（3:15:32），JUnit case-time 合计 11,723.986 秒；退出码 1。
- 交接仓库：收集 2,241 项；2,211 passed、21 failed、9 skipped、0 errors、7 warnings；pytest 墙钟耗时 10,845.73 秒（3:00:45），退出码 1。实际这次运行使用同内容的忽略脚本 `.dev/run_old_pytest.ps1` 和 PowerShell 7；已跟踪入口将必填旧仓库路径参数化，避免把本机旧目录写死在工具内。此前 PowerShell 5 的一次启动因中文路径解码错误在 pytest 收集前退出，未计入结果。
- 节点对照：五项计数完全一致；21 个 assertion-failure、0 个 error、9 个 skipped 的归一化节点集合分别完全一致，新旧各自独有节点均为 0。严格比较脚本 `scripts/migration/compare_pytest_summaries.py` 的 `equivalent=true`；旧仓库的 Git 状态在运行前后均为同两份原有未跟踪交接文档。
- 比较边界：新环境为 Python 3.12.13，旧环境为 Python 3.11.15，两边 pytest 均为 9.1.1；隔离参数形式相同，但 `--basetemp` 的绝对路径长度不同。因而这证明同一组节点在两套本机环境中呈现相同结果，不能把环境敏感失败归因于迁移，也不能宣称两套解释器和 Windows 路径条件完全相同。`fc1dd45` 后新增的 3 个开发工作流回归测试未包含在上述 2,241 项历史基线中，另行定向验证 20/20 通过。

严格节点比较用已跟踪工具从两份忽略的 JUnit 生成 JSON；不显示失败 traceback 或测试载荷：

```powershell
backend\.venv\Scripts\python.exe scripts\migration\summarize_junit.py .dev\task8-new-20260911-verify\pytest-new.xml > .dev\new-summary.json
backend\.venv\Scripts\python.exe scripts\migration\summarize_junit.py .dev\task8-old-20260911-verify-pwsh\pytest-old.xml > .dev\old-summary.json
backend\.venv\Scripts\python.exe scripts\migration\compare_pytest_summaries.py .dev\new-summary.json .dev\old-summary.json
```

比较脚本只有在全部计数及 failure/error/skip 节点集合均一致时退出 0。
- 新仓库失败节点：

- `test_advertising_governance::test_active_policy_allows_first_approved_action_then_enforces_daily_limit`
- `test_advertising_governance::test_ad_action_requires_approval_then_creates_7_14_30_day_reviews`
- `test_advertising_governance::test_automation_policy_enforces_kill_switch_limits_and_approval`
- `test_channel_wecom::test_concurrent_wecom_secret_rotations_serialize_and_match_running_config`
- `test_feishu_process_spike::test_parent_watchdog_escalates_from_ignored_terminate_to_kill`
- `test_feishu_process_spike::test_repeated_start_stop_leaves_no_supervisor_threads_or_children`
- `test_general_skills::test_general_skill_runner_executes_bash_package_command`
- `test_general_skills::test_general_skill_runner_materializes_folder_package`
- `test_harness_artifact_download::test_publisher_builds_relative_hashed_metadata`
- `test_harness_command::test_bounded_subprocess_caps_output_and_terminates_timeout`
- `test_harness_command::test_exec_command_validates_every_line_of_multiline_script`
- `test_harness_command::test_non_mount_sandbox_rewrites_model_visible_workspace_paths`
- `test_harness_v2::test_attachments_are_materialized_inside_only_the_task_workspace`
- `test_harness_v2::test_general_skill_harness_tool_does_not_enter_legacy_sandbox_runner`
- `test_harness_v2::test_general_skill_harness_tool_does_not_publish_legacy_runner_artifacts`
- `test_harness_v2::test_harness_reads_published_deliverable_from_an_earlier_task_frame`
- `test_harness_v2::test_staged_image_is_both_a_sandbox_file_and_vision_payload`
- `test_markdown_render::test_parse_multiple_inline_code_no_infinite_loop`
- `test_runner_bash_guard::test_bash_supported_on_dev_posix`
- `test_runtime_lock::test_runtime_lock_rejects_second_process_for_same_sqlite_database`
- `test_runtime_lock::test_runtime_lock_reports_existing_owner`

这些失败没有被描述成“全量绿灯”。旧仓库的 21 个同名失败构成直接基线证据：其中有执行门禁默认关闭、Windows 路径长度和换行差异、POSIX/Windows 进程及文件锁语义、时序等环境相关情形；具体归因仍以单项复现为准。此次没有出现迁移后独有的失败或缺失测试，现存失败是后续业务/跨平台修复工作，不能视为已解决。

## 前端、集成和打包门禁

| 检查 | 结果 |
| --- | --- |
| `npm --prefix frontend-enterprise run config:check` | 退出 0 |
| `npm --prefix frontend-enterprise run i18n:check` | 退出 0；4,209 条英文翻译覆盖 |
| `npm --prefix frontend-enterprise run test:typecheck` | 退出 0 |
| `npm --prefix frontend-enterprise test` | 退出 0；64 个文件、271 个测试通过 |
| `npm --prefix frontend-enterprise run build` | 退出 0；2,163 个模块完成生产构建 |
| TikTok 确定性 mock SOP replay | 退出 0；5/5，通过且 `external_writes=false` |
| Python runner compile、PowerShell AST、Bash `-n` | 均退出 0 |

Vite 保留既有插件耗时提示和大于 500 kB chunk 的非阻断警告。`frontend-enterprise/dist/` 是已重新生成且被 Git 忽略的运行产物。

集成 replay 的实际命令为：

```powershell
backend\.venv\Scripts\python.exe tests\integration\run_tiktok_mock_sop_replay.py
```

## PostgreSQL 门禁

忽略的 `backend/.env` 只在进程内加载，URL 未输出。运行 `backend/scripts/verify_postgres_production_gate.py` 的结果为 `ok=true`，缺失表 0、未启用 RLS 0、未强制 RLS 0、缺失角色 0、带 `BYPASSRLS` 的运行角色 0，退出 0。

以下是实际只读调用的脱敏等价形式；dotenv 值只进入子进程环境，不进入命令行或标准输出：

```powershell
@'
import os
import subprocess
from dotenv import dotenv_values

env = os.environ.copy()
env["STAFFDECK_POSTGRES_RUNTIME_URL"] = str(dotenv_values("backend/.env")["DATABASE_URL"])
subprocess.run(
    ["backend/.venv/Scripts/python.exe", "backend/scripts/verify_postgres_production_gate.py"],
    env=env,
    check=True,
)
'@ | backend\.venv\Scripts\python.exe -
```

Compose 项目 `joukir-restored-20260909` 的 PostgreSQL 与 Casdoor 在迁移和测试期间的各次检查均为 `healthy`，分别仅绑定回环端口 55433 和 18000；没有停止容器或修改其卷。

## Web 切换和在线行为

2026-09-12 09:40（Asia/Shanghai）执行已复审的本机切换脚本 `scripts/migration/cutover_web.ps1` 的同内容本地副本 `.dev/cutover_web.ps1`，退出 0，`Ok=true`、`RollbackPerformed=false`。旧 Web 启动器 PID 39436、监听 PID 23640 经路径、父子关系和精确 uvicorn 参数再次确认后停止；新启动器 PID 40608、监听 PID 37160 接管 5173，健康状态 `ok`，应用名“九骥 Joukir”。新旧进程 PID 是当次证据，不是长期固定配置。

切换只终止了经可执行路径、父子关系和精确 uvicorn 参数确认的旧 5173 进程树。新进程从 `joukir\backend` 启动，使用新虚拟环境、忽略的 `backend/.env` 和外置 `E:\develop\数字员工\joukir-runtime\data`；PID 写入忽略的 `.dev/local-web.pid`，日志写入外置 runtime 的 `logs/`。切换脚本包含失败时只停止新进程并恢复原命令的回滚路径。

无凭据 HTTP 验证：

| 检查 | 结果 |
| --- | --- |
| `GET /api/health` | 200；`status=ok`；应用名为“九骥 Joukir” |
| `GET /workspace/gallery` | 200；HTML root 和构建资源入口存在 |
| `GET /api/auth/oidc/config` | 200；OIDC 启用且登录入口匹配 |
| Casdoor `GET /api/health` | 200；`status=ok` |
| OIDC 无跟随跳转 | 302；进入回环 Casdoor `/login/oauth/authorize` |
| OAuth/OIDC 参数 | authorization code、回调 URI、state、nonce、PKCE challenge 和 `S256` 均存在并匹配 |

浏览器烟测：Codex 内置浏览器在 `http://127.0.0.1:5173/workspace/gallery` 实际渲染数字员工广场、分类、搜索和账户控件；此浏览器已有 Admin 会话，因此页面没有出现未登录的“企业 SSO 登录”按钮，不能把本次 UI 检查写成经按钮完成 SSO。另在 `http://127.0.0.1:18000/login` 实际渲染 Casdoor 的 Password 页和账号、密码字段；OIDC 入口到 Casdoor 的 302 与 PKCE 参数由上面的无凭据 HTTP 检查证明。未输入用户名、密码，也未提交认证。

## 最终仓库状态

在此记录提交且最终复审尚未完成时，功能分支 `chore/main-repository-migration` 包含验证证据，本地 `main` 仍为设计基线 `9cc0327b7ac84c0d277293cf347fea2ccd40a8cb`；复审通过后执行 `git merge --ff-only chore/main-repository-migration`，并另行核验两个分支指针。交接标签仍可解引用到原提交，`git fsck --full` 退出 0（只报告无引用 blob），无 object alternates、无 remote，未发生外部 push。新增的 8 个 `scripts/migration/` 文件是可复现审计和一次性切换工具，不会进入测试收集；当前后端收集 2,244 项，其中相对 2,241 项对照基线新增的 3 项为已定向通过的开发工作流回归测试。

交接仓库和备份目录均未删除。加密包 `Joukir-Casdoor-PostgreSQL-20260909.tar.enc` 为 217,915,841 字节，SHA-256 为 `7eaf0859d8662486e9ec9b33b0670e3270cd1db4a611721dee834229d08635b4`，与交接清单一致。独立 key 仍位于外部备份目录，为 43 字节；仅用 `Test-Path`、`Get-Item`、`Get-Acl` 检查存在性、大小和 ACL，未读取、打印、复制进 Git 或人工展示其内容；权限仅允许当前 Administrator 与 SYSTEM，且未继承。

备份核验的脱敏命令（不读取 key 内容）：

```powershell
$backup = 'E:\develop\数字员工\joukir-casdoor-database-backup-20260909'
$archive = Join-Path $backup 'Joukir-Casdoor-PostgreSQL-20260909.tar.enc'
$key = Join-Path $backup 'joukir-casdoor-database-backup-20260909.key'
(Get-Item -LiteralPath $archive).Length
(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
Test-Path -LiteralPath $key
(Get-Item -LiteralPath $key).Length
Get-Acl -LiteralPath $key | Select-Object AreAccessRulesProtected, Access
```

## 已知边界

- 本次验证没有使用人工 Casdoor 账号完成最终登录，也没有逐角色执行页面验收。
- 没有向外部模型发送真实请求；TikTok、广告、社交、渠道等第三方生产授权和写入仍按本地配置保持关闭或未验收。
- 备份不包含 MinIO 对象数据，Redis 和 Superset 也不在恢复范围内，因此历史对象资源可用性未证明。
- macOS/Linux 打包烟测、签名和 notarization 需要目标平台及维护者凭据。
- GitHub remote、首次 push、远端 required checks 和 `main` 分支保护需等待维护者提供真实仓库 URL。

## 回滚边界

旧源码目录会保留到用户人工验收后自行移除。若新 Web 后续需要回退，先根据 `.dev/local-web.pid` 和监听进程祖先再次确认它确实来自新虚拟环境，再停止该进程树；随后从交接仓库的 backend 目录按相同 uvicorn 参数启动，并继续使用外置 runtime 数据目录。PostgreSQL、Casdoor、数据库卷和加密备份无需参与 Web 进程回滚。
