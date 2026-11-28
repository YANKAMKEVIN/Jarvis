"""Recovery of UI focus when the requested element is not found."""
from __future__ import annotations

import re
from typing import Any

from jarvis.capabilities.results import ToolResult
from jarvis.tools.accessibility import normalize_text


class InteractionRecoveryMixin:
    """Recovery of UI focus when the requested element is not found. Mixed into InteractionCapability."""

    def _recover_ui_focus(
        self,
        action: str,
        query: str,
        role: str | None,
        steps: list[dict[str, Any]],
    ) -> ToolResult:
        inspected = self.ui_accessibility.inspect_ui(max_depth=6, max_elements=150)
        steps.append(self._step(
            "inspect_ui_recovery",
            inspected,
            recovery_attempted=True,
        ))

        if not inspected.ok:
            return inspected

        candidates = self._recovery_candidates(
            query=query,
            role=role,
            elements=inspected.data.get("elements", []),
        )

        if not candidates:
            return ToolResult(
                ok=False,
                action=action,
                message=(
                    "Aucun candidat Accessibility suffisamment sur n'a ete "
                    "trouve pour recuperer cette cible."
                ),
                data={
                    "query_length": self._safe_len(query),
                    "role": role,
                    "recovery_attempted": True,
                    "recovery_succeeded": False,
                    "candidate_count": 0,
                },
                error_code="ui_element_not_found",
            )

        if len(candidates) > 1:
            return ToolResult(
                ok=False,
                action=action,
                message=(
                    "Plusieurs candidats Accessibility plausibles ont ete "
                    "trouves pendant la recuperation."
                ),
                data={
                    "query_length": self._safe_len(query),
                    "role": role,
                    "recovery_attempted": True,
                    "recovery_succeeded": False,
                    "candidate_count": len(candidates),
                },
                error_code="ambiguous_ui_element",
            )

        recovered_label = self._candidate_label(candidates[0])
        recovered = self.ui_accessibility.focus_ui_element(recovered_label, role)
        steps.append(self._step(
            "focus_ui_element_recovery",
            recovered,
            query_length=self._safe_len(recovered_label),
            role=role,
            recovery_attempted=True,
            recovery_succeeded=recovered.ok and recovered.data.get("state_confirmed") is True,
        ))
        return recovered

    def _recovery_candidates(
        self,
        query: str,
        role: str | None,
        elements: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(elements, list):
            return []

        normalized_query = normalize_text(query)

        if len(normalized_query) <= 1:
            return []

        query_tokens = set(normalized_query.split())

        if not query_tokens.intersection(self.SEARCH_TOKENS):
            return []

        normalized_role = normalize_text(role) if role else None
        candidates = []

        for element in elements:
            if not isinstance(element, dict):
                continue

            element_role = element.get("role")

            if normalized_role and normalize_text(element_role) != normalized_role:
                continue

            if not normalized_role and element_role not in self.RECOVERY_TEXT_ROLES:
                continue

            fields = [
                field
                for field in (
                    element.get("title"),
                    element.get("description"),
                    element.get("identifier"),
                )
                if isinstance(field, str) and field.strip()
            ]

            if any(
                set(re.findall(r"[^\W_]+", normalize_text(field))).intersection(self.SEARCH_TOKENS)
                for field in fields
            ):
                candidates.append(element)

        return candidates

    @staticmethod
    def _candidate_label(candidate: dict[str, Any]) -> str:
        for key in ("title", "description", "identifier"):
            value = candidate.get(key)

            if isinstance(value, str) and value.strip():
                return value

        return ""
