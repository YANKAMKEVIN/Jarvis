from __future__ import annotations

from typing import Any

from jarvis.capabilities.results import ToolResult
from jarvis.tools.browser import BrowserError, BrowserTools


class BrowserCapability:
    """Tab-aware, verified control of Safari / Google Chrome.

    Navigation and reads only. Every mutating flow reads the active tab back
    and reports state_confirmed from the observed URL, so a sent command is
    never mistaken for a loaded page.
    """

    def __init__(self, browser_tools: BrowserTools | None = None):
        self.browser_tools = (
            browser_tools if browser_tools is not None else BrowserTools()
        )

    def open_url(
        self,
        url: str,
        browser: str | None = None,
        new_tab: bool = True,
    ) -> ToolResult:
        try:
            state = self.browser_tools.open_url(url, browser, new_tab)
        except BrowserError as error:
            return self._tool_failure("open_url", error)
        except Exception as error:
            return self._system_error("open_url", error)

        if state.get("state_confirmed"):
            message = f"{state['browser']} affiche la page demandee."
        else:
            message = (
                f"La commande de navigation a ete envoyee a {state['browser']}, "
                "mais le chargement de la page n'est pas confirme."
            )

        return ToolResult.success(action="open_url", message=message, **state)

    def search_web(
        self,
        query: str,
        browser: str | None = None,
        engine: str | None = None,
    ) -> ToolResult:
        try:
            url = self.browser_tools.build_search_url(query, engine)
        except BrowserError as error:
            return self._tool_failure("search_web", error)

        try:
            state = self.browser_tools.open_url(url, browser, new_tab=True)
        except BrowserError as error:
            return self._tool_failure("search_web", error)
        except Exception as error:
            return self._system_error("search_web", error)

        if state.get("state_confirmed"):
            message = f"La recherche a ete lancee dans {state['browser']}."
        else:
            message = (
                f"La recherche a ete envoyee a {state['browser']}, mais la page "
                "de resultats n'est pas confirmee."
            )

        return ToolResult.success(
            action="search_web",
            message=message,
            query_length=self._safe_len(query),
            engine=(engine or "google"),
            **state,
        )

    def get_active_tab(self, browser: str | None = None) -> ToolResult:
        try:
            state = self.browser_tools.get_active_tab(browser)
        except BrowserError as error:
            return self._tool_failure("get_active_tab", error)
        except Exception as error:
            return self._system_error("get_active_tab", error)

        if not state.get("has_window"):
            message = f"{state['browser']} n'a aucune fenetre ouverte."
        elif state.get("title"):
            message = f"L'onglet actif de {state['browser']} : {state['title']}."
        else:
            message = f"L'onglet actif de {state['browser']} a ete lu."

        return ToolResult.success(action="get_active_tab", message=message, **state)

    def list_tabs(self, browser: str | None = None) -> ToolResult:
        try:
            state = self.browser_tools.list_tabs(browser)
        except BrowserError as error:
            return self._tool_failure("list_tabs", error)
        except Exception as error:
            return self._system_error("list_tabs", error)

        count = state.get("count", 0)
        message = (
            f"{state['browser']} n'a aucune fenetre ouverte."
            if count == 0
            else f"{count} onglet(s) ouvert(s) dans {state['browser']}."
        )

        return ToolResult.success(action="list_tabs", message=message, **state)

    def activate_tab(self, query: str, browser: str | None = None) -> ToolResult:
        if not isinstance(query, str) or not query.strip():
            return ToolResult.failure(
                action="activate_tab",
                message="Le critere de recherche de l'onglet est obligatoire.",
                error_code="invalid_query",
            )

        try:
            listing = self.browser_tools.list_tabs(browser)
        except BrowserError as error:
            return self._tool_failure("activate_tab", error)
        except Exception as error:
            return self._system_error("activate_tab", error)

        matches = self._match_tabs(query, listing.get("tabs", []))

        if not matches:
            return ToolResult.failure(
                action="activate_tab",
                message="Aucun onglet ne correspond a cette recherche.",
                error_code="tab_not_found",
            )

        if len(matches) > 1:
            return ToolResult.failure(
                action="activate_tab",
                message=(
                    "Plusieurs onglets correspondent. Precise lequel activer."
                ),
                error_code="ambiguous_tab",
            )

        target = matches[0]

        try:
            state = self.browser_tools.activate_tab_index(
                target["index"],
                listing.get("browser"),
            )
        except BrowserError as error:
            return self._tool_failure("activate_tab", error)
        except Exception as error:
            return self._system_error("activate_tab", error)

        if not state.get("state_confirmed"):
            return ToolResult(
                ok=False,
                action="activate_tab",
                message="L'onglet cible n'a pas pu etre confirme au premier plan.",
                data=dict(state),
                error_code="tab_not_activated",
            )

        return ToolResult.success(
            action="activate_tab",
            message=f"L'onglet a ete active dans {state['browser']}.",
            query_length=self._safe_len(query),
            **state,
        )

    @staticmethod
    def _match_tabs(query: str, tabs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        needle = query.strip().casefold()
        matches = []

        for tab in tabs:
            if tab.get("index") is None:
                continue

            haystack = " ".join(
                value.casefold()
                for value in (tab.get("url"), tab.get("title"))
                if isinstance(value, str)
            )

            if needle in haystack:
                matches.append(tab)

        return matches

    @staticmethod
    def _tool_failure(action: str, error: BrowserError) -> ToolResult:
        return ToolResult(
            ok=False,
            action=action,
            message=error.message,
            data=dict(error.data),
            error_code=error.code or "browser_error",
        )

    @staticmethod
    def _system_error(action: str, error: Exception) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message=f"Echec du controle du navigateur : {error}",
            error_code="system_error",
        )

    @staticmethod
    def _safe_len(value: str | None) -> int | None:
        return len(value) if isinstance(value, str) else None
