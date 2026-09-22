# TikTok P3-B0 可运行数据验证工作台设计

日期：2026-09-22

## 状态

用户已在对话中批准总体方向。本书面规格在进入实现计划和业务源码修改前等待复核。

## 目标

在现有 TikTok 事业部页面内增加一个租户隔离、可持久化、可重复运行的数据验证工作台，把 PRD 19.1 的 P3-B0 要求变成可检查的系统状态：

- 明确美国市场试点店铺、达人范围、业务 Owner、数据 Owner 和授权现状。
- 建立联盟样品、订单、物流、视频、PID/归因和 GMV 的字段契约与来源优先级。
- 按具体动作记录 Seller、Affiliate、Creator/Partner、Ads/Product GMV Max、LIVE、店铺消息和客服的 E0-E3 证据。
- 对 FastMoss、领星/ERP、达密 Ultra 和飞书形成可审计的采用、暂缓或拒绝结论。
- 运行确定性的 Mock 数据校验，保存输入摘要、检查结果和问题列表。
- 分别显示“工作台配置就绪”和“真实数据就绪”，禁止用 Mock、文档、登录成功或其他接口的证据替代真实账号端到端验证。

本阶段交付的是 P3-B0 的验证能力和事实盘点入口，为 P3-B1 的看板、样品履约和指标字典建立输入门禁；不提前实现 P3-B1 的业务事实表和运营看板。

## 已知事实、设计推断与产品决定

### 已知事实

- PRD 要求 P3-B0 覆盖试点范围、字段字典、来源优先级、Mock 或录制回放、动作级 E0-E3 证据和四个外部系统的接入结论。
- PRD 定义 E0 为未核验，E1 为官方文档或合同声明，E2 为沙箱、授权导出或 Mock 契约验证，E3 为真实账号按目标市场、主体、scope 和资产完成端到端验证。
- 当前代码已有租户隔离的 TikTok 组织、资源、外部授权、Mock SOP 回放、Seller 官方只读连接器和影子运行能力，但没有 P3-B0 字段契约与能力证据工作台。
- 当前官方连接器只独立证明 Seller 只读路径；Affiliate、Creator/Partner、Ads、LIVE 和消息动作不能继承 Seller 的验证结论。
- 当前 13 个 TikTok 后端专项测试文件共 68 项通过。完整后端套件仍有仓库已记录的其他基线失败，因此本设计只把专项结果作为当前改动前基线。
- 真实美国店铺部署、完整 OAuth 回调和各目标动作的真实账号调用尚未形成独立 E3 验收证据。

### 设计推断

- P3-B0 首先需要一个能保存口径、责任和证据并反复运行校验的内部工作台；直接构建所有真实 Connector 会把尚未确认的权限、字段和供应商决定固化进生产结构。
- 字段来源需要同时表达 Mock 来源与候选真实来源，否则 Mock 校验通过容易被误读为生产数据可用。
- 证据必须按“平台域 + 动作 + 主体/资产”记录。平台登录成功、同平台其他接口通过或一个租户的结果都不能外推到目标动作。

### 产品决定

- 首版只内置确定性 Mock 数据集，不接受用户上传的原始外部响应，不接入真实同步任务。
- 租户管理员负责修改和运行；其他已登录租户用户只读，以便业务角色共同核对口径。
- 当前状态由服务实时计算；运行记录保存当时的状态快照用于审计，不把快照当作后续真实状态。
- P3-B0 可以在 `real_data_ready=false` 时完成“可运行工作台”交付。真实数据门禁需要后续独立 E3 和真实或脱敏录制回放证据。

## 非目标

- 不实现 P3-B1 的 BD 看板、样品履约事实、订单事实、视频指标或 GMV 聚合。
- 不在浏览器或 API 路由里直接调用 TikTok、FastMoss、领星、达密或飞书。
- 不保存 Token、Cookie、客户端密钥、原始 OAuth 载荷、原始第三方响应、达人地址或明文联系方式。
- 不把外部账号可登录、文档说明、Mock 通过或 Seller Scope 自动提升为其他动作的 E3。
- 不开放消息发送、发布、预算、活动、直播控制或其他外部写入。
- 不在首版支持原始文件上传或任意录制数据导入；这需要单独的数据脱敏、文件扫描、保留期和访问控制设计。

## 核心概念

### 工作台配置就绪

