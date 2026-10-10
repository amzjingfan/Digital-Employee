from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi import HTTPException

from app.api.general_skills import (
    _files_from_zip,
    _normalize_skill_files,
    _validate_skill_package_references,
)
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


def test_folder_import_rejects_multiple_skill_definitions() -> None:
    with pytest.raises(HTTPException, match="multiple SKILL.md"):
        _normalize_skill_files(
            [
                GeneralSkillFile(path="bundle/one/SKILL.md", content="# One"),
                GeneralSkillFile(path="bundle/two/SKILL.md", content="# Two"),
            ],
            None,
        )


def test_zip_import_rejects_multiple_skill_definitions() -> None:
    archive = BytesIO()
    with ZipFile(archive, "w") as zipped:
        zipped.writestr("bundle/one/SKILL.md", "# One")
        zipped.writestr("bundle/two/SKILL.md", "# Two")

    with pytest.raises(HTTPException, match="multiple SKILL.md"):
        _files_from_zip(archive.getvalue())
