# TikTok P3-B0 脱敏录制回放验证设计

日期：2026-09-22
状态：已完成会话设计确认，等待书面规格复核
基线：`main@5a34f63`，现有目录版本 `p3-b0.v1`

## 1. 背景与目标

现有 P3-B0 数据验证工作台已经具备租户隔离的试点范围、30 个字段契约、27 个动作能力、4 个供应商决定、确定性 Mock 校验和独立的 `workbench_ready` / `real_data_ready` 门禁。Mock 能证明工作台可运行，不能证明真实业务形态的数据可用。

本设计增加经审批的脱敏录制数据回放入口。管理员在浏览器选择本地 JSON 文件，服务在严格大小限制内完成内存校验，只保存不可逆摘要、无原值检查结果、审批元数据和范围/契约快照。原始文件、原始记录、文件名、外部响应、OAuth 载荷和凭据不进入数据库、日志或响应。

成功的录制回放只满足 `real_data_ready` 的数据集验证部分。逐动作 E3 `real_account` 证据、有效资产授权、当前试点范围和字段真实来源仍由已有门禁独立判断。

## 2. 事实、判断与范围

### 2.1 已知事实

- TikTok 模块 PRD 19.1 要求为联盟、订单、物流、视频和 GMV 建立字段字典、来源优先级以及 Mock 或录制回放。
- PRD 19.2 的“至少 30 条真实或脱敏历史记录完成对照”属于 P3-B1 退出条件，不是 P3-B0 录制入口的退出条件。
- 当前 `tiktok_data_validation_runs` 只允许 `mode='mock'`，并用数据库约束强制 `real_data_ready_snapshot=false`。
- 当前共享校验逻辑已经覆盖必需字段与类型、业务键唯一性、关联、金额币种、时间窗口、新鲜度、PID/商品一致性和来源授权。
- 当前真实授权与逐动作 E3 尚未独立验证，因此录制回放通过后仍可能保持 `real_data_ready=false`。

### 2.2 设计判断

- 复用现有追加写运行历史比新建一套录制导入历史更简单，也能保持一种审计语义。
- 直接实时拉取 TikTok API 会把本功能绑定到尚未验证的权限、网络和账号状态，不适合作为本阶段入口。
- 浏览器文件选择比服务器文件路径更适合业务管理员；服务必须自行执行大小、结构和敏感字段校验，不能信任浏览器预检。
- 录制数据的新鲜度必须相对回放基准 `replay_as_of` 计算。相对当前时间计算会把合法历史快照误判为陈旧。

### 2.3 不在范围内

- 不实现 P3-B1 的看板、样品/履约事实表、指标字典或 30 条业务对照流程。
- 不调用 TikTok、FastMoss、领星、达密、飞书或其他外部系统。
- 不增加任何外部写入、消息发送、付费生成或自动化能力。
- 不自动创建、升级或复制 E3 能力证据。
- 不保存可供再次下载的原始文件或业务记录。

## 3. 方案比较与选择

### 3.1 扩展现有追加写运行表（采用）

Mock 与 recorded 共享运行历史、校验结果、权限和就绪判断。新增字段通过条件约束只在 recorded 模式出现，避免 Mock 伪装为真实数据验证。

### 3.2 新建独立录制导入表（不采用）

独立表可隔离审批字段，但会重复运行状态、检查结果、RLS、追加写保护、查询排序和 UI 模型。当前没有第二类生命周期需要独立聚合根。

### 3.3 直接调用真实 Connector（不采用）

真实 Connector 最终仍需建设，但当前逐动作 E3、scope 和有效资产授权不足。把它作为本功能前置会让可验证的录制路径被外部阻塞，并可能错误扩大权限结论。

## 4. 输入合约

请求使用 `Content-Type: application/json`。前端读取用户选择的 JSON 文件并把 `dataset` 与界面填写的审批元数据组合成一次请求。文件名不进入请求。

```json
{
  "scope_revision": 3,
  "source_label": "approved-order-export",
  "approval_ref": "APPROVAL-2026-09-22-01",
  "approved_by_user_id": "user_data_owner",
  "approved_at": "2026-09-22T02:00:00Z",
  "approval_valid_until": "2026-10-22T02:00:00Z",
  "data_period_start": "2026-08-01T00:00:00Z",
  "data_period_end": "2026-08-31T23:59:59Z",
  "replay_as_of": "2026-09-01T02:00:00Z",
  "sanitization_attested": true,
  "dataset": {
    "samples": [],
    "orders": [],
    "logistics": [],
    "videos": [],
    "attribution": [],
    "gmv": []
  }
}
```