`workbench_ready` 表示 P3-B0 配置与 Mock 验证闭环完整，可以进入真实来源接入和 P3-B1 设计，不表示真实业务数据已经可读。它由服务根据当前记录实时计算。

### 真实数据就绪

`real_data_ready` 表示当前试点范围需要的读取动作都有未过期 E3、有效资产授权和真实或经批准脱敏的录制回放。首版没有录制回放入口，因此 Mock 运行永远不能把该值变为 `true`。

### 字段契约

字段契约定义一个稳定的标准字段代码、对象域、类型、是否必需、Owner、关联业务键、新鲜度上限、缺失处理和按优先级排列的来源候选。它描述未来 P3-B1 可以依赖什么，不存储业务事实本身。

### 动作级能力证据

能力证据描述一个明确动作在指定主体、市场、scope 和资产上的验证等级、证据类型、结论、检查时间和有效期。证据条目不能跨动作、租户或资产继承。

## 数据模型

四类租户数据由四张物理表承载。每张表包含 `tenant_id`，PostgreSQL 启用并强制 RLS；所有唯一约束、查询和关联都包含租户边界。

### `tiktok_data_validation_scopes`

每个租户和市场一条当前试点范围记录，首版只允许 `market='US'`。

| 字段 | 含义 |
|---|---|
| `id` | 内部 ID |
| `tenant_id` | 租户边界 |
| `market` | 首版固定为 `US` |
| `store_resource_id` | 已存在的 `business_resources` 店铺资源，可在配置前为空 |
| `creator_scope_summary` | 不含 PII 的达人范围说明，例如名单来源、数量和筛选边界 |
| `business_owner_user_id` | 业务验收 Owner，可在配置前为空 |
| `data_owner_user_id` | 字段与授权 Owner，可在配置前为空 |
| `status` | `draft`、`active` 或 `closed` |
| `revision` | 乐观并发版本 |
| `created_at` / `updated_at` | 审计时间 |

约束：`(tenant_id, market)` 唯一；选择店铺时必须是同租户、`resource_type='store'` 且状态有效；Owner 必须是同租户有效用户。服务不允许把范围标为 `active`，除非店铺和两个 Owner 都存在。

### `tiktok_field_contracts`

每个标准字段一条记录，不拆出业务事实表。`sources_json` 使用固定 Pydantic 结构校验，避免首版为尚未确定的供应商建立过早的连接器表。

| 字段 | 含义 |
|---|---|
| `id` | 内部 ID |
| `tenant_id` | 租户边界 |
| `field_code` | 稳定标准代码，例如 `order.order_id` |
| `domain` | `sample`、`order`、`logistics`、`video`、`attribution` 或 `gmv` |
| `label` | 中文展示名 |
| `data_type` | `string`、`datetime`、`decimal`、`integer`、`boolean` 或 `enum` |
| `required` | 是否属于 P3-B0 必需字段 |
| `owner_user_id` | 同租户字段 Owner，可在配置前为空 |
| `business_key` | 该字段所属记录的主关联键，例如 `order_id` 或 `video_id` |
| `freshness_sla_seconds` | 可接受的最大数据年龄，正整数 |
| `missing_behavior` | `unknown`、`manual_review`、`block_stage` 或 `not_applicable` |
| `sources_json` | 有序来源候选列表 |
| `status` | `draft`、`confirmed`、`blocked` 或 `not_applicable` |
| `revision` | 乐观并发版本 |
| `created_at` / `updated_at` | 审计时间 |

每个来源候选包含：

- `source_key`：稳定来源代码。
- `source_type`：`official_api`、`approved_export`、`internal_database`、`vendor` 或 `mock_fixture`。
- `object_name` 与 `field_path`：来源对象和字段路径。
- `priority`：同一字段、同一 `usage` 下从 1 开始且不能重复。
- `usage`：`mock` 或 `real`。
- `decision`：`use`、`defer` 或 `reject`。
- `authorization_state`：`not_required`、`unverified`、`authorized` 或 `denied`。

`decision='use'` 且 `usage='real'` 的来源如果是 `official_api` 或 `vendor`，必须为 `authorization_state='authorized'` 才能参与真实数据门禁。`denied` 来源只能是 `reject`，不能被验证器选择。Mock 来源只能服务 Mock 运行。

字段目录由代码常量确定并通过幂等 bootstrap 创建，首版覆盖以下最小集合：

