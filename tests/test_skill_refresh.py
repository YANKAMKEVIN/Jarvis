"""A skill added during the session is usable at once (idea 33)."""
from jarvis.live.extensions import _skills_description
from jarvis.skills import SkillLibrary

SKILL = """---
name: {name}
description: Fait une revue de la semaine.
---
Etapes de la revue.
"""


def add_skill(root, name):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(SKILL.format(name=name))


def test_use_skill_rereads_folders_for_an_unknown_name(tmp_path):
    library = SkillLibrary([tmp_path])
    assert library.list_skills().data["skills"] == []
    add_skill(tmp_path, "weekly-review")
    result = library.use_skill("weekly-review")
    assert result.ok, result.message
    assert library.use_skill("absente").error_code == "skill_not_found"


def test_description_points_to_list_skills_for_newer_skills(tmp_path):
    add_skill(tmp_path, "weekly-review")
    description = _skills_description(SkillLibrary([tmp_path]))
    assert "list_skills" in description and "weekly-review" in description
