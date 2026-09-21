import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


class RequestType(Enum):
    ACTION = "action"
    CONVERSATION = "conversation"
    KNOWLEDGE = "knowledge"


@dataclass
class RouteDecision:
    request_type: RequestType
    reason: str


def normalize_text(text: str) -> str:
    text = text.lower()
    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    text = re.sub(r"[^a-z0-9\s%]", " ", text)
    return " ".join(text.split())


class RequestRouter:
    ACTION_PATTERNS = [
        r"^(?:ouvre|lance|demarre)\b",
        r"^(?:ferme|quitte)\b",
        r"^(?:mets|regle|baisse|monte)\b.*\bvolume\b",
        r"^(?:coupe|remets)\b.*\bson\b",
        r"^(?:recherche|cherche)\b",
        r"^(?:va|ouvre)\b.*\b(?:sur|\.com|\.fr|\.org|\.net)\b",
        r"^(?:quelle date sommes nous|nous sommes quel jour|donne moi la date)\b",
    ]

    CONVERSATION_PATTERNS = [
        r"^(?:aide moi|aide-moi)\b",
        r"^resume\b",
        r"^reformule\b",
        r"^donne moi\b.*\bidees?\b",
        r"^explique moi simplement\b",
    ]

    KNOWLEDGE_PATTERNS = [
        r"\b(?:actuel|actuelle|actuellement|aujourd hui|demain|hier|recent|recents|dernier|derniere|maintenant)\b",
        r"\b(?:actualites|meteo|prix|cours|bitcoin|match|resultat|president|dirigeant|horaire|horaires)\b",
        r"^qui (?:est|a gagne)\b",
        r"^quel(?:le|s)?\b.*\b(?:prix|temps|meteo|president|date|heure)\b",
        r"^comment dit on\b",
        r"^que signifie\b.*\bexpression\b",
    ]

    def classify(self, message: str) -> RouteDecision:
        normalized = normalize_text(message)

        if not normalized:
            return RouteDecision(
                RequestType.CONVERSATION,
                "message vide ou non exploitable",
            )

        if self._matches_any(normalized, self.ACTION_PATTERNS):
            return RouteDecision(
                RequestType.ACTION,
                "formulation compatible avec une action locale",
            )

        if self._matches_any(normalized, self.KNOWLEDGE_PATTERNS):
            return RouteDecision(
                RequestType.KNOWLEDGE,
                "information factuelle a verifier",
            )

        if self._matches_any(normalized, self.CONVERSATION_PATTERNS):
            return RouteDecision(
                RequestType.CONVERSATION,
                "tache de redaction ou raisonnement local",
            )

        return RouteDecision(
            RequestType.CONVERSATION,
            "route par defaut vers le modele local",
        )

    @staticmethod
    def _matches_any(text: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, text) for pattern in patterns)
