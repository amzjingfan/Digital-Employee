# Joukir TikTok Skill Pack 来源与许可证清单

## 审计范围

本清单覆盖 `registry.json` 中的 12 个生产候选 Skill。每个 Skill 的 `manifest.json` 和本目录的 `inventory.json` 必须同时通过自动校验后，才允许进入 AgentRelease 预检。

## 统一结论

- 来源：Joukir 内部原创流程方法与 Schema，使用 `internal://joukir/skills/<skill_id>` 标识。
- 许可证：`Joukir-internal-methods`，不包含第三方代码、第三方提示词或第三方数据集。
- 依赖：运行时依赖由平台提供；Skill 包自身不声明外部运行时依赖。
- Clipcat：不是硬依赖，也不作为生产执行前置条件。
- 当前状态：`approved_seed` 仅表示已通过本地种子和安全门禁，不等于业务负责人完成生产发布审批。

逐 Skill 的来源、许可证、第三方内容、依赖和审核状态见同目录 `inventory.json`。
