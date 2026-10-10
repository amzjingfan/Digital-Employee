from app.api.general_skills import _normalize_skill_files, _validate_skill_package_references
from app.general_skills.schema import GeneralSkillFile


def test_folder_import_accepts_markdown_references_followed_by_chinese_text() -> None:
    files = _normalize_skill_files(
        [
            GeneralSkillFile(
                path="amazon-ads-autopilot/skills/amazon-ads-autopilot/SKILL.md",
                content=(
                    "读取 [数据契约](references/data-contract.md)。数据不全时记录缺口。\n"
                    "再读 references/decision-rules.md，计算动作。\n"
                ),
            ),
            GeneralSkillFile(
                path="amazon-ads-autopilot/skills/amazon-ads-autopilot/references/data-contract.md",
                content="# 数据契约\n",
            ),
            GeneralSkillFile(
                path="amazon-ads-autopilot/skills/amazon-ads-autopilot/references/decision-rules.md",
                content="# 决策规则\n",
            ),
        ],
        None,
    )

    assert [file.path for file in files] == [
        "SKILL.md",
        "references/data-contract.md",
        "references/decision-rules.md",
    ]
    _validate_skill_package_references(files)