### 4.1 请求大小与数量

- 服务按字节流读取请求，硬上限为 2 MiB；超过上限立即返回 413，不继续读取或解析。
- 六个集合每个最多 500 条，总数最多 3,000 条。
- 字符串值和审批文本分别设置明确长度上限，防止超大嵌套值绕过记录数限制。
- JSON 最大嵌套深度固定；本合约只允许顶层对象、六个数组和扁平记录对象。

### 4.2 集合与字段

仅允许 `samples`、`orders`、`logistics`、`videos`、`attribution`、`gmv` 六个集合。记录只允许 `p3-b0.v1` 当前 30 个字段在其对应集合中的叶字段名。所有 Pydantic 模型使用 `extra='forbid'`。

当前契约中存在 required 且未标记 `not_applicable` 的领域必须至少有一条记录；空集合产生 `required_collection_empty`，防止“检查 0 条却通过”。

### 4.3 脱敏边界

递归扫描键名并拒绝明显敏感字段，包括姓名、电话、邮箱、地址、Token、Cookie、Secret、密码、OAuth code/state 和原始授权载荷。比较使用大小写折叠和非字母数字归一化，防止简单变体绕过。

业务 ID 允许存在，但输入方必须先将其转换为稳定假名，以保持集合间关联。系统无法可靠判断任意字符串值是否包含个人信息，因此管理员必须勾选固定版本的脱敏声明；该限制在 UI 和运行手册中明确说明。

原始 JSON 只存在于请求处理内存中。代码不得记录请求体、原始值、文件名或解析异常片段。验证完成或失败后释放引用；前端提交后清除文件对象和解析后的 dataset，保留非敏感审批表单便于修正。

## 5. 审批和时间规则

审批字段均为 recorded 模式必需字段：

- `source_label`：安全的来源说明，不得包含路径、URL 查询、账号或秘密。
- `approval_ref`：内部审批编号，不得保存审批正文或外部授权载荷。
- `approved_by_user_id`：同租户 active 用户，且不得等于 `started_by_user_id`。
- `approved_at`、`approval_valid_until`：审批时间与到期时间。
- `data_period_start`、`data_period_end`：业务数据覆盖周期。
- `replay_as_of`：提取/快照完成后用于历史新鲜度计算的基准。
- `sanitization_attested`：必须为 true；运行记录保存固定声明版本 `p3-b0-recorded.v1`，不保存自由文本。

时间顺序必须满足：

```text
data_period_start <= data_period_end <= replay_as_of <= approved_at <= now < approval_valid_until
```

服务端允许极小的时钟漂移，但不允许未来审批。所有时间必须包含时区并归一到 UTC；无时区值直接拒绝。

## 6. 持久化与数据库约束

新增迁移扩展 `tiktok_data_validation_runs`，增加：

- `source_label`
- `approval_ref`
- `approved_by_user_id`
- `approved_at`
- `approval_valid_until`
- `data_period_start`
- `data_period_end`
- `replay_as_of`
- `scope_id`
- `scope_revision`
- `contract_digest`
- `attestation_version`

数据库调整如下：

1. `mode` 约束改为 `mock | recorded`。
2. recorded 行必须填写全部录制字段；mock 行必须保持这些字段为 NULL。
3. recorded 行要求审批人与执行人不同、scope revision 大于 0、时间顺序合法。
4. `real_data_ready_snapshot=true` 只允许出现在 `mode='recorded' AND status='passed'` 的行。
5. 审批人使用 `(tenant_id, approved_by_user_id)` 同租户外键。
6. scope 使用 `(tenant_id, scope_id)` 同租户外键；若范围表缺少所需唯一键，迁移同时补充 `(tenant_id, id)` 唯一约束。
7. 运行表继续 FORCE RLS，并继续由现有触发器禁止 UPDATE 和 DELETE。
8. 回滚迁移先恢复所有行可满足的旧约束；若存在 recorded 行，回滚必须明确失败，避免静默丢失审计证据。

数据库不增加 dataset JSON、文件 blob、原始请求、文件名或值级错误字段。

## 7. 契约摘要与失效

`contract_digest` 使用当前租户 30 个字段契约的规范化 JSON 计算 SHA-256。参与摘要的字段包括：

