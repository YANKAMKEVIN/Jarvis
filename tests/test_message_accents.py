"""Messages shown in the desktop cards keep their French accents (idea 36).

Scans every ToolResult.success/failure message written in capabilities/,
live/ and planner/ for unaccented spellings of common words. Add the accent
rather than extending the allowlist.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "jarvis"
UNACCENTED = {
    "etre", "ete", "deja", "apres", "securite", "duree", "evenement", "evenements", "fenetre", "ecran",
    "memoire", "modele", "reponse", "resultat", "resultats", "echec", "element", "elements", "operation",
    "etape", "etapes", "tache", "taches", "caractere", "caracteres", "reglage", "systeme", "acces",
    "periode", "delai", "luminosite", "evenement", "donnees", "parametre", "requete", "debut",
}
WORD = re.compile(r"[A-Za-zÀ-ÿ]+")


def messages():
    for folder in ("capabilities", "live", "planner"):
        for path in (ROOT / folder).glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                if name not in ("success", "failure"):
                    continue
                values = [kw.value for kw in node.keywords if kw.arg == "message"] + node.args[1:2]
                for value in values:
                    for part in ast.walk(value):
                        if isinstance(part, ast.Constant) and isinstance(part.value, str):
                            yield path.relative_to(ROOT), part.value


def test_tool_messages_keep_their_accents():
    offenders = []
    for path, text in messages():
        bad = sorted({word.lower() for word in WORD.findall(text)} & UNACCENTED)
        if bad:
            offenders.append(f"{path}: {bad} in {text[:80]!r}")
    assert not offenders, "\n".join(offenders)


def test_scan_finds_messages():
    assert sum(1 for _ in messages()) > 150