- 样品：申请 ID、达人 ID、商品 ID、状态、申请时间、履约截止时间。
- 订单：订单 ID、达人 ID、商品 ID、状态、创建时间、完成时间。
- 物流：订单 ID、运单号、物流状态、事件时间。
- 视频：视频 ID、达人 ID、商品 ID、发布时间、播放量、点赞量。
- PID/归因：PID、订单 ID、归因窗口开始和结束时间。
- GMV：订单 ID、金额、币种、发生时间。

bootstrap 只提供标准代码、类型、必需性、Mock fixture 来源和建议缺失处理；它不替用户填写 Owner，不把任何真实来源标为已授权，也不自动确认字段。

### `tiktok_capability_evidence`

同一张表记录平台动作和外部系统决策，使用 `entry_kind` 区分。

| 字段 | 含义 |
|---|---|
| `id` | 内部 ID |
| `tenant_id` | 租户边界 |
| `entry_code` | 稳定目录代码 |
| `entry_kind` | `capability` 或 `provider_decision` |
| `platform_domain` | Seller、Affiliate、Creator/Partner、Ads/GMV Max、LIVE、Messaging、FastMoss、Lingxing、Dami 或 Feishu |
| `action` | 具体读取/写入/导出动作；供应商条目为 `integration_decision` |
| `direction` | `read`、`write`、`export` 或 `decision` |
| `subject_key` | 证据适用主体或 `global`，避免空值唯一约束失效 |
| `resource_id` | 可选的同租户业务资源 |
| `required_scope` | 目标 scope 文本；不存 Token |
| `endpoint_or_artifact` | API 路径、导出类型或合同材料的安全引用，不存原始载荷 |
| `api_version` | 适用 API/导出版本 |
| `evidence_level` | `E0`、`E1`、`E2` 或 `E3` |
| `evidence_type` | `unverified`、`official_docs`、`contract`、`mock`、`sandbox`、`approved_export` 或 `real_account` |
| `status` | `unverified`、`verified`、`blocked` 或 `not_applicable` |
| `decision` | 平台动作可为空；供应商条目必须是 `use`、`defer` 或 `reject` |
| `summary` | 结论、限制或阻塞原因，不含秘密和原始数据 |
| `evidence_ref` | Evidence ID、文件哈希或受控记录引用 |
| `checked_by_user_id` | 同租户检查人 |
| `checked_at` / `valid_until` | 检查时间和可选失效时间 |
| `revision` | 乐观并发版本 |
| `created_at` / `updated_at` | 审计时间 |

约束：`(tenant_id, entry_code, subject_key)` 唯一。E3 只允许 `evidence_type='real_account'`；E2 只允许 Mock、沙箱或经批准导出；过期证据不参与当前门禁。供应商条目必须有决定、摘要和检查人。

bootstrap 至少创建这些动作目录：

- Seller：读取店铺、读取 Seller 权限、读取商品、读取订单、读取物流。
- Affiliate：读取样品申请、读取联盟订单、读取联盟 GMV。
- Creator/Partner：读取达人档案、读取视频、读取合作关系。
- Ads/Product GMV Max：读取活动、商品层、素材层、花费与收入归因。
- LIVE：读取场次、商品、流量互动和交易漏斗。
- 店铺消息：读取会话、生成建议、人工发送、受控发送。
- 客服：读取工单、生成建议、人工发送、受控发送。
- 外部系统：FastMoss、领星/ERP、达密 Ultra、飞书各一条接入决定。

不同发送动作保留独立条目；工作台不执行这些动作。任何写入动作未达 E3 时只显示阻塞，不能通过本工作台开启。

### `tiktok_data_validation_runs`

保存每次确定性验证的审计摘要，不保存原始记录。

| 字段 | 含义 |
|---|---|
| `id` | 内部 ID |
| `tenant_id` | 租户边界 |
| `mode` | 首版固定为 `mock` |
| `catalog_version` | 字段和规则目录版本 |
| `dataset_digest` | 规范化 fixture 的 SHA-256 |
| `record_count` | 被验证的规范化记录数 |
| `status` | `passed` 或 `failed` |
| `workbench_ready_snapshot` | 运行时工作台就绪快照 |
| `real_data_ready_snapshot` | 首版必须为 `false` |
| `checks_json` | 检查代码、通过状态和计数，不含原值 |
| `issues_json` | 问题代码、字段代码、严重度和说明，不含原值 |
| `started_by_user_id` | 运行人 |
| `created_at` | 运行时间 |

