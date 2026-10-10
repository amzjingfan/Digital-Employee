# Joukir 内网部署记录（2026-10-08）

## 2026-10-10 技能文件夹多选批量导入

- 当前应用发布目录为 `/home/joukir/releases/e5f8740-batch-skill-import`，源码对应本地分支提交 `e5f8740`。多技能文件夹弹窗支持勾选一项、多项或全选；点击“导入选中”后立即启用。新增批量接口将整批保存放在同一数据库事务中，任一项失败则整批回滚。
- 切换前 `joukir-backup.service` 成功；旧应用发布 `/home/joukir/releases/6e524a1-folder-import` 和旧 unit `/home/joukir/runtime/joukir.service.pre-e5f8740` 保留。前端以 `VITE_TENANT_ID=tenant_internal`、`VITE_TIKTOK_BUSINESS_UNIT_ENABLED=false` 构建，线上主 JS 与本地构建的 SHA-256 相同。
- 切换后健康、OIDC 配置、技能页面均为 200，TikTok API 为 404，PostgreSQL healthy。只读数据库计数发布前后均为 1 租户、2 用户、11 通用技能、19 知识库、17 工具。本轮没有上传或真实导入用户给出的四个技能文件夹。两套多技能合集的文件总大小分别约 0.03 MB 与 9.75 MB，低于 50 MB 站点请求上限。
- 自动化浏览器的 Chrome 桥接仍报 `nodeRepl.fetch request failed`；已登录管理员在可信任内网 CA 的浏览器中的最终视觉验收待完成。此项完成前分支保留，暂不合并 `main`。

## 2026-10-10 技能文件夹导入修复

- 当前应用发布目录为 `/home/joukir/releases/6e524a1-folder-import`，源码对应本地提交 `6e524a1`。更新了技能文件夹子技能选择、原子 UTF-8 读取及服务端多 `SKILL.md` 校验；四个下载目录没有上传到服务器，也没有创建技能记录。
- 切换前 `joukir-backup.service` 成功。旧发布 `/home/joukir/releases/b7b4048-skill-ref-20261010` 和旧 unit `/home/joukir/runtime/joukir.service.pre-6e524a1` 保留供应用回滚。前端以 `VITE_TENANT_ID=tenant_internal`、`VITE_TIKTOK_BUSINESS_UNIT_ENABLED=false` 构建，线上 JS 哈希与本地构建一致。
- 切换后服务正常，健康及 OIDC 配置接口 200，TikTok API 404，PostgreSQL 容器 healthy；只读计数仍为 1 租户、2 用户、10 通用技能、19 知识库、17 工具。管理员浏览器侧弹窗未验收：当前浏览器控制环境不信任内网 CA，不能绕过证书警告。结构和保存前校验见[四目录检查报告](../reports/skill-folder-import-check-20261010.md)。

## 2026-10-10 TikTok 事业部不纳入内网发布

- 当前应用发布目录为 `/home/joukir/releases/b7b4048-no-tiktok`，源码对应本地 `main@b7b4048`。构建前端时明确设置 `VITE_TENANT_ID=tenant_internal` 和 `VITE_TIKTOK_BUSINESS_UNIT_ENABLED=false`。侧栏不显示“TikTok 事业部”，前端不注册其页面路由；打包结果无 TikTok 页面文件或 `/api/enterprise/tiktok/` 调用代码。
- 原 Nginx 阻断继续生效：`/enterprise/tiktok` 返回 302，`/api/enterprise/tiktok/overview` 返回 404。当前应用的其他页面、Casdoor 登录入口和原生广场数据保留。
- 切换前 `joukir-backup.service` 成功；旧应用发布目录 `/home/joukir/releases/a59044e-tenant-internal` 与旧 unit `/home/joukir/runtime/joukir.service.pre-b7b4048` 保留用于回滚。切换后健康、控制台和 OIDC 配置接口均为 200，服务器提供的 JS 与已核验构建文件 SHA-256 一致。PostgreSQL 中 2 个用户、11 个非整体员工、19 个知识库、25 个 SOP、17 个工具未变。
- 生产打包只移除了该前端页面和入口；服务器端源码仍保留兼容实现，但 TikTok 官方接入、影子同步与执行开关保持关闭，外部 API 由 Nginx 拦截。若日后启用，需要单独审查权限、生产配置和发布门禁。

