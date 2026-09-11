from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BusinessRoleDefinition:
    key: str
    label: str
    casdoor_group: str
    description: str


BUSINESS_ROLES = (
    BusinessRoleDefinition(
        "operations_supervisor",
        "运营主管",
        "九头蛇/staffdeck-jiutoushe-operations-supervisor",
        "汇总各岗位结果，管理协作流程并生成日报、周报。",
    ),
    BusinessRoleDefinition(
        "after_sales_specialist",
        "跨境售后专员",
        "九头蛇/staffdeck-jiutoushe-after-sales",
        "处理客服、退换货、退款和售后工单。",
    ),
    BusinessRoleDefinition(
        "listing_compliance_specialist",
        "Listing 合规专员",
        "九头蛇/staffdeck-jiutoushe-listing-compliance",
        "检查商品内容、知识资料和平台规则。",
    ),
    BusinessRoleDefinition(
        "logistics_exception_specialist",
        "物流异常专员",
        "九头蛇/staffdeck-jiutoushe-logistics-exception",
        "监控履约、物流轨迹和异常任务。",
    ),
    BusinessRoleDefinition(
        "advertising_inspection_specialist",
        "广告巡检专员",
        "九头蛇/staffdeck-jiutoushe-advertising-inspection",
        "巡检广告数据并提交操作建议。",
    ),
    BusinessRoleDefinition(
        "designer",
        "美工设计",
        "九头蛇/staffdeck-jiutoushe-designer",
        "维护商品视觉素材和设计知识资产。",
    ),
    BusinessRoleDefinition(
        "procurement_specialist",
        "采购专员",
        "九头蛇/staffdeck-jiutoushe-procurement",
        "处理供应商、采购资料和采购协作任务。",
    ),
    BusinessRoleDefinition(
        "tiktok_bd_specialist",
        "TikTok BD 专员",
        "joukir/tiktok-bd",
        "负责 TikTok 达人、品牌和机构商务拓展。",
    ),
    BusinessRoleDefinition(
        "tiktok_content_specialist",
        "TikTok 短视频专员",
        "joukir/tiktok-content",
        "负责短视频选题、脚本、素材审核和发布建议。",
    ),
    BusinessRoleDefinition(
        "tiktok_shop_operator",
        "TikTok 小店运营",
        "joukir/tiktok-shop",
        "负责 TikTok Shop 商品、订单和店铺经营分析。",
    ),
    BusinessRoleDefinition(
        "tiktok_media_buyer",
        "TikTok 投流专员",
        "joukir/tiktok-media",
        "负责广告账户巡检、预算和投放优化建议。",
    ),
    BusinessRoleDefinition(
        "tiktok_tap_manager",
        "TikTok TAP 专员",
        "joukir/tiktok-tap",
        "负责联盟达人、TAP 机构协作和佣金分析。",
    ),
    BusinessRoleDefinition(
        "tiktok_live_operator",
        "TikTok 直播专员",
        "joukir/tiktok-live",
        "负责直播排期、直播间数据和复盘任务。",
    ),
)

BUSINESS_ROLE_BY_KEY = {role.key: role for role in BUSINESS_ROLES}
DEFAULT_GROUP_ROLE_MAPPING = {role.casdoor_group: role.key for role in BUSINESS_ROLES}


class GroupRoleMappingError(ValueError):
    pass


def parse_group_role_mapping(value: str) -> dict[str, str]:
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise GroupRoleMappingError("OIDC group role mapping is invalid JSON") from exc
    if not isinstance(raw, dict):
        raise GroupRoleMappingError("OIDC group role mapping must be an object")
    mapping: dict[str, str] = {}
    for group, role in raw.items():
        group_name = str(group).strip()
        role_key = str(role).strip()
        if not group_name or role_key not in BUSINESS_ROLE_BY_KEY:
            raise GroupRoleMappingError("OIDC group role mapping contains an unknown role")
        mapping[group_name] = role_key
    return mapping


def normalized_group_claim(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise GroupRoleMappingError("OIDC groups claim must be an array")
    groups: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise GroupRoleMappingError("OIDC groups claim contains a non-string value")
        group = item.strip()
        if group and group not in groups:
            groups.append(group[:200])
    if len(groups) > 100:
        raise GroupRoleMappingError("OIDC groups claim exceeds the supported limit")
    return groups


def resolve_business_role(
    *, groups: list[str], mapping: dict[str, str], require_mapped_group: bool
) -> str:
    mapped = {mapping[group] for group in groups if group in mapping}
    if len(mapped) > 1:
        raise GroupRoleMappingError("OIDC identity maps to conflicting business roles")
    if mapped:
        return mapped.pop()
    if require_mapped_group:
        raise GroupRoleMappingError("OIDC identity is not assigned to a Joukir business group")
    return "member"


def business_role_label(key: str) -> str:
    if key == "platform_admin":
        return "平台管理员"
    if key == "member":
        return "普通成员"
    definition = BUSINESS_ROLE_BY_KEY.get(key)
    return definition.label if definition else key