同一输入和目录版本产生同一 `dataset_digest` 与检查结果。运行记录追加写，不能更新或删除。

## 后端模块边界

- `app/tiktok/data_validation.py`：目录常量、bootstrap、读写服务、就绪计算和确定性 Mock 验证。外部网络调用不进入该模块。
- `app/tiktok/schema.py`：请求和响应模型，含严格枚举、长度、正整数和 `sources_json` 结构验证。
- `app/api/tiktok.py`：仅做认证、请求映射、HTTP 错误转换和事务入口；业务规则留在服务模块。
- `app/db/models.py`：四个 SQLModel 持久化模型。
- PostgreSQL migration：建表、组合约束、索引、RLS 策略和可逆 down migration。

服务方法必须从 `current_user.tenant_id` 取得租户，忽略或拒绝调用方提交的租户字段。写操作先执行 `ensure_tenant_admin`，再做同租户资源与用户校验。

## API 契约

所有路径沿用 `/api/enterprise/tiktok` 前缀。

| 方法 | 路径 | 行为 | 权限 |
|---|---|---|---|
| `GET` | `/data-validation` | 返回范围、字段契约、能力证据、最近运行、两个就绪状态和阻塞项 | 当前租户用户只读 |
| `POST` | `/data-validation/bootstrap` | 幂等补齐当前目录缺失项，不覆盖租户已编辑值 | 租户管理员 |
| `PUT` | `/data-validation/pilot-scope` | 创建或按 `revision` 更新 US 试点范围 | 租户管理员 |
| `PUT` | `/data-validation/field-contracts/{field_code}` | 按 `revision` 更新一个已知字段契约 | 租户管理员 |
| `PUT` | `/data-validation/capability-evidence/{entry_code}` | 按 `revision` 更新一个已知动作或供应商决定 | 租户管理员 |
| `POST` | `/data-validation/runs/mock` | 对内置 fixture 运行确定性校验并追加运行记录 | 租户管理员 |

目录代码不由客户端创建。未知代码返回 404；版本冲突返回 409；跨租户资源、用户或证据引用返回 404，避免暴露其他租户对象是否存在；非管理员写入返回 403。

`GET /data-validation` 不返回凭据引用、Token 指纹、原始授权 metadata 或原始第三方数据。阻塞项使用稳定代码，前端可直接定位到对应范围、字段或能力行。

## 就绪算法

### `workbench_ready`

必须同时满足：

1. US 试点范围为 `active`，店铺资源、业务 Owner、数据 Owner 和达人范围说明完整。
2. 每个必需字段为 `confirmed`，有 Owner、业务键、正数新鲜度、明确缺失处理，并至少有一个 `decision='use'` 的 Mock 来源。
3. 没有 `authorization_state='denied'` 的来源被标记为 `use`；未核验真实来源可以保留为 `defer`，但不能伪装成可用。
4. 每个必需动作都有明确的 `verified`、`blocked` 或 `not_applicable` 结论、检查人和检查时间；证据等级与证据类型组合有效。
5. FastMoss、领星/ERP、达密 Ultra、飞书都有 `use`、`defer` 或 `reject` 决定及理由。
6. 最近一次 Mock 运行通过当前 `catalog_version`，且输入摘要可复算。

被阻塞的真实能力不会阻止工作台本身运行，但会以阻塞项进入响应，并阻止 `real_data_ready`。这使 P3-B0 能如实记录“不具备某能力”，而不是为了获得绿色状态虚构证据。

### `real_data_ready`

必须在 `workbench_ready=true` 基础上同时满足：

1. 当前试点需要的所有读取动作达到未过期 E3，证据类型为 `real_account`，主体、US 市场、scope 和店铺/资产完全匹配。
2. 对应 `external_authorizations` 记录状态有效、未过期并绑定同一资源；只记录安全状态，不读取或显示凭据内容。
3. 每个必需字段至少有一个 `usage='real'`、`decision='use'` 且授权状态允许的来源。
4. 存在真实数据或经批准脱敏的录制回放验证，校验业务键唯一性、关联完整性、新鲜度、币种、时区和缺失处理。

