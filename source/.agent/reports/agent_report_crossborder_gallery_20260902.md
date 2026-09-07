# StaffDeck 七岗位开放广场发布验证报告

## 结论

- 时间：2026-09-02 14:00:32 +08:00
- 租户：`tenant_demo`
- 结果：七个跨境生产只读岗位已发布到开放广场，并通过岗位级可见性控制、数据库幂等部署、真实 HTTP 工具调用和任务快照验证。
- 正式独立发布结论仍为 `INCONCLUSIVE`：源码副本没有 Git commit/tree，不能形成不可变版本签署。

## 广场岗位

- 运营主管
- 跨境售后专员
- Listing 合规专员
- 物流异常专员
- 广告巡检专员
- 美工设计
- 采购专员

每个岗位的广场元数据包含：`gallery_category=跨境电商`、`gallery_template_kind=reviewed_production_role`，以及“生产只读、岗位授权、已审核”标识。

## 可见性与使用规则

- 平台管理员：可见和使用全部七个岗位。
- 运营主管：可见和使用全部七个岗位。
- 其他岗位用户：只能看见并使用与本人 Casdoor `business_role` 一致的岗位。
- 限制覆盖企业端岗位列表、聊天端选择、公开 API 凭据解析、公开 Gallery API 和定时任务入口。
- 既有且未设置 `gallery_allowed_business_roles` 的广场员工保持原有租户级可见行为，避免破坏兼容性。

## 验证证据

- 相关权限、能力包和公开 API 测试：`22 passed in 4.95s`。
- 扩展回归首轮：`52 passed in 10.02s`。
- 一项既有异步 Trace 测试在第二次组合回归中偶发失败，单独重跑为 `1 passed`；该测试不涉及广场、岗位或权限代码。
- Ruff `E9/F/I`：通过。
- Python `compileall`：通过。
- 前端 `tsc -b && vite build`：通过，仅有既有的大 chunk 性能告警。
- 七个岗位数据库 provision：成功且幂等。
- 七个岗位 verifier：`gallery_published=true`、`gallery_role_gate_verified=true`、`mapped_supervisor_visibility_verified=true`；数据库中已映射的运营主管用户可见全部七个岗位。
- 七个岗位真实工具调用：全部通过。
- 七个岗位任务快照：每个均为 `SOP=1、knowledge=1、tools=1`，摘要复算全部通过。
- StaffDeck supervisor/app 正常，5173 端口监听，健康检查通过。

## 当前 SHA-256

```text
backend/app/security/permissions.py 844a8a7f4ca0ece60f000a80e9e0df1c2423e12680fb1926d8a0925a686050aa
backend/app/api/agents.py 927cdbeb0a5e3c89ea5130e791b93305102c00f203768ea6a0833a985751deea
backend/app/api/chat.py 5f017d2e237e6881c1720f857ab5b49198bf595b1d23766abf5573225787ad47
backend/app/public_api/auth.py 592feadcc98652b988f59f9ed57441c91f263412faf92acee6af5a923b369c2c
backend/app/scheduled_tasks/service.py ce0bbe5f8243e7b87d91587734f725c79002dc7f41934fb56bfe1f11376abb70
backend/app/crossborder/capability_pack.py 76faa3260b9c1c51f50990cd3c494d6f768f567530554991b64dcafaa9fe9c58
backend/scripts/verify_crossborder_production_capabilities.py bceba4ce49e802251c177aa8e81d36c956572213de9a3788e645f0e6ae704d93
backend/tests/test_crossborder_capability_pack.py 352ab773fb37bf608c97f48a7ff0f4322517b5d35fde1c171c054b9700748ad3
backend/tests/test_agent_permissions.py bb88cf7ba64e21984c2991cc3545c21040e824bbf2d65404de4c731959d125f7
backend/tests/test_public_api_v1.py 0c3fda194e2dc5d2c756998897fdb53ed911fd3315444a349760c869111a3ea9
D:/saas/research/crossborder-digital-workforce-prd-2026.md 1edf335031681cfe3e2326ff5bf5339e44e1dc9379481e431c7455eba3e32822
```

以上哈希是当前工作副本证据，不能替代 Git commit/tree 和独立审核签名。
