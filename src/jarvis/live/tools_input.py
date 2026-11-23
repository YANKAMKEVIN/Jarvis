"""Live tools, family « input » : Clavier, souris et interface accessible.

Part of ToolRegistry.livekit_tools(): `self` is the registry; tools keep its
locks, journal, pending-action store and read-only guard.
"""
from jarvis.capabilities.results import ToolResult
from jarvis.live.config import debug_live
from livekit.agents import function_tool
import asyncio
from jarvis.live.registry import DIRECT_PROMPT_APPS


def input_tools(self) -> dict:
    @function_tool(
        name="type_text",
        description=(
            "Saisit le texte fourni dans la fenetre macOS actuellement "
            "active. N'appuie jamais automatiquement sur Entree."
        ),
    )
    @self._desktop_access
    async def type_text(text: str) -> dict:
        """Type text into the currently active macOS window."""
        debug_live(
            "tool_call",
            tool="type_text",
            length=len(text) if isinstance(text, str) else None,
        )
        async with self.keyboard_lock:
            result = await asyncio.to_thread(self.keyboard.type_text, text)
        self._debug_keyboard_result("type_text", result)
        return result.to_livekit_dict()

    @function_tool(
        name="press_key",
        description=(
            "Appuie sur une touche clavier autorisee dans la fenetre "
            "macOS actuellement active : enter, escape, tab, space, "
            "arrow_up, arrow_down, arrow_left ou arrow_right."
        ),
    )
    @self._desktop_access
    async def press_key(key: str) -> dict:
        """Press one allowed key in the currently active macOS window."""
        debug_live("tool_call", tool="press_key", key=key)
        async with self.keyboard_lock:
            result = await asyncio.to_thread(self.keyboard.press_key, key)
        self._debug_keyboard_result("press_key", result)
        return result.to_livekit_dict()

    @function_tool(
        name="hotkey",
        description=(
            "Envoie un raccourci clavier explicitement autorise dans la "
            "fenetre macOS actuellement active. Passe keys comme une "
            'liste separee, par exemple ["command", "a"] ou '
            '["command", "shift", "z"]. Raccourcis V1 : command+a, '
            "command+c, command+v, command+z, command+shift+z, "
            "command+f, command+s."
        ),
    )
    @self._desktop_access
    async def hotkey(keys: list[str]) -> dict:
        """Send one allowed hotkey in the active macOS window."""
        debug_live("tool_call", tool="hotkey", keys=keys)
        async with self.keyboard_lock:
            result = await asyncio.to_thread(self.keyboard.hotkey, keys)
        self._debug_keyboard_result("hotkey", result)
        return result.to_livekit_dict()

    @function_tool(
        name="get_mouse_position",
        description=(
            "Lit la position actuelle reelle du pointeur de souris dans "
            "les coordonnees globales macOS."
        ),
    )
    @self._desktop_access
    async def get_mouse_position() -> dict:
        """Read the current mouse pointer position."""
        debug_live("tool_call", tool="get_mouse_position")
        async with self.mouse_lock:
            result = await asyncio.to_thread(self.mouse.get_mouse_position)
        self._debug_mouse_result("get_mouse_position", result)
        return result.to_livekit_dict()

    @function_tool(
        name="move_mouse",
        description=(
            "Deplace le pointeur de souris vers des coordonnees macOS "
            "explicites x/y. Ne devine jamais ces coordonnees."
        ),
    )
    @self._desktop_access
    async def move_mouse(x: int, y: int) -> dict:
        """Move the mouse pointer to explicit macOS coordinates."""
        debug_live("tool_call", tool="move_mouse", x=x, y=y)
        async with self.mouse_lock:
            result = await asyncio.to_thread(self.mouse.move_mouse, x, y)
        self._debug_mouse_result("move_mouse", result)
        return result.to_livekit_dict()

    @function_tool(
        name="click",
        description=(
            "Envoie un clic gauche a la position actuelle du pointeur. "
            "Ce tool ne confirme pas l'effet applicatif du clic."
        ),
    )
    @self._desktop_access
    async def click() -> dict:
        """Send one left click at the current mouse position."""
        debug_live("tool_call", tool="click")
        async with self.mouse_lock:
            result = await asyncio.to_thread(self.mouse.click)
        self._debug_mouse_result("click", result)
        return result.to_livekit_dict()

    @function_tool(
        name="double_click",
        description=(
            "Envoie un double clic gauche a la position actuelle du "
            "pointeur. Ce tool ne confirme pas l'effet applicatif."
        ),
    )
    @self._desktop_access
    async def double_click() -> dict:
        """Send one double left click at the current mouse position."""
        debug_live("tool_call", tool="double_click")
        async with self.mouse_lock:
            result = await asyncio.to_thread(self.mouse.double_click)
        self._debug_mouse_result("double_click", result)
        return result.to_livekit_dict()

    @function_tool(
        name="right_click",
        description=(
            "Envoie un clic droit a la position actuelle du pointeur. "
            "Ce tool ne confirme pas l'effet applicatif du clic."
        ),
    )
    @self._desktop_access
    async def right_click() -> dict:
        """Send one right click at the current mouse position."""
        debug_live("tool_call", tool="right_click")
        async with self.mouse_lock:
            result = await asyncio.to_thread(self.mouse.right_click)
        self._debug_mouse_result("right_click", result)
        return result.to_livekit_dict()

    @function_tool(
        name="scroll",
        description=(
            "Envoie un scroll souris dans une direction explicite : up, "
            "down, left ou right, avec amount entre 1 et 10."
        ),
    )
    @self._desktop_access
    async def scroll(direction: str, amount: int = 3) -> dict:
        """Send a bounded mouse scroll command."""
        debug_live(
            "tool_call",
            tool="scroll",
            direction=direction,
            amount=amount,
        )
        async with self.mouse_lock:
            result = await asyncio.to_thread(
                self.mouse.scroll,
                direction,
                amount,
            )
        self._debug_mouse_result("scroll", result)
        return result.to_livekit_dict()

    @function_tool(
        name="inspect_ui",
        description=(
            "Inspecte les elements Accessibility utiles dans la fenetre "
            "macOS actuelle, avec une profondeur et un nombre d'elements bornes."
        ),
    )
    @self._desktop_access
    async def inspect_ui(max_depth: int = 4, max_elements: int = 80) -> dict:
        """Inspect the current macOS Accessibility UI tree."""
        debug_live(
            "tool_call",
            tool="inspect_ui",
            max_depth=max_depth,
            max_elements=max_elements,
        )
        async with self.ui_lock:
            result = await asyncio.to_thread(
                self.ui_accessibility.inspect_ui,
                max_depth,
                max_elements,
            )
        self._debug_ui_result("inspect_ui", result)
        return result.to_livekit_dict()

    @function_tool(
        name="find_ui_elements",
        description=(
            "Recherche des elements Accessibility par nom ou label humain. "
            "role est optionnel et ne doit etre fourni que s'il est utile."
        ),
    )
    @self._desktop_access
    async def find_ui_elements(query: str, role: str | None = None) -> dict:
        """Find current macOS Accessibility UI elements by human label."""
        debug_live(
            "tool_call",
            tool="find_ui_elements",
            query_length=len(query) if isinstance(query, str) else None,
            role=role,
        )
        async with self.ui_lock:
            result = await asyncio.to_thread(
                self.ui_accessibility.find_ui_elements,
                query,
                role,
            )
        self._debug_ui_result("find_ui_elements", result)
        return result.to_livekit_dict()

    @function_tool(
        name="focus_ui_element",
        description=(
            "Met le focus Accessibility sur un element nomme de "
            "l'interface actuelle. L'element est re-resolu juste avant l'action."
        ),
    )
    @self._desktop_access
    async def focus_ui_element(query: str, role: str | None = None) -> dict:
        """Focus one current macOS Accessibility UI element."""
        debug_live(
            "tool_call",
            tool="focus_ui_element",
            query_length=len(query) if isinstance(query, str) else None,
            role=role,
        )
        async with self.ui_lock:
            result = await asyncio.to_thread(
                self.ui_accessibility.focus_ui_element,
                query,
                role,
            )
        self._debug_ui_result("focus_ui_element", result)
        return result.to_livekit_dict()

    @function_tool(
        name="activate_ui_element",
        description=(
            "Active un element Accessibility nomme avec AXPress lorsque "
            "l'element expose cette action. Aucun fallback souris automatique."
        ),
    )
    @self._desktop_access
    async def activate_ui_element(query: str, role: str | None = None) -> dict:
        """Activate one current macOS Accessibility UI element with AXPress."""
        debug_live(
            "tool_call",
            tool="activate_ui_element",
            query_length=len(query) if isinstance(query, str) else None,
            role=role,
        )
        async with self.ui_lock:
            result = await asyncio.to_thread(
                self.ui_accessibility.activate_ui_element,
                query,
                role,
            )
        self._debug_ui_result("activate_ui_element", result)
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
    @self._journaled("click_element")
    @self._desktop_access
    async def click_element(query: str, role: str | None = None) -> dict:
        """Click an element by its Accessibility-grounded position (never blind)."""
        debug_live("tool_call", tool="click_element",
                   query_length=len(query) if isinstance(query, str) else None)
        located = await asyncio.to_thread(self.ui_accessibility.locate, query, role)
        if not located.ok:
            return located.to_livekit_dict()
        candidate = located.data.get("candidate") or {}
        actions = candidate.get("actions") or []

        if "AXPress" in actions:
            async with self.ui_lock:
                result = await asyncio.to_thread(
                    self.ui_accessibility.activate_ui_element, query, role,
                )
            self._debug_ui_result("click_element", result)
            return result.to_livekit_dict()

        position = candidate.get("position")
        size = candidate.get("size")
        if not (isinstance(position, dict) and isinstance(size, dict)):
            return ToolResult.failure(
                action="click_element",
                message=(
                    "Cet élément n'expose ni action ni position via Accessibility ; "
                    "je ne clique pas à l'aveugle."
                ),
                error_code="no_grounded_target",
            ).to_livekit_dict()

        center_x = int(position["x"] + size["width"] / 2)
        center_y = int(position["y"] + size["height"] / 2)
        async with self.mouse_lock:
            move = await asyncio.to_thread(self.mouse.move_mouse, center_x, center_y)
            if not move.ok or move.data.get("state_confirmed") is not True:
                return ToolResult.failure(
                    action="click_element",
                    message="Impossible de positionner le pointeur sur l'élément.",
                    error_code="move_failed",
                ).to_livekit_dict()
            await asyncio.to_thread(self.mouse.click)
        return ToolResult.success(
            action="click_element",
            message=(
                "Clic envoyé au centre de l'élément (coordonnées Accessibility). "
                "L'effet applicatif n'est pas confirmé."
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
    @self._desktop_access
    async def select_all_and_copy() -> dict:
        """Run command+a then command+c as one ordered interaction."""
        debug_live("tool_call", tool="select_all_and_copy")
        async with self.interaction_lock:
            result = await asyncio.to_thread(
                self.interaction.select_all_and_copy,
            )
        self._debug_interaction_result("select_all_and_copy", result)
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
    @self._journaled("focus_app_ui_and_type", "app_name")
    @self._desktop_access
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
        async with self.interaction_lock:
            result = await asyncio.to_thread(
                self.interaction.focus_app_ui_and_type,
                app_name,
                text,
                query,
                role,
                press_enter,
            )
        self._debug_interaction_result("focus_app_ui_and_type", result)
        return result.to_livekit_dict()

    @function_tool(
        name="open_app_and_focus_ui",
        description=(
            "Ouvre ou focalise une application puis focalise une cible "
            "Accessibility nommee, sans taper de texte. Utilise ce tool "
            "pour ouvrir une app et mettre le curseur dans un champ nomme."
        ),
    )
    @self._journaled("open_app_and_focus_ui", "app_name")
    @self._desktop_access
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
        async with self.interaction_lock:
            result = await asyncio.to_thread(
                self.interaction.open_app_and_focus_ui,
                app_name,
                query,
                role,
            )
        self._debug_interaction_result("open_app_and_focus_ui", result)
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
    @self._desktop_access
    async def select_all_and_delete() -> dict:
        """Verify an editable target, then Command+A and one Backspace."""
        debug_live("tool_call", tool="select_all_and_delete")
        async with self.interaction_lock:
            result = await asyncio.to_thread(
                self.interaction.select_all_and_delete,
            )
        self._debug_interaction_result("select_all_and_delete", result)
        return result.to_livekit_dict()

    @function_tool(
        name="send_prompt_to_app",
        description=(
            "Ouvre ou focalise une application de chat (par exemple Claude), "
            "verifie le champ de saisie editable focalise, y saisit le texte "
            "puis valide avec Entree pour l'envoyer. Utilise ce tool pour une "
            "demande comme demande a Claude de ..., ouvre Claude et ecris ... "
            "ou lance une discussion avec Claude sur ... Fournis query "
            "seulement si un champ precis est nomme ; sinon la saisie va dans "
            "le champ editable actuellement focalise, qui doit etre verifie "
            "via Accessibility. Si editable_target_not_verified est retourne, "
            "rien n'a ete saisi ni envoye : demande une clarification. "
            "command_executed signifie que la saisie et la validation ont ete "
            "envoyees, pas que l'application a traite la demande."
        ),
    )
    @self._journaled("send_prompt_to_app", "app_name")
    @self._desktop_access
    async def send_prompt_to_app(
        app_name: str,
        text: str,
        query: str | None = None,
    ) -> dict:
        """Open/focus an app, type a prompt into it, and submit with Enter."""
        debug_live(
            "tool_call",
            tool="send_prompt_to_app",
            app_name=app_name,
            text_length=len(text) if isinstance(text, str) else None,
            query_length=len(query) if isinstance(query, str) else None,
        )
        direct = (
            not (isinstance(query, str) and query.strip())
            and isinstance(app_name, str)
            and app_name.strip().casefold() in DIRECT_PROMPT_APPS
        )
        async with self.interaction_lock:
            if direct:
                # Electron/web apps (e.g. Claude) expose no targetable AX
                # field: confirm the app is frontmost, then type directly.
                result = await asyncio.to_thread(
                    self.interaction.open_app_and_type,
                    app_name,
                    text,
                    True,
                )
            else:
                result = await asyncio.to_thread(
                    self.interaction.focus_app_ui_and_type,
                    app_name,
                    text,
                    query,
                    None,
                    True,
                )
        self._debug_interaction_result("send_prompt_to_app", result)
        return result.to_livekit_dict()

    return {
        "type_text": type_text,
        "press_key": press_key,
        "hotkey": hotkey,
        "get_mouse_position": get_mouse_position,
        "move_mouse": move_mouse,
        "click": click,
        "double_click": double_click,
        "right_click": right_click,
        "scroll": scroll,
        "inspect_ui": inspect_ui,
        "find_ui_elements": find_ui_elements,
        "focus_ui_element": focus_ui_element,
        "activate_ui_element": activate_ui_element,
        "click_element": click_element,
        "select_all_and_copy": select_all_and_copy,
        "focus_app_ui_and_type": focus_app_ui_and_type,
        "open_app_and_focus_ui": open_app_and_focus_ui,
        "select_all_and_delete": select_all_and_delete,
        "send_prompt_to_app": send_prompt_to_app,
    }