首版没有第 4 项入口，因此服务明确返回 `real_data_ready=false` 和 `recorded_or_real_validation_missing`。Mock 运行不允许改变该结果。

## Mock 验证规则

fixture 固定在后端代码并带 `catalog_version`，包含正常记录和可单测的失败变体。生产 API 只运行正常 fixture；失败变体用于自动化测试验证问题检测能力。

检查至少覆盖：

- 必需字段存在且类型正确。
- 样品、订单、视频和物流业务键非空且在各自对象内唯一。
- 订单、物流、视频、PID 和 GMV 对引用的业务键可关联；无法关联时报 `manual_review`，不猜测合并。
- 金额为 Decimal 可解析值且不为负，币种为大写三字母代码；缺少金额或币种时 GMV 为未知而不是 0。
- 时间字段可解析、归因窗口起止顺序正确、事件不晚于允许的未来偏差。
- `observed_at` 与字段新鲜度 SLA 比较，陈旧数据明确失败或降级。
- PID 与商品关联冲突进入问题列表，不选择“最新值”覆盖。
- 未授权或被拒绝的真实来源不被验证器选中。

结果只保存检查代码和计数；fixture 原值不进入数据库、日志或前端响应。

## 前端工作台

在 `TikTokBusinessUnitPage` 增加第七个“数据验证”页签。页面由五个区域组成：

1. 顶部状态卡：工作台配置就绪、真实数据就绪、最近 Mock 运行、当前阻塞数，并解释两个状态的区别。
2. 试点范围：US 店铺、达人范围、业务 Owner、数据 Owner 和当前授权摘要。
3. 字段契约表：按域分组显示字段、Owner、业务键、新鲜度、缺失处理、优先来源和状态。
4. 能力证据矩阵：按平台域和具体动作显示 E0-E3、证据类型、主体/资产、检查时间、结论和阻塞；四个外部系统决定单独分组。
5. Mock 运行：管理员可启动校验；所有角色可查看摘要、检查项和问题代码。

管理员看到编辑和运行控件。其他角色使用同一数据响应但控件禁用并显示只读说明。页面不展示或接受秘密、原始外部响应、达人联系信息或地址。新增文案沿用现有 TikTok 页面模式；仍运行仓库 i18n 检查，本任务不顺带重构整页文案体系。

## 迁移、RLS 与审计

- 使用新的可逆 SQL migration 建四张表和索引；SQLite 测试由 SQLModel metadata 创建对应结构。
- PostgreSQL 对四张表启用 `ENABLE ROW LEVEL SECURITY` 和 `FORCE ROW LEVEL SECURITY`。
- `staffdeck_runtime` 只能访问 `tenant_id = app.current_staffdeck_tenant_id()`；worker 策略沿用现有受控跨租户模式，但服务任务仍显式传递租户。
- 资源、Owner 和检查人关联必须验证同租户；可用的关联采用 `(tenant_id, id)` 组合外键。
- 运行记录追加写。可编辑表用 `revision` 防止覆盖其他管理员刚提交的修改。
- API 不提供删除。目录升级通过 bootstrap 增加新条目，已有租户修改不被覆盖；停用项使用状态表达。

## 失败处理

- 工作台尚未 bootstrap：GET 返回空状态和 `catalog_not_bootstrapped`，页面提供管理员初始化操作。
- 目录部分缺失：bootstrap 只补缺失条目，返回创建数和当前目录版本。
- 版本冲突：返回 409 和当前 revision，前端刷新该行，不静默覆盖。
- 无效证据组合：返回 422，例如 E3 搭配 Mock 或供应商决定缺少理由。
- Mock 校验失败：保存 `failed` 运行及结构化问题；不回滚该审计记录，也不创建 P3-B1 业务事实。
- 数据库或事务失败：回滚编辑，不创建半成品运行；错误响应不包含连接串或输入值。

## 测试策略

按照红绿重构顺序实现。聚焦测试包括：

### 后端