- field code、domain、data type、required
- business key、freshness SLA、missing behavior、status、revision
- 按 priority 和 source key 排序后的来源选择、usage、decision、authorization state

标签、创建时间和显示顺序不影响摘要。规范化使用 UTF-8、稳定键排序和紧凑 JSON。

录制运行保存当前 `scope_id`、`scope_revision` 和 `contract_digest`。任何范围 revision 或参与摘要的字段契约变化都会让旧运行变为 stale，必须重新回放。

## 8. 校验流程

1. 鉴权并确认租户管理员。
2. 流式读取请求并执行 2 MiB 限制。
3. 解析 JSON；执行严格结构、数量、深度和敏感字段检查。
4. 校验当前 US active 试点范围及客户端提交的 scope revision。
5. 校验审批人、声明和时间顺序。
6. 读取当前 30 个字段契约并计算 contract digest。
7. 使用 `replay_as_of` 调用泛化后的确定性数据校验器。
8. 在同一事务中追加 recorded 运行摘要并计算就绪快照。
9. 返回安全响应；无论成功或失败均清除请求数据引用。

现有 `validate_mock_dataset` 泛化为清楚命名的共享校验入口，并保留兼容包装器或等价兼容路径，避免破坏已有测试和调用者。

## 9. 运行结果与失败语义

### 9.1 不创建运行记录

以下输入在进入数据质量检查前失败，不创建 run：

- 413：请求超过大小限制。
- 415：不是 JSON content type。
- 422：JSON 无法解析、结构/字段/数量/深度不合法、发现敏感字段、声明缺失或审批时间非法。
- 403：当前用户不是租户管理员。
- 404：scope 或审批用户不属于当前租户或不是 active。
- 409：scope revision 已变化，或目录/契约不完整。

错误响应只返回稳定错误代码和通用说明，不包含文件内容、值、路径或解析片段。

### 9.2 创建追加写记录

结构和审批通过后执行数据质量检查：

- 有质量问题：保存 `mode='recorded'`、`status='failed'` 的摘要。
- 无质量问题：保存 `status='passed'` 的摘要。
- 检查与问题继续只包含 code、field code、severity、detail 和计数，不包含原值或记录索引。
- 数据集摘要由目录版本和规范化 dataset 计算；摘要不可作为再次下载数据的凭据。

## 10. 就绪语义

工作区按创建时间选择最新 recorded 运行，不从更旧的成功记录回退：

- 无 recorded 运行：`recorded_or_real_validation_missing`。
- 最新运行失败：`latest_recorded_validation_failed`。
- scope ID/revision 不匹配：`recorded_validation_scope_stale`。
- contract digest 不匹配：`recorded_validation_contract_stale`。
- 审批已过期：`recorded_validation_approval_expired`。
- 目录版本不匹配：`recorded_validation_catalog_stale`。

只有最新 recorded 运行通过且仍匹配当前范围、目录、契约与审批有效期时，数据集验证部分才满足。`real_data_ready` 仍要求：

- `workbench_ready=true`
- 必需字段拥有可用真实来源
- 每个必需读取动作有独立、未过期且主体/资产/scope 匹配的 E3 `real_account`
- 有效、资产关联的官方授权
- 最新 recorded 运行有效

录制回放不会创建或修改 capability evidence。通过 recorded 回放但缺 E3 时，界面必须继续显示 E3 blocker。

## 11. API

新增：

```text
POST /api/enterprise/tiktok/data-validation/runs/recorded
```

该路由只允许租户管理员。服务手工读取有限字节流后再交给严格请求模型，避免框架在执行大小判断前无界解析请求体。

响应复用扩展后的 `TikTokDataValidationRunRead`，recorded 行额外返回安全审批字段和 stale 状态所需摘要。Mock 行对应字段为 null。响应不返回文件名、dataset、请求体或任何原始记录。

现有六个数据验证路由保持兼容；工作区读取继续允许同租户成员。

## 12. 前端体验

新增独立组件 `TikTokRecordedValidationForm`，由现有数据验证面板加载，避免继续扩大单文件职责。

管理员流程：

1. 选择 `.json` 文件；客户端先检查 2 MiB 和 JSON 基本结构。
2. 填写来源、审批编号、审批人、审批时间/到期时间、数据周期和 replay time。
3. 勾选固定脱敏声明。
4. 提交后展示结构结果、八类数据检查、运行状态及最新 readiness blockers。
5. 无论成功或失败均清除文件对象和 dataset；非敏感审批字段可保留。

