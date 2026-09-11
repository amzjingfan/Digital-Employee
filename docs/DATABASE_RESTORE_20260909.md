# PostgreSQL 与 Casdoor 本机恢复记录

日期：2026-09-09。源码基线：`integration/portable-development-20260909` / `e0cb8df042b3a5f856c60b45cf7e9c2bafbc23b5`。

## 当前状态

独立 Compose 项目 `joukir-restored-20260909` 已启动，PostgreSQL 与 Casdoor 均为 healthy；Web/API 已连接恢复库，健康检查通过。原机器的运行路径、数据库端口及 M2M 文件路径已替换为本机路径。未修改应用业务源码。

| 服务 | 本机地址 | 说明 |
| --- | --- | --- |
| Joukir | http://127.0.0.1:5173/workspace/gallery | 点击“企业 SSO 登录”，使用原账号 |
| Casdoor | http://localhost:18000 | 原组织、应用和身份数据已恢复 |
| PostgreSQL | `127.0.0.1:55433` | 独立卷 `joukir-restored-20260909_postgres_data` |

全部端口仅监听回环地址。原有 CRM/WhatsApp 容器和数据卷未改动。

## 备份校验和恢复

源目录：`E:\develop\数字员工\joukir-casdoor-database-backup-20260909`。用户补充的 `joukir-casdoor-database-backup-20260909.key` 有效，未在报告或日志中记录密钥内容。

- 密文 SHA-256：`7eaf0859d8662486e9ec9b33b0670e3270cd1db4a611721dee834229d08635b4`。
- AES-256-GCM 认证解密成功；明文 tar SHA-256：`055c73afd57cdaa53748456e9a94e0daf86a8a1b7f1242abf024380e036b75f5`。
- 包内 40 项文件 SHA-256 校验全部通过。
- 从离线包导入 Casdoor `3.161.1` 和 pgvector `0.8.6-pg16-bookworm` 镜像，并核对镜像 ID；运行 PostgreSQL 16.15、vector 0.8.6。
- 四个数据库均在本次新建实例中恢复，`pg_restore --exit-on-error` 全部退出 0。
- 备份初始化脚本含 CRLF；仅将运行目录中的 shell 副本改为 LF，完成新集群初始化。原始交付包不变。

## 数据与权限验证

以下为恢复后的原始快照校验，均与备份清单匹配。后续服务鉴权会正常增加 Casdoor token/record，因此这些数字不是持续运行后的固定计数。

| 数据库 | 恢复时关键计数 |
| --- | --- |
| `casdoor` | 用户 6、应用 17、组织 2、token 108、record 177、API 权限规则 98 |
| `staffdeck_app` | 租户 1、用户 4、会话 32、消息 6、模型配置 1、技能 45、工具 32、任务 24、迁移记录 27 |
| `staffdeck_migration_drill_20260905` | 租户 1、用户 2、迁移记录 8 |
| `staffdeck_migration_restore_20260905` | 租户 1、用户 2、迁移记录 8 |

数据库 owner 正确。Casdoor、migrator、runtime、worker 均无超级用户、建库、建角色或 BYPASSRLS 权限。runtime 未设租户时用户计数为 0，设置 `tenant_demo` 时为 4，其他租户为 0。worker 和 migrator 行为符合各自现有策略。

## 与交付源码对齐

首次启动发现备份数据库缺少集成代码要求的 21 张表。只对恢复的 `staffdeck_app` 执行仓库已有的五个事务迁移：

1. `20260908_brand_access_v1`
2. `20260908_bi_metric_pipeline_v1`
3. `20260908_social_creator_audiences_v1`
4. `20260908_offsite_channel_assets_v1`
5. `20260908_pdca_search_term_rules_v1`

五个迁移全部成功，迁移记录从 27 增至 32；新增 21 张表均属于 migrator，且启用 FORCE RLS，强制 RLS 表总数从 125 增至 146。原业务关键计数保持一致，两个演练库保持备份版本。

## 应用与登录验证

- 后端使用原 APP_SECRET、数据库角色凭据与 OIDC 配置；原模型 API Key 解密成功，内容未输出。
- 前端 `.env.local` 启用 `VITE_OIDC_ENABLED=true`，TypeScript/Vite 构建、`config:check`、4209 条 i18n 覆盖检查通过。
- `/api/health` HTTP 200、`status=ok`；页面与 OIDC 配置接口 HTTP 200。
- Casdoor 健康接口、OIDC discovery、issuer、回调地址和原应用客户端凭据匹配检查通过。
- 浏览器点击“企业 SSO 登录”后进入 Casdoor 账号密码页，跳转使用 PKCE。尚未输入人工账号密码，不能据此声称已完成最终登录或角色页面验收。
- 12 个活跃数字员工服务身份通过现有 `authenticate_service_identity` 路径验证，覆盖 client credentials 换取令牌及签名、issuer、audience 校验；令牌未输出。
- 仓库 `verify_postgres_production_gate.py` 返回 `ok=true`，缺失表、RLS、角色和 BYPASSRLS 异常列表均为空。该检查只覆盖数据库前置条件，不代表全部业务已达到生产就绪。

## 文件和运行方式

- 运行配置与验证报告：`E:\develop\数字员工\joukir-runtime`。
- 当前后端配置：`E:\develop\数字员工\joukir-enterprise\source\backend\.env`。
- 保留的演示库：`E:\develop\数字员工\joukir-enterprise\source\backend\skill_agent_loop.db`；旧配置：`joukir-runtime\sqlite-demo.env`。
- 验证证据：运行目录中的 `primary-database-verification.json`、`drill-database-verification.json`、`migration-verification.json`、`m2m-verification.json`、`production-gate-verification.json`。前两份反映其验证时点；`verify_databases.py` 用于备份快照校验，不能直接当作迁移及鉴权后的固定计数监控。
- 临时明文 tar、解包目录、导入日志及容器内四个临时 dump 已删除。加密原包与恢复密钥保留；恢复后的数据库和运行必需 Secret 继续保留。
- 运行目录、当前后端 Secret 和恢复密钥的访问权限限制为当前管理员与 SYSTEM。密钥仍位于用户提供的备份目录；后续传输时应将密钥与密文分开。
- 启动命令见 [本地启动记录](./LOCAL_STARTUP_20260909.md)。Web 当前在隐藏后台进程运行，未配置开机自启；不要对 Compose 使用 `down -v`，否则会删除恢复的数据卷。

## 尚未覆盖

MinIO 对象数据、Redis、Superset 不在该备份内，本次未恢复或启动这些服务。原素材链接是否可用需要另行验证。

当前运行角色为 `api`，业务写入、任务自动执行、TikTok 正式连接等关闭。原模型凭据只验证了恢复和解密，未发起真实模型请求；外部连接器、后台任务、命令执行沙箱和人工账号业务流程仍待验收。第一阶段 SQLite 环境测试结果保留于启动记录，不冒充原库完整验收。
