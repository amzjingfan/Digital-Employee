# StaffDeck 七岗位生产只读能力包审计报告

> 版本说明：本报告的文件哈希记录的是首次能力包审核状态。七岗位随后增加了受业务角色约束的开放广场发布能力；最新代码、数据库状态和哈希以 `agent_report_crossborder_gallery_20260902.md` 为准。

## 1. 审计结论

- 审计对象：`staffdeck.crossborder.production-readonly` `1.0.0`
- 租户：`tenant_demo`
- 执行时间：2026-09-02 11:22:28 +08:00（2026-09-02T03:22:28Z）
- 工程验证结论：通过。七个岗位的 SOP、知识库、GET-only 工具、私有绑定、M2M 身份、真实 HTTP 调用和任务版本快照均符合当前只读影子运行门槛。
- 正式独立发布结论：`INCONCLUSIVE`。工作副本没有 `.git/`，无法把结果绑定到不可变 commit/tree；本轮也没有独立于实现者的审核人签署。因此本报告不能替代正式生产写权限审批或发布签字。
- 允许范围：本地生产同构环境中的只读巡检、影子运行、人工复核和审批建议。
- 不允许范围：退款、Listing 发布/修改、物流改路、广告修改、素材发布、采购下单或付款等外部写操作。

## 2. 用户授权与范围

用户明确要求：根据已安装相关 skills 与 GitHub 优秀项目，设计、开发并绑定七个岗位经过审核的生产 SOP、知识库和工具。

本轮仅修改 StaffDeck 本地代码、文档和 `tenant_demo` 中对应能力资源；没有调用任何真实电商、广告、物流或供应商外部写接口，也没有改变审批矩阵或授予生产写权限。

## 3. 设计依据

### 3.1 已安装 skills

- `agent-workflow`：用于任务状态、失败恢复、幂等与可审计执行设计。
- `sellerspace-amazon-ops-cadence`：用于运营主管日报、周报、跟进合同和多岗位节奏。
- `amazon-return-reduction`：用于售后 RCA、Listing/包装/物流联动。
- `amazon-product-compliance`：用于市场、类目、证据矩阵和发布前合规门禁。
- `amazon-inventory-management`：用于物流、库存和补货上下文，避免无 SLA/交期时编造结论。
- `amazon-advertising-strategy`：用于广告指标口径、归因窗口、毛利和库存约束。
- `amazon-listing-images`：用于素材真实性、渠道要求、权利证明和版本测试。
- `amazon-wholesale-sourcing`：用于供应商证据、MOQ、到岸成本、交期和采购边界。
- `independent-verification`：用于信任边界审查、证据记录和诚实的发布结论。

### 3.2 GitHub 一手参考

- Amazon Selling Partner API Models：字段、枚举和 OpenAPI 契约参考。
- Amazon Selling Partner API Samples：集成流程、样例边界和生产加固参考。
- Amazon Ads Advanced Tools Docs：广告 API、报告和 bulk 契约参考。
- OpenMetadata：来源、所有权、新鲜度和可信度元数据模式。
- Langfuse：Trace、评测数据集和版本回归模式。

这些项目只用于架构和契约参考；平台政策、类目要求、广告阈值、SLA、毛利和采购参数都没有被当作通用生产常量。

## 4. 已实施能力

| 岗位 | SOP/技能 | 知识库重点 | 工具 |
|---|---|---|---|
| 运营主管 | `cb_ops_review_v1` | 数据质量、汇总口径、运营节奏、跟进合同 | `crossborder.operations_supervisor.context_read` |
| 售后专员 | `cb_after_sales_triage_v1` | 案件证据、退货 RCA、联动和处置边界 | `crossborder.after_sales_specialist.context_read` |
| Listing 合规专员 | `cb_listing_compliance_v1` | 市场/类目、证据矩阵、内容一致性 | `crossborder.listing_compliance_specialist.context_read` |
| 物流异常专员 | `cb_logistics_exception_v1` | 事件时间线、SLA、库存联动和升级路径 | `crossborder.logistics_exception_specialist.context_read` |
| 广告巡检专员 | `cb_advertising_inspection_v1` | 指标定义、可比性、阈值治理和决策上下文 | `crossborder.advertising_inspection_specialist.context_read` |
| 美工设计 | `cb_creative_review_v1` | 真实性、渠道要求、权利证明和素材测试 | `crossborder.designer.context_read` |
| 采购专员 | `cb_procurement_assessment_v1` | 供应商证据、条款、到岸成本、交期和合规 | `crossborder.procurement_specialist.context_read` |

每个岗位包含一个已发布私有 SOP、一个已发布知识库版本、六个带来源治理的知识块、一个已批准 GET-only 工具、一个活动技能分支和一个活动知识分支。任务启动时把这三类资源固定进不可变快照并保存摘要。

## 5. 安全与治理控制

- 请求必须通过租户、数字员工、岗位、技能分支、SOP allowlist、工具绑定和资源范围的交集校验。
- 生产只读工具和 mock 接口使用不同 HMAC 作用域；mock 凭证不能调用生产只读端点。
- 仅精确匹配配置的 StaffDeck 内部 origin 和路径时才注入凭证；外部同路径 URL 不注入内部凭证。
- 租户、数字员工、技能和工具上下文由执行器覆盖，调用者提供的伪造 Header 不被信任。
- 缺少可信上下文时失败关闭；未认证、错误令牌、跨岗位和跨租户访问均拒绝。
- 输出为字段白名单，不返回业务资源 `metadata_json`、审批 `payload_json` 或凭据字段。
- 检索文本视为不可信输入，不能改变权限、读取凭据或绕过审批。
- 同版本重复部署幂等；若同一 `1.0.0` 内容漂移则拒绝覆盖，必须升版。
- 所有高风险外部动作只生成审批建议，能力包元数据明确记录 `live_write_approval=not_granted`。