## 2026-10-10 原生广场数据导入

- 初次部署使用新空库，因此此前只显示 1 个测试员工，没有原生广场资源。现已在保留现有 PostgreSQL、`tenant_internal`、Casdoor 用户及测试员工的前提下，导入项目内置数据包：10 个原生员工、19 个知识库、9 个通用技能、25 个 SOP、17 个工具。库内目前有 11 个非整体员工（含原测试员工）、2 个用户、1 个租户；未导入 TikTok 资源。
- 导入程序是 [import_native_gallery.py](../../src/deploy/import_native_gallery.py)。以后新环境先完成数据库迁移、创建生产租户和管理员，然后运行此程序；不应开启 `DATABASE_SEED_DEMO_DATA`，因为那会创建 `tenant_demo` 与默认演示账号。程序默认事务回滚，带 `--apply` 才提交；重复执行已在本地验证不会增加重复记录。
- 本次服务器运行方式：先将该脚本复制到主机 root 可读的运行目录，再使用当前发布目录的 Python 与环境文件执行 `--tenant tenant_internal --admin joukir-admin` 试跑；确认计数、完成数据库备份后，增加 `--apply` 正式执行。`systemd-run` 从生产环境文件读取配置，避免把凭据写入命令或日志。新发布时替换 `RELEASE` 为实际发布目录。

```bash
RELEASE=/home/joukir/releases/a59044e-tenant-internal
install -m 600 "$RELEASE/src/deploy/import_native_gallery.py" /home/joukir/runtime/import_native_gallery.py
systemd-run --collect --wait --pipe -p EnvironmentFile=/home/joukir/config/joukir.env -p WorkingDirectory="$RELEASE/src/backend" -p Environment=PYTHONPATH=. "$RELEASE/src/backend/.venv/bin/python" /home/joukir/runtime/import_native_gallery.py --tenant tenant_internal --admin joukir-admin
systemctl start joukir-backup.service
systemd-run --collect --wait --pipe -p EnvironmentFile=/home/joukir/config/joukir.env -p WorkingDirectory="$RELEASE/src/backend" -p Environment=PYTHONPATH=. "$RELEASE/src/backend/.venv/bin/python" /home/joukir/runtime/import_native_gallery.py --tenant tenant_internal --admin joukir-admin --apply
```
- 导入前手动执行 `joukir-backup.service` 成功；服务器试跑及正式导入均成功。导入后直接核对数据库广场绑定为知识库 19、通用技能 9、SOP 25、工具 17，10 个原生员工已发布；HTTPS 健康接口 200，应用服务和 PostgreSQL 健康。截图中较早版本的 SOP 数量为 26；当前可核对的原生数据包和本地恢复库均为 25 个，未凭空补造第 26 个。

## 2026-10-10 前端生产租户修正

- 当前服务指向 `/home/joukir/releases/a59044e-tenant-internal`。源码仍是本地 `main@a59044e`，但前端以 `VITE_TENANT_ID=tenant_internal` 从不含 `.env.local` 的干净归档重新构建。回滚可切回 `/home/joukir/releases/a59044e`，切换前 unit 备份在 `/home/joukir/runtime/joukir.service.pre-tenant-internal`；该旧版前端含错误的 `tenant_demo`，仅宜作为短时应用回滚，不应长期恢复此租户错误。
- 用户登录后出现 `Tenant not found: tenant_demo` 与 `Tenant mismatch`，原因是前端构建期租户 ID 沿用了开发默认值，后端实际租户为 `tenant_internal`。新 JS 经检查包含 `tenant_internal` 且没有 `tenant_demo`；未改数据库、Casdoor 配置或后端源码。
- 修复前备份成功。只读数据库计数为 1 个租户、2 个用户、1 个未发布的数字员工草稿，0 个会话、团队、技能、知识库、消息和业务资源；这是先前部署的新库，并非历史库迁入。应用健康为 200、PostgreSQL 容器健康；用服务器上的应急账号在回环地址验证登录、租户匹配及员工/团队读取均为 200，未显示密码或令牌。用户浏览器可能需强制刷新获取新前端资源。