- bootstrap 可重复调用，第二次不复制记录，也不覆盖租户修改。
- 两个租户使用相同字段代码、店铺代码、外部业务键和能力代码时完全隔离。
- 租户成员可读但不能 bootstrap、编辑或运行；管理员只能引用本租户店铺和用户。
- 未知目录代码、错误 revision、跨租户引用和无效枚举分别返回预期状态码。
- `workbench_ready` 精确列出缺失 Owner、业务键、新鲜度、缺失处理、来源决定、能力结论和供应商决定。
- `blocked` 能力可以完成事实盘点，但不能使 `real_data_ready` 通过。
- Mock 运行摘要稳定；缺字段、重复业务键、陈旧数据、错误金额/币种、PID 冲突和跨对象断链能被检测。
- Mock、文档、沙箱、登录成功和其他动作 E3 都不能把目标动作或真实数据状态升级。
- 过期 E3、错误主体、错误市场、错误 scope 或错误资产不参与真实数据门禁。
- 运行记录不包含 fixture 原值、凭据或原始第三方载荷。
- PostgreSQL migration 有 FORCE RLS、租户组合约束和 down migration；测试布局门禁通过。

### 前端

- 第七个页签能加载空状态、已 bootstrap 状态、就绪状态和 API 错误。
- 管理员可见初始化、编辑和运行入口；成员只读且不能触发写请求。
- 工作台就绪和真实数据就绪使用不同标签与解释；Mock 通过仍显示真实数据未就绪。
- 字段和能力阻塞项可定位，过期和 E0-E3 状态可访问地呈现。
- Mock 运行结果不展示原始 fixture 数据。

### 验证命令

- 聚焦后端 pytest 及现有 TikTok 专项回归。
- PostgreSQL migration/RLS 测试和 `src/tests/check_test_layout.py`。
- 变更 Python 路径 Ruff。
- 前端 Vitest、测试类型检查、i18n 检查、Vite 配置检查和生产构建。
- 受影响路由分别以管理员和成员在浏览器验证，并保留不含秘密或个人数据的截图证据。

## 实施切片

1. 先用失败测试固定表约束、目录、bootstrap、租户隔离和就绪算法，再实现模型、migration 和服务。
2. 用失败测试固定 API 权限、revision 冲突、错误映射和 Mock 运行记录，再接入 TikTok router。
3. 用前端失败测试固定管理员/成员差异和两个就绪状态，再实现“数据验证”页签。
4. 运行专项、迁移、RLS、前端和构建门禁，最后做双角色浏览器验收。

每个切片都必须保持 Mock 与真实数据状态分离。真实授权或录制数据接入作为后续独立设计，不在实现过程中临时扩展。

## 预计变更文件

- `src/backend/app/db/models.py`
- `src/backend/app/tiktok/data_validation.py`
- `src/backend/app/tiktok/schema.py`
- `src/backend/app/api/tiktok.py`
- `src/backend/migrations/<timestamp>_tiktok_data_validation_workbench_v1.sql`
- `src/backend/migrations/<timestamp>_tiktok_data_validation_workbench_v1.down.sql`
- `src/frontend-enterprise/src/pages/TikTokBusinessUnitPage.tsx`
- `src/tests/backend/test_tiktok_data_validation.py`
- `src/tests/backend/test_postgres_tiktok_data_validation_migration.py`
- `src/tests/frontend/TikTokBusinessUnitPage.test.tsx`
- 相关文档索引、开发记录和未完成时的交接记录

## 验收标准

- 管理员可在 UI 初始化目录、配置 US 试点、维护字段契约和动作级证据，并运行 Mock 校验。
- 成员可以读取同租户安全摘要，但所有写入口在 UI 和 API 两层都被拒绝。
- 每个必需字段能显示 Owner、来源优先级、业务键、新鲜度和缺失处理；被拒绝或未授权来源不能作为真实使用来源。
- 每个要求的平台动作都有独立 E0-E3 记录，四个外部系统各有明确决定和理由。
- Mock 结果可复算、可审计、无原始敏感数据；失败检查能指出字段和问题代码。
- `workbench_ready` 与 `real_data_ready` 独立计算，任何 Mock 结果都不能使后者通过。
- 两个租户使用相同外部标识时没有读取、更新或聚合串租户。
- PostgreSQL 四张表全部 FORCE RLS，迁移可正向和回退执行。
- 现有 TikTok 专项测试保持通过，新增聚焦后端和前端测试通过。

## 后续边界

书面规格通过后再编写逐步实施计划。首版工作台完成后，下一项独立工作应是按 US 试点店铺接入真实 Seller/Affiliate 读取或经批准的脱敏录制回放，并用工作台记录对应 E3；在此之前不得宣称 P3-B1 已具备真实数据输入。
