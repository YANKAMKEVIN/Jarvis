"""Accessibility (UI element) and composed interaction tools.

Built by ``build(registry)``; ``jarvis.live.registry`` assembles every
toolset into the voice and planner tool lists.
"""
import asyncio
from typing import TYPE_CHECKING, Any

from livekit.agents import function_tool

from jarvis.capabilities.results import ToolResult
from jarvis.live.config import debug_live

if TYPE_CHECKING:
    from jarvis.live.registry import ToolRegistry


def build(registry: "ToolRegistry") -> dict[str, Any]:
    """Return this group's tools by name, bound to ``registry``."""
    @function_tool(
        name="inspect_ui",
        description=(
            "Inspecte les elements Accessibility utiles dans la fenetre "
            "macOS actuelle, avec une profondeur et un nombre d'elements bornes."
        ),
    )
    @registry._desktop_access
    async def inspect_ui(max_depth: int = 4, max_elements: int = 80) -> dict:
        """Inspect the current macOS Accessibility UI tree."""
        debug_live(
            "tool_call",
            tool="inspect_ui",
            max_depth=max_depth,
            max_elements=max_elements,
        )
        async with registry.ui_lock:
            result = await asyncio.to_thread(
                registry.ui_accessibility.inspect_ui,
                max_depth,
                max_elements,
            )
        registry._debug_ui_result("inspect_ui", result)
        return result.to_livekit_dict()

    @function_tool(
        name="find_ui_elements",
        description=(
            "Recherche des elements Accessibility par nom ou label humain. "
            "role est optionnel et ne doit etre fourni que s'il est utile."
        ),
    )
    @registry._desktop_access
    async def find_ui_elements(query: str, role: str | None = None) -> dict:
        """Find current macOS Accessibility UI elements by human label."""
        debug_live(
            "tool_call",
            tool="find_ui_elements",
            query_length=len(query) if isinstance(query, str) else None,
            role=role,
        )
        async with registry.ui_lock:
            result = await asyncio.to_thread(
                registry.ui_accessibility.find_ui_elements,
                query,
                role,
            )
        registry._debug_ui_result("find_ui_elements", result)
        return result.to_livekit_dict()

    @function_tool(
        name="focus_ui_element",
        description=(
            "Met le focus Accessibility sur un element nomme de "
            "l'interface actuelle. L'element est re-resolu juste avant l'action."
        ),
    )
    @registry._desktop_access
    async def focus_ui_element(query: str, role: str | None = None) -> dict:
        """Focus one current macOS Accessibility UI element."""
        debug_live(
            "tool_call",
            tool="focus_ui_element",
            query_length=len(query) if isinstance(query, str) else None,
            role=role,
        )
        async with registry.ui_lock:
            result = await asyncio.to_thread(
                registry.ui_accessibility.focus_ui_element,
                query,
                role,
            )
        registry._debug_ui_result("focus_ui_element", result)
        return result.to_livekit_dict()

    @function_tool(
        name="activate_ui_element",
        description=(
            "Active un element Accessibility nomme avec AXPress lorsque "
            "l'element expose cette action. Aucun fallback souris automatique."
        ),
    )
    @registry._desktop_access
    async def activate_ui_element(query: str, role: str | None = None) -> dict:
        """Activate one current macOS Accessibility UI element with AXPress."""
        debug_live(
            "tool_call",
            tool="activate_ui_element",
            query_length=len(query) if isinstance(query, str) else None,
            role=role,
        )
        async with registry.ui_lock:
            result = await asyncio.to_thread(
                registry.ui_accessibility.activate_ui_element,
                query,
                role,
            )
        registry._debug_ui_result("activate_ui_element", result)
        return result.to_livekit_dict()

    @function_tool(
        name="click_element",
        description=(
            "Clique sur un element de l'ecran decrit par l'utilisateur ('clique "
            "sur Valider', 'clique sur le bouton bleu Envoyer'), en combinant ce "
            "qui est affiche et l'Accessibility. Les coordonnees viennent "
            "TOUJOURS de l'Accessibility, jamais devinees depuis l'image : si "
            "l'element n'est pas expose par Accessibility, Jarvis refuse plutot "
            "que de cliquer a l'aveugle. Il utilise AXPress quand c'est possible, "
            "sinon un clic au centre de la position Accessibility de l'element. "
            "Pour voir ce qui est affiche/cliquable, describe_screen ou "
            "inspect_ui. query : description de l'element."
        ),
    )
    @registry._journaled("click_element")
    @registry._desktop_access
    async def click_element(query: str, role: str | None = None) -> dict:
        """Click an element by its Accessibility-grounded position (never blind)."""
        debug_live("tool_call", tool="click_element",
                   query_length=len(query) if isinstance(query, str) else None)
        located = await asyncio.to_thread(registry.ui_accessibility.locate, query, role)
        if not located.ok:
            return located.to_livekit_dict()
        candidate = located.data.get("candidate") or {}
        actions = candidate.get("actions") or []

        if "AXPress" in actions:
            async with registry.ui_lock:
                result = await asyncio.to_thread(
                    registry.ui_accessibility.activate_ui_element, query, role,
                )
            registry._debug_ui_result("click_element", result)
            return result.to_livekit_dict()

        position = candidate.get("position")
        size = candidate.get("size")
        if not (isinstance(position, dict) and isinstance(size, dict)):
            return ToolResult.failure(
                action="click_element",
                message=(
                    "Cet element n'expose ni action ni position via Accessibility ; "
                    "je ne clique pas a l'aveugle."
                ),
                error_code="no_grounded_target",
            ).to_livekit_dict()

        center_x = int(position["x"] + size["width"] / 2)
        center_y = int(position["y"] + size["height"] / 2)
        async with registry.mouse_lock:
            move = await asyncio.to_thread(registry.mouse.move_mouse, center_x, center_y)
            if not move.ok or move.data.get("state_confirmed") is not True:
                return ToolResult.failure(
                    action="click_element",
                    message="Impossible de positionner le pointeur sur l'element.",
                    error_code="move_failed",
                ).to_livekit_dict()
            await asyncio.to_thread(registry.mouse.click)
        return ToolResult.success(
            action="click_element",
            message=(
                "Clic envoye au centre de l'element (coordonnees Accessibility). "
                "L'effet applicatif n'est pas confirme."
            ),
            command_executed=True,
            state_confirmed=False,
            x=center_x,
            y=center_y,
            grounded="accessibility",
        ).to_livekit_dict()

    @function_tool(
        name="select_all_and_copy",
        description=(
            "Selectionne tout puis copie dans la fenetre active avec une "
            "sequence mecanique command+a puis command+c. Utilise ce tool "
            "pour les demandes naturelles comme selectionne tout et copie."
        ),
    )
    @registry._desktop_access
    async def select_all_and_copy() -> dict:
        """Run command+a then command+c as one ordered interaction."""
        debug_live("tool_call", tool="select_all_and_copy")
        async with registry.interaction_lock:
            result = await asyncio.to_thread(
                registry.interaction.select_all_and_copy,
            )
        registry._debug_interaction_result("select_all_and_copy", result)
        return result.to_livekit_dict()

    @function_tool(
        name="focus_app_ui_and_type",
        description=(
            "Ouvre ou focalise une application, focalise "
            "une cible Accessibility nommee, puis saisit du texte seulement "
            "si la cible est verifiee. Utilise ce tool pour ouvrir une app "
            "et ecrire dans une cible naturelle comme une barre de recherche. "
            "Fournis obligatoirement query pour toute cible semantique nommee ou "
            "impliquee, meme si l'application est connue : recherche/navigation "
            "=> query='recherche', champ Nom => query='Nom'. query=None accepte "
            "uniquement un champ editable actuellement focalise et verifie via "
            "Accessibility ; sinon editable_target_not_verified, aucune saisie ni Enter. "
            "press_enter suit uniquement une saisie executee apres validation. "
            "command_executed ne prouve pas le succes de la recherche/navigation."
        ),
    )
    @registry._journaled("focus_app_ui_and_type", "app_name")
    @registry._desktop_access
    async def focus_app_ui_and_type(
        app_name: str,
        text: str,
        query: str | None = None,
        role: str | None = None,
        press_enter: bool = False,
    ) -> dict:
        """Focus an app/UI target, then type text in a verified sequence."""
        debug_live(
            "tool_call",
            tool="focus_app_ui_and_type",
            app_name=app_name,
            text_length=len(text) if isinstance(text, str) else None,
            query_length=len(query) if isinstance(query, str) else None,
            role=role,
            press_enter=press_enter,
        )
        async with registry.interaction_lock:
            result = await asyncio.to_thread(
                registry.interaction.focus_app_ui_and_type,
                app_name,
                text,
                query,
                role,
                press_enter,
            )
        registry._debug_interaction_result("focus_app_ui_and_type", result)
        return result.to_livekit_dict()

    @function_tool(
        name="open_app_and_focus_ui",
        description=(
            "Ouvre ou focalise une application puis focalise une cible "
            "Accessibility nommee, sans taper de texte. Utilise ce tool "
            "pour ouvrir une app et mettre le curseur dans un champ nomme."
        ),
    )
    @registry._journaled("open_app_and_focus_ui", "app_name")
    @registry._desktop_access
    async def open_app_and_focus_ui(
        app_name: str,
        query: str,
        role: str | None = None,
    ) -> dict:
        """Open/focus an app and focus one named UI element."""
        debug_live(
            "tool_call",
            tool="open_app_and_focus_ui",
            app_name=app_name,
            query_length=len(query) if isinstance(query, str) else None,
            role=role,
        )
        async with registry.interaction_lock:
            result = await asyncio.to_thread(
                registry.interaction.open_app_and_focus_ui,
                app_name,
                query,
                role,
            )
        registry._debug_interaction_result("open_app_and_focus_ui", result)
        return result.to_livekit_dict()

    @function_tool(
        name="select_all_and_delete",
        description=(
            "Selectionne tout puis supprime le texte dans le champ editable "
            "actuellement focalise : verifie d'abord une cible editable sure, "
            "puis command+a, puis une suppression unique (Backspace). Utilise "
            "ce tool pour les demandes comme selectionne tout et supprime ou "
            "efface tout le texte. N'utilise jamais select_all_and_copy pour "
            "supprimer, et ne simule jamais la suppression avec Escape ou "
            "Entree. N'efface aucun fichier et ne copie rien. state_confirmed "
            "reste false : l'effacement du champ ne peut pas etre confirme."
        ),
    )
    @registry._desktop_access
    async def select_all_and_delete() -> dict:
        """Verify an editable target, then Command+A and one Backspace."""
        debug_live("tool_call", tool="select_all_and_delete")
        async with registry.interaction_lock:
            result = await asyncio.to_thread(
                registry.interaction.select_all_and_delete,
            )
        registry._debug_interaction_result("select_all_and_delete", result)
        return result.to_livekit_dict()

    return {
        "inspect_ui": inspect_ui,
        "find_ui_elements": find_ui_elements,
        "focus_ui_element": focus_ui_element,
        "activate_ui_element": activate_ui_element,
        "click_element": click_element,
        "select_all_and_copy": select_all_and_copy,
        "focus_app_ui_and_type": focus_app_ui_and_type,
        "open_app_and_focus_ui": open_app_and_focus_ui,
        "select_all_and_delete": select_all_and_delete,
    }