## 2026-10-10 Casdoor 登录入口修复

- 当前应用发布为本地 `main@a59044e`，位于 `/home/joukir/releases/a59044e`；前一版 `/home/joukir/releases/c158265` 及 `/home/joukir/runtime/joukir.service.pre-a59044e` 保留作应用回滚。下面的 `c158265` 是当天较早的品牌更新记录。
- 登录页原先依赖未随前端构建设置的 `VITE_OIDC_ENABLED`，虽然生产后端 OIDC 已启用，企业 SSO 按钮仍被隐藏。现在由登录页读取公开 `/api/auth/oidc/config` 的 `enabled` 状态，显示“企业 SSO 登录”；本地应急登录保留。
- 发布前备份成功。生产页面经本地 SSH 隧道在浏览器确认按钮出现；从 Windows 携带内网 CA 访问登录和健康接口均返回 200，OIDC 登录入口返回 302，应用及 PostgreSQL 容器健康，TikTok API 仍为 404。未改 Casdoor 配置或数据库。客户端浏览器仍需信任内网 CA；本次未进行真实凭据登录。

## 2026-10-10 应用品牌更新

- 当前应用源码为本地 `main@c158265`，发布目录 `/home/joukir/releases/c158265`。`joukir.service` 的工作目录和启动命令已同步指向新目录，原 `/home/joukir/releases/58d6691` 及 `/home/joukir/runtime/joukir.service.pre-c158265` 保留供应用回滚。本节以下的 `58d6691` 描述是 2026-10-08 的初次发布记录。
- 首次引导弹窗与登录预览图显示“九骥 Joukir”，用户可见的导出文件名和运行提示已更新；内部兼容标识仍为原名。沿用原 PostgreSQL Compose 容器、`staffdeck_app` 数据库、Casdoor 与生产配置；未运行数据库迁移、重建或重新播种。切换前手动执行备份服务成功。
- 验证：新发布目录后端模块导入成功；服务重启后 HTTPS `/api/health` 和 `/enterprise/dashboard` 返回 200，TikTok API 返回 404、页面入口返回 302，PostgreSQL 容器健康。Windows 客户端使用内网 CA 验证后，健康和登录页均返回 200；Schannel 因内网 CA 没有在线撤销查询，验证时关闭该查询。用户浏览器尚需信任内网 CA 后目视验收已登录的引导弹窗。

## 2026-10-08 初始发布

