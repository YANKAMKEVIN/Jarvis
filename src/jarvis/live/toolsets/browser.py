"""Browser tools.

Built by ``build(registry)``; ``jarvis.live.registry`` assembles every
toolset into the voice and planner tool lists.
"""
import asyncio
from typing import TYPE_CHECKING, Any

from livekit.agents import function_tool

from jarvis.live.config import debug_live

if TYPE_CHECKING:
    from jarvis.live.registry import ToolRegistry


def build(registry: "ToolRegistry") -> dict[str, Any]:
    """Return this group's tools by name, bound to ``registry``."""
    @function_tool(
        name="browse_open_url",
        description=(
            "Ouvre une URL dans Safari ou Google Chrome, active la fenetre "
            "puis relit l'onglet actif pour verifier le chargement. Utilise "
            "ce tool pour aller sur un site. browser=None choisit "
            "automatiquement le navigateur ouvert (Safari par defaut). "
            "new_tab=true ouvre un nouvel onglet, false reutilise l'onglet "
            "actif. state_confirmed=true seulement si l'onglet actif pointe "
            "bien vers le domaine demande."
        ),
    )
    @registry._journaled("browse_open_url", "url", registry._journal_host)
    @registry._desktop_access
    async def browse_open_url(
        url: str,
        browser: str | None = None,
        new_tab: bool = True,
    ) -> dict:
        """Open a URL in a browser and verify the active tab."""
        debug_live(
            "tool_call",
            tool="browse_open_url",
            browser=browser,
            new_tab=new_tab,
        )
        async with registry.browser_lock:
            result = await asyncio.to_thread(
                registry.browser.open_url,
                url,
                browser,
                new_tab,
            )
        registry._debug_browser_result("browse_open_url", result)
        return result.to_livekit_dict()

    @function_tool(
        name="browse_search_web",
        description=(
            "Lance une recherche web dans Safari ou Google Chrome puis relit "
            "l'onglet actif pour verifier. Utilise ce tool pour une demande "
            "comme cherche la meteo. engine accepte google, duckduckgo ou "
            "bing (google par defaut). command_executed ne prouve pas que les "
            "resultats sont charges ; state_confirmed le fait."
        ),
    )
    @registry._journaled("browse_search_web")
    @registry._desktop_access
    async def browse_search_web(
        query: str,
        browser: str | None = None,
        engine: str | None = None,
    ) -> dict:
        """Run a web search in a browser and verify the active tab."""
        debug_live(
            "tool_call",
            tool="browse_search_web",
            browser=browser,
            engine=engine,
            query_length=len(query) if isinstance(query, str) else None,
        )
        async with registry.browser_lock:
            result = await asyncio.to_thread(
                registry.browser.search_web,
                query,
                browser,
                engine,
            )
        registry._debug_browser_result("browse_search_web", result)
        return result.to_livekit_dict()

    @function_tool(
        name="browse_get_active_tab",
        description=(
            "Lit l'onglet actif (URL et titre) de Safari ou Google Chrome. "
            "Utilise ce tool pour savoir quelle page est affichee au lieu de "
            "le deduire. browser=None choisit automatiquement le navigateur."
        ),
    )
    @registry._desktop_access
    async def browse_get_active_tab(browser: str | None = None) -> dict:
        """Read the active tab of a browser."""
        debug_live("tool_call", tool="browse_get_active_tab", browser=browser)
        async with registry.browser_lock:
            result = await asyncio.to_thread(
                registry.browser.get_active_tab,
                browser,
            )
        registry._debug_browser_result("browse_get_active_tab", result)
        return result.to_livekit_dict()

    @function_tool(
        name="browse_list_tabs",
        description=(
            "Liste les onglets ouverts (index, URL, titre) de la fenetre "
            "active de Safari ou Google Chrome. Utile avant d'activer un "
            "onglet precis. browser=None choisit automatiquement."
        ),
    )
    @registry._desktop_access
    async def browse_list_tabs(browser: str | None = None) -> dict:
        """List the tabs of a browser's front window."""
        debug_live("tool_call", tool="browse_list_tabs", browser=browser)
        async with registry.browser_lock:
            result = await asyncio.to_thread(
                registry.browser.list_tabs,
                browser,
            )
        registry._debug_browser_result("browse_list_tabs", result)
        return result.to_livekit_dict()

    @function_tool(
        name="browse_activate_tab",
        description=(
            "Active un onglet dans Safari ou Google Chrome, puis verifie "
            "qu'il est au premier plan. Deux modes exclusifs : fournis index, "
            "un entier (position de l'onglet telle que donnee par "
            "browse_list_tabs), pour l'activer directement et de maniere "
            "deterministe ; OU fournis query (texte) pour une recherche sur "
            "l'URL ou le titre. Quand l'utilisateur choisit explicitement un "
            "onglet par son numero ou sa position (par exemple le 8), utilise "
            "index, jamais query. Si query correspond a plusieurs onglets, le "
            "resultat est ambiguous_tab : ne choisis pas au hasard, relis "
            "browse_list_tabs et rappelle ce tool avec l'index voulu. "
            "browser=None choisit automatiquement."
        ),
    )
    @registry._desktop_access
    async def browse_activate_tab(
        query: str | None = None,
        index: int | None = None,
        browser: str | None = None,
    ) -> dict:
        """Activate a tab by explicit index or by query, then verify it."""
        debug_live(
            "tool_call",
            tool="browse_activate_tab",
            browser=browser,
            index=index,
            query_length=len(query) if isinstance(query, str) else None,
        )
        async with registry.browser_lock:
            result = await asyncio.to_thread(
                registry.browser.activate_tab,
                query,
                index,
                browser,
            )
        registry._debug_browser_result("browse_activate_tab", result)
        return result.to_livekit_dict()

    return {
        "browse_open_url": browse_open_url,
        "browse_search_web": browse_search_web,
        "browse_get_active_tab": browse_get_active_tab,
        "browse_list_tabs": browse_list_tabs,
        "browse_activate_tab": browse_activate_tab,
    }
