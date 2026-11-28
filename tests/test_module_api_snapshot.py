"""Caracterisation de l'API des modules decoupes.

Fige, dans tests/fixtures/module_api.json, les noms accessibles sur chaque
module et, pour chaque classe du projet qu'il definit, ses membres (methodes,
statiques, proprietes, signaux...) avec leur nature. Un decoupage doit garder
tous ces noms importables depuis le module d'origine, avec la meme nature.

Regeneration apres un changement VOLONTAIRE d'API :
    JARVIS_UPDATE_MODULE_API=1 python -m pytest tests/test_module_api_snapshot.py
"""
import importlib
import inspect
import json
import os
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "module_api.json"
MODULES = (
    "jarvis.capabilities.interaction",
    "jarvis.desktop.app",
    "jarvis.desktop.charts",
    "jarvis.desktop.live_runtime",
    "jarvis.tools.accessibility",
    "jarvis.tools.filesystem",
    "jarvis.tools.macos",
)


def _project_members(cls):
    members = {}
    for klass in reversed(cls.__mro__):
        if not getattr(klass, "__module__", "").startswith("jarvis"):
            continue
        for name in vars(klass):
            if name.startswith("__") and name != "__init__":
                continue
            members[name] = type(inspect.getattr_static(cls, name)).__name__
    return dict(sorted(members.items()))


def _describe(module_name):
    module = importlib.import_module(module_name)
    names = sorted(n for n in dir(module) if not n.startswith("__"))
    classes = {}
    for name in names:
        value = getattr(module, name)
        if inspect.isclass(value) and value.__module__ == module_name:
            classes[name] = _project_members(value)
    return {"names": names, "classes": classes}


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8")) if FIXTURE.exists() else {}


if os.environ.get("JARVIS_UPDATE_MODULE_API") == "1":
    FIXTURE.write_text(json.dumps({m: _describe(m) for m in MODULES}, indent=1) + "\n",
                       encoding="utf-8")
_SNAPSHOT = _load()


@pytest.mark.parametrize("module_name", MODULES)
def test_module_keeps_its_names_and_classes(module_name):
    expected = _SNAPSHOT[module_name]
    module = importlib.import_module(module_name)
    missing = [n for n in expected["names"] if not hasattr(module, n)]
    assert missing == []
    for class_name, members in expected["classes"].items():
        cls = getattr(module, class_name)
        assert _project_members(cls) == members, class_name