- 主机：`192.168.110.210`，Ubuntu 26.04；访问入口：[https://192.168.110.210](https://192.168.110.210)。发布源码为 `main@58d6691`，位于 `/home/joukir/releases/58d6691`。
- Nginx 的独立 `192.168.110.210:443` 站点代理到只监听 `127.0.0.1:5174` 的 `joukir.service`。既有 80、3080 端口和站点未改动。
- PostgreSQL 16 在独立 Compose 项目 `joukir-internal` 中运行，数据库仅映射到 `127.0.0.1:55434`。全新数据库 `staffdeck_app` 使用无业务数据的结构快照引导；已写入 `tenant_internal`。运行、迁移和工作角色均无超级用户或 `BYPASSRLS` 权限，生产 RLS 门禁通过。
- Casdoor 使用主机上已有服务；本次新增 `joukir` 组织、`app-joukir` 应用和 `joukir-admin` 组织管理员。登录会跳转到 `https://casdoor.overselfx.com`，内网客户端需要能访问该地址。另有 `emergency-admin` 本地应急管理员。
- TikTok 官方连接、影子同步、真实业务执行、工作任务后台执行及公开 API 均关闭；Nginx 对整组 `/api/enterprise/tiktok` 返回 404，直接访问 `/enterprise/tiktok` 跳回控制台。发布包仍包含项目已有 TikTok 页面与历史结构，前端菜单项尚未隐藏；未接入 TikTok 授权、凭据或同步。
- 默认模型地址 `127.0.0.1:52010` 当前未监听。控制台、身份认证和核心 API 可用；模型生成需另行提供生产模型端点及安全凭据交接。

## 证书和凭据

- HTTPS 使用独立内网 CA 签发的 IP 证书，有效期至 2027-10-08。CA SHA-256 指纹：`73:E9:FE:59:2C:52:88:DE:5C:E1:00:8B:42:17:1A:45:0F:8C:61:3B:66:5E:6C:8B:8A:C5:EC:AA:0D:9E:4C:DB`。
- 需由管理员核对上述指纹后，将公有 CA 证书 `/home/joukir/runtime/tls/ca.crt` 安装到访问设备的受信任根证书存储区；Windows 操作机保留一份在 `E:\develop\数字员工\joukir-runtime\deploy-20261008\joukir-internal-ca.crt`。不要分发 CA 私钥。
- 正常管理员用户名为 `joukir-admin`，密码仅存主机 root 可读的 `/home/joukir/runtime/casdoor_admin_password`。应急账号用户名为 `emergency-admin`、租户为 `tenant_internal`，密码仅存 `/home/joukir/runtime/local_admin_password`。运行配置位于 `/home/joukir/config/joukir.env`，不在 Git 中。需要交接时由授权管理员通过 SSH 在主机上读取，不要复制到聊天、工单或文档。

## 日常操作与备份

```bash
systemctl status joukir.service --no-pager
systemctl restart joukir.service
docker compose -f /home/joukir/runtime/postgres-compose.yml -p joukir-internal ps
curl --cacert /home/joukir/runtime/tls/ca.crt https://192.168.110.210/api/health
systemctl status joukir-backup.timer --no-pager
systemctl start joukir-backup.service
```

- `joukir-backup.timer` 每日约 02:30 运行，将 PostgreSQL 自定义格式转储、Casdoor SQLite 一致性快照及含密钥的配置归档写入 `/home/joukir/backups/`；目录仅 root 可读，约保留七天。归档本身未加密，复制到异机前必须加密传输和加密存储。首次备份已校验归档目录与 SQLite 完整性。恢复前应再做一次异机恢复演练；同机备份不能替代异机副本。
- 查看服务日志：`journalctl -u joukir.service -n 100 --no-pager`。Nginx 配置在 `/www/server/panel/vhost/nginx/joukir-internal.conf`；此主机的 aaPanel Nginx 由 `/www/server/nginx/sbin/nginx` 运行，不能以 `systemctl status nginx` 判断实际状态。改动后先执行 `/www/server/nginx/sbin/nginx -t -c /www/server/nginx/conf/nginx.conf`，再执行同一二进制的 `-s reload`。
- 如需回滚应用代码，先确认目标发布目录的依赖、前端构建及数据库兼容性，再将 `joukir.service` 的 `WorkingDirectory` 和 `ExecStart` 同步切到目标版本，`systemctl daemon-reload && systemctl restart joukir.service`。数据库恢复必须单独规划，不能简单用旧代码覆盖新结构。

## 本次验证和剩余事项

- 前端构建、配置检查、i18n 检查和完整仓库的前端测试类型检查通过；聚焦后端测试 50 项通过。目标主机的生产配置校验、PostgreSQL 生产门禁、RLS 无上下文/租户上下文隔离、Nginx 配置测试均通过。
- 从 Windows 客户端携带 CA 证书访问 HTTPS 健康接口返回 200；目标主机上健康接口和控制台页面返回 200。TikTok API 返回 404、页面入口返回 302。真实 Casdoor 授权码回调得到 `tenant_internal` 的 `admin/platform_admin` 身份，登出返回 204；本地应急账号的登录与 `/api/auth/me` 返回 200。应用服务重启后再次检查健康接口和控制台页面，均为 200。
- 尚需在使用者的浏览器中安装并信任内网 CA，进行页面目视验收。模型生成需配置实际提供者。异机备份与恢复演练尚未完成。