## 6. 验证证据

### 6.1 自动化回归

命令：

```text
python -m pytest -q tests/test_crossborder_capability_pack.py tests/test_crossborder_tools.py tests/test_tool_executor.py tests/test_work_tasks.py tests/test_work_task_m2m.py tests/test_work_task_execution.py tests/test_work_task_snapshots.py tests/test_authorization.py tests/test_business_resources.py
```

结果：`44 passed in 9.23s`。

覆盖内容包括能力包幂等性、版本冲突、岗位绑定、跨岗位拒绝、跨租户拒绝、Header 覆盖、外部 origin 拒绝、mock/生产令牌隔离、任务执行、M2M、快照摘要、授权和业务资源范围。

### 6.2 静态与构建检查

- Ruff：通过。
- Python `compileall`：通过。
- 前端 `tsc -b && vite build`：通过；仅存在 Vite 大 chunk 性能告警，不影响本能力包正确性。
- 敏感信息特征扫描：通过，变更的生产代码和脚本未发现常见 API Key、私钥或长 Bearer Token 字面量。

### 6.3 PostgreSQL 与真实 HTTP 验证

- provision 脚本在 `tenant_demo` 上重复执行成功，证明当前数据库状态与 `1.0.0` 声明一致且部署幂等。
- 七个岗位的工具真实 HTTP 调用均为 `passed`。
- 七个岗位的临时任务启动快照均为 `sops=1, knowledge=1, tools=1`。
- 七个快照摘要重新计算均为 `true`。
- 七个岗位均有独立、活动的 Casdoor M2M 身份。
- 无令牌与错误令牌访问生产工具端点均返回 HTTP 401。
- StaffDeck 进程和 supervisor 正常，端口 5173 正在监听，`/api/health` 正常。

### 6.4 发现与修复

1. 首次数据库验证发现工具 URL 使用 `127.0.0.1`，而运行时信任 origin 固定为 `localhost`，调用返回 401。根因是一次手工 provision 参数覆盖；在没有发布任务快照前，把七个受管工具 URL 修正为运行时规范化 base URL。随后默认参数幂等部署与七岗位真实调用全部通过。
2. 安全审查发现生产只读端点最初复用 mock 的内部派生令牌。已拆分 HMAC 作用域，并增加“mock 令牌调用生产端点必须失败”的回归测试。

## 7. 文件清单与 SHA-256

```text
backend/app/security/internal_service.py 481d75c70192235305bf559a5f3f50ee60199e27c5ae3feac0006739c737ecd3
backend/app/tools/tool_executor.py 74c6342ee22ce626d245b1a2ed214a361c53021462d1d544b7b0ec74f5a94710
backend/app/api/crossborder_tools.py 1e23076a9200f0d48e1934225b374fdcf33ff48a9b1238aec9a40ddd194e851b
backend/app/crossborder/__init__.py a03240ce53d21f1e952591df05fa283f274d2d7c17bb8ac32caf7812a5652b1c
backend/app/crossborder/capability_pack.py f5a4bb57f0c0b1354e8fa2c943d85340acc624face639ef420cafa657cedbf99
backend/app/main.py f504fcab04f3a1987db89fe2c1cb0518e1ae35f726dc752e2fe67d76b2043acf
backend/scripts/provision_crossborder_production_capabilities.py 633a637f045b3f35959d620df22bd06e3608e938dfeb5d6bf635b8025335c0ff
backend/scripts/verify_crossborder_production_capabilities.py d6b17cea804cd7f73aba15215ea2e2a06fa86ec2abe0705bc6e628dba20aa842
backend/tests/test_crossborder_capability_pack.py 823268105894cbd0f18ef31676899277870a05258e0631a79ef61c74449a65b4
backend/tests/test_crossborder_tools.py 66900acb78bc5187c82f06f3643064456da3cf4e2855b0099b064b0f06f9f1e0
backend/tests/test_tool_executor.py bc91ff4715e98ca2dc2dba7b62cb83cad1e436372e478140f11105b0fdc8afae
tmp/creative-production-capability-pack.md 27b098480d99a68073fb6469067b5938e47b61d46e8fc08f28099251bd9d4445
D:/saas/research/crossborder-digital-workforce-prd-2026.md fadbdc007a3b730e0b67f05a70099942281b6256403bdd5bb902a40f8f428db2
```

注意：以上哈希只能证明审计时文件内容，不能替代 Git commit/tree、受保护分支和独立审核签名。

## 8. 回滚与后续门槛

- 立即回滚：停用七个受管工具或对应数字员工/分支；工具本身无外部写副作用。
- 数据回滚：保留历史任务和快照用于审计，通过新版本修正能力包；不覆盖已启动任务的不可变快照。
- 正式生产前：把源码纳入 Git，固定 commit/tree；在隔离环境重放相同命令；由独立审核人签署验证结果；补充业务负责人对公司政策、平台规则、SLA、毛利阈值、审批矩阵和数据源新鲜度的验收。
- 任何外部写能力必须作为新版本单独设计，加入幂等键、dry-run、最小 scope、金额/幅度限额、双人审批、对账与补偿流程后重新审核。
