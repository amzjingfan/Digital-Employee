import pytest

from app.security.business_roles import (
    GroupRoleMappingError,
    normalized_group_claim,
    parse_group_role_mapping,
    resolve_business_role,
)


def test_group_claim_is_deduplicated_without_alias_expansion() -> None:
    groups = ["acme/staffdeck-designer", "acme/staffdeck-designer"]
    assert normalized_group_claim(groups) == [
        "acme/staffdeck-designer"
    ]


def test_mapping_rejects_unknown_role() -> None:
    with pytest.raises(GroupRoleMappingError):
        parse_group_role_mapping('{"built-in/unknown":"platform_owner"}')


def test_strict_mapping_requires_exact_configured_group() -> None:
    mapping = parse_group_role_mapping('{"acme/staffdeck-designer":"designer"}')
    assert resolve_business_role(
        groups=["acme/staffdeck-designer"], mapping=mapping, require_mapped_group=True
    ) == "designer"
    with pytest.raises(GroupRoleMappingError):
        resolve_business_role(
            groups=["other/staffdeck-designer"], mapping=mapping, require_mapped_group=True
        )