文件名仅在浏览器当前组件中显示，不发送到服务，不写入 localStorage/sessionStorage。页面代码不得 `console.log` 文件、dataset 或完整错误对象。

成员只看到安全运行摘要和当前阻塞项，不渲染文件控件、审批表单或提交按钮。

## 13. 权限与安全

- 管理员写、同租户成员读，沿用现有权限助手。
- API、服务和数据库分别执行租户边界；不能用应用层检查替代 RLS。
- 同租户审批人外键与服务校验同时存在。
- 禁止外部网络调用和外部写入。
- 不修改冻结的 TikTok 外部写面；新增路由需要纳入现有路由审计清单，因为它是本地写入面。
- 日志、异常、测试 fixture 和截图均使用合成假名数据。

## 14. 代码边界

计划涉及：

- `src/backend/app/db/models.py`：扩展运行模型。
- `src/backend/migrations/`：新增可回滚 migration。
- `src/backend/app/tiktok/recorded_validation.py`：有限读取后的结构、安全和审批输入处理。
- `src/backend/app/tiktok/data_validation.py`：共享校验、持久化和 readiness 集成。
- `src/backend/app/tiktok/schema.py`：严格请求/响应模型。
- `src/backend/app/api/tiktok.py`：recorded 路由和安全错误映射。
- `src/frontend-enterprise/src/pages/tiktok/TikTokRecordedValidationForm.tsx`：管理员表单与摘要。
- `TikTokDataValidationPanel.tsx`：装配子组件和刷新工作区。
- `src/tests/backend/`、`src/tests/frontend/`：聚焦回归。
- `docs/`：运行手册、项目记忆、交接和验收记录。

不进行与该功能无关的模型或前端重构。

## 15. 测试与验收

### 15.1 后端

- 2 MiB 边界、非 JSON、非法 JSON、嵌套/数量超限。
- 未知集合、未知字段、敏感键变体和空 required 集合。
- 时区缺失、时间顺序、未来审批和过期审批。
- 审批人与执行人分离、inactive/跨租户审批人。
- admin/member 权限、scope revision 冲突和目录不完整。
- dataset/contract digest 确定性且响应/数据库无原值。
- recorded 成功与失败追加写；最新失败覆盖旧成功。
- scope、contract、catalog、approval 变化使运行失效。
- Mock 永不产生真实就绪；recorded 也不能绕过 E3 和授权。
- 双租户使用相同业务键仍完全隔离。

### 15.2 数据库

- 正向/回滚 migration 静态检查。
- PostgreSQL 可用时验证条件约束、同租户外键、FORCE RLS 和 UPDATE/DELETE 拒绝。
- 存在 recorded 行时回滚明确失败，不静默丢失证据。

### 15.3 前端

- 管理员文件与审批表单、客户端大小检查和声明门禁。
- 提交后清除文件/dataset，文件名不进入请求。
- 422/409/质量失败保留非敏感审批字段并显示稳定错误。
- 成员只读且没有文件/提交控件。
- 最新 run 和 E3/授权 blocker 分开展示。

### 15.4 浏览器验收

- 管理员运行一份合成脱敏成功数据和一份质量失败数据。
- 确认最新失败不会由更旧成功覆盖。
- 成员确认只读。
- 检查网络响应、页面和截图中没有原始业务值、文件名、Token、Cookie 或个人信息。

### 15.5 仓库门禁

- 完整 TikTok 后端矩阵与新增录制测试。
- 测试布局检查和变更 Python Ruff。
- 完整前端 Vitest、类型检查、i18n、配置检查和生产构建。
- 全后端非绿基线继续单独记录，不把既有失败描述为本功能通过。

## 16. 完成条件

本功能完成需要同时满足：

1. 管理员能提交符合合约的脱敏录制数据并得到追加写安全摘要。
2. 非法或敏感输入在保存运行前被拒绝。
3. 质量失败被审计但不满足数据集门禁。
4. 当前范围或契约变化后旧录制运行自动失效。
5. 成员只能读取安全摘要。
6. Mock、录制回放和 E3/授权门禁保持独立。
7. 所有聚焦自动化、前端门禁和双角色浏览器验收通过。

完成这些条件不等于 P3-B1 完成，也不等于生产数据已就绪。`real_data_ready` 只有在已有 E3 和授权条件也真实满足时才可为 true。
