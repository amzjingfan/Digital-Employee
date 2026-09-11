# 站外渠道运营并行分支开发日志

## 2026-09-08 · 功能 26 Offsite-P0 渠道资产底座（开始）

- 目标：在 `prd/offsite-channels` 分支交付功能 26 的 P0 垂直切片，闭环渠道资产创建、追加式证据、证据新鲜度/缺口判断、人工复核分层和审计回放。
- 范围：只修改 `D:/saas/worktrees/joukir-offsite/source`；新增独立 `offsite` 后端域、PostgreSQL 正向/回滚迁移、聚焦测试及业务闭环页面入口。
- 现状审计：已有 `crossborder` 售后/物流、`creator_account`/`partner_account` 资源类型、店铺资源授权与统一高风险审批/执行模型；尚无 `ChannelAsset`、`ChannelEvidence`、`DealProposal/ProfitGateDecision` 或达人组合领域实现。
- 选择依据：功能 26 的资产底座属于 OFF-M0/Offsite-P0，是功能 21 匹配、23 利润门控及后续 22/24/25 的共同证据依赖；本步不提前实现 P1 自动维护。
- 安全边界：资产必须绑定已授权店铺范围；证据追加写、带来源和有效期；证据不足或过期时执行资格固定为 `blocked`；页面和 API 不提供付款、发布、触达或其他外部副作用入口。
- 已知阻塞：当前基线没有独立 Brand/BrandMembership 模型，先用非空 `brand_key` 加已授权 `store_resource_id` 双重限定，并把正式品牌成员关系列为后续平台集成风险；真实渠道连接器与平台 PoC 未提供，本切片只接收人工或已授权导入证据，不伪造联网验证。

## 2026-09-08 · 功能 26 Offsite-P0 渠道资产底座（完成）

- 交付：新增 `OffsiteChannelAsset`、`OffsiteChannelEvidence`、`OffsiteChannelEvent`，稳定接口前缀为 `/api/v1/offsite`；支持店铺范围内的资产创建/幂等回放、列表/详情、追加证据、主管状态/层级复核和审计事件。
- 证据门禁：按资产类型计算必需证据、缺口和到期状态；`human_judgment` 只保留为审计上下文，不能代替来源事实/声明；已验证状态的证据过期后，对外有效状态立即降为 `needs_review`，资格固定为 `blocked`。
- 数据与安全：新实体显式携带 tenant/brand 范围，子表使用 `(tenant_id, brand_key, asset_id)` 同范围外键；PostgreSQL 迁移启用并强制 RLS，证据/事件用触发器禁止更新或删除；URL 拒绝凭据/敏感查询项，证据 JSON 拒绝明文联系方式或秘密。
- 页面：在跨境业务闭环中为运营主管、TikTok BD 和 TAP 岗位增加“站外渠道资产”入口，展示层级/状态、新鲜度、证据缺口、追加式时间线和明确的无外部动作边界；列表只返回证据摘要，详情按需加载完整时间线。
- 客户端修复：带 `Idempotency-Key` 的 POST 现在会与认证头及 `Content-Type` 正确合并，不再覆盖公共请求头。
- 验证：`pytest -q tests/test_offsite_channel_assets.py tests/test_business_resources.py tests/test_authorization.py tests/test_crossborder_casework.py` 为 23 passed；Ruff `I,E9,F` 通过；`compileall` 与主应用 offsite 路由挂载检查通过；Vitest 全量为 64 files / 269 tests passed；`npm run build` 成功（仅保留既有大 chunk 警告）。
- 修复回路：首次组件测试暴露缺少 `I18nProvider` 测试包装及不精确的文本查询，修复后聚焦测试与全量前端测试均通过；首次主路由断言不兼容 FastAPI 惰性 `_IncludedRouter`，改为检查其 `original_router.prefix` 后通过，应用导入本身从未失败。
- 未纳入本切片：维护任务生成器/去重、关系网络、实验/经济性、真实连接器、联系人加密存储及任何付款/发布/触达 Operation；它们仍属于后续 Offsite-P0/P1 工作，不应因本次资产底座交付被视为完成。
- 集成风险：基线仍缺正式 Brand/BrandMembership；当前以 `brand_key` 数据约束叠加已授权店铺范围做过渡，接入平台品牌成员关系前不得放宽店铺授权或宣称已完成品牌级身份治理。
