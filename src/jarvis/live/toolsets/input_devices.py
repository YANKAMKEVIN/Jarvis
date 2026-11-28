"""Clipboard, keyboard and mouse tools.

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
        name="get_clipboard_text",
        description=(
            "Lit le texte actuellement disponible dans le presse-papiers "
            "du Mac. Utilise ce tool pour savoir ce qui a ete copie ou "
            "si le presse-papiers contient du texte."
        ),
    )
    @registry._desktop_access
    async def get_clipboard_text() -> dict:
        """Read current readable text from the Mac clipboard."""
        debug_live("tool_call", tool="get_clipboard_text")
        async with registry.clipboard_lock:
            result = await asyncio.to_thread(
                registry.clipboard.get_clipboard_text,
            )
        registry._debug_clipboard_result("get_clipboard_text", result)
        return result.to_livekit_dict()

    @function_tool(
        name="set_clipboard_text",
        description=(
            "Remplace le contenu texte du presse-papiers du Mac par le "
            "texte fourni, puis verifie que le texte relu est identique."
        ),
    )
    @registry._desktop_access
    async def set_clipboard_text(text: str) -> dict:
        """Set Mac clipboard text and verify the result."""
        debug_live(
            "tool_call",
            tool="set_clipboard_text",
            length=len(text) if isinstance(text, str) else None,
        )
        async with registry.clipboard_lock:
            result = await asyncio.to_thread(
                registry.clipboard.set_clipboard_text,
                text,
            )
        registry._debug_clipboard_result("set_clipboard_text", result)
        return result.to_livekit_dict()

    @function_tool(
        name="clear_clipboard",
        description=(
            "Efface le texte lisible du presse-papiers du Mac, puis "
            "verifie prudemment qu'aucun texte lisible n'est detecte."
        ),
    )
    @registry._desktop_access
    async def clear_clipboard() -> dict:
        """Clear readable text from the Mac clipboard."""
        debug_live("tool_call", tool="clear_clipboard")
        async with registry.clipboard_lock:
            result = await asyncio.to_thread(
                registry.clipboard.clear_clipboard,
            )
        registry._debug_clipboard_result("clear_clipboard", result)
        return result.to_livekit_dict()

    @function_tool(
        name="rewrite_clipboard",
        description=(
            "Transforme le texte actuellement dans le presse-papiers selon une "
            "instruction (reformuler, corriger les fautes, traduire, resumer, "
            "changer le ton) et remet le resultat dans le presse-papiers pour "
            "que l'utilisateur le colle : 'corrige ce que j'ai copie', 'traduis "
            "ca en anglais', 'reformule plus poliment'. instruction : ce qu'il "
            "faut faire du texte."
        ),
    )
    @registry._journaled("rewrite_clipboard")
    @registry._desktop_access
    async def rewrite_clipboard(instruction: str) -> dict:
        """Transform the clipboard text with the local model."""
        debug_live("tool_call", tool="rewrite_clipboard")
        async with registry.clipboard_lock:
            result = await asyncio.to_thread(
                registry.text_workshop.rewrite_clipboard, instruction,
            )
        registry._debug_tool_result("rewrite_clipboard", result)
        return result.to_livekit_dict()

    @function_tool(
        name="type_text",
        description=(
            "Saisit le texte fourni dans la fenetre macOS actuellement "
            "active. N'appuie jamais automatiquement sur Entree."
        ),
    )
    @registry._desktop_access
    async def type_text(text: str) -> dict:
        """Type text into the currently active macOS window."""
        debug_live(
            "tool_call",
            tool="type_text",
            length=len(text) if isinstance(text, str) else None,
        )
        async with registry.keyboard_lock:
            result = await asyncio.to_thread(registry.keyboard.type_text, text)
        registry._debug_keyboard_result("type_text", result)
        return result.to_livekit_dict()

    @function_tool(
        name="press_key",
        description=(
            "Appuie sur une touche clavier autorisee dans la fenetre "
            "macOS actuellement active : enter, escape, tab, space, "
            "arrow_up, arrow_down, arrow_left ou arrow_right."
        ),
    )
    @registry._desktop_access
    async def press_key(key: str) -> dict:
        """Press one allowed key in the currently active macOS window."""
        debug_live("tool_call", tool="press_key", key=key)
        async with registry.keyboard_lock:
            result = await asyncio.to_thread(registry.keyboard.press_key, key)
        registry._debug_keyboard_result("press_key", result)
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
    @registry._desktop_access
    async def hotkey(keys: list[str]) -> dict:
        """Send one allowed hotkey in the active macOS window."""
        debug_live("tool_call", tool="hotkey", keys=keys)
        async with registry.keyboard_lock:
            result = await asyncio.to_thread(registry.keyboard.hotkey, keys)
        registry._debug_keyboard_result("hotkey", result)
        return result.to_livekit_dict()

    @function_tool(
        name="get_mouse_position",
        description=(
            "Lit la position actuelle reelle du pointeur de souris dans "
            "les coordonnees globales macOS."
        ),
    )
    @registry._desktop_access
    async def get_mouse_position() -> dict:
        """Read the current mouse pointer position."""
        debug_live("tool_call", tool="get_mouse_position")
        async with registry.mouse_lock:
            result = await asyncio.to_thread(registry.mouse.get_mouse_position)
        registry._debug_mouse_result("get_mouse_position", result)
        return result.to_livekit_dict()

    @function_tool(
        name="move_mouse",
        description=(
            "Deplace le pointeur de souris vers des coordonnees macOS "
            "explicites x/y. Ne devine jamais ces coordonnees."
        ),
    )
    @registry._desktop_access
    async def move_mouse(x: int, y: int) -> dict:
        """Move the mouse pointer to explicit macOS coordinates."""
        debug_live("tool_call", tool="move_mouse", x=x, y=y)
        async with registry.mouse_lock:
            result = await asyncio.to_thread(registry.mouse.move_mouse, x, y)
        registry._debug_mouse_result("move_mouse", result)
        return result.to_livekit_dict()

    @function_tool(
        name="click",
        description=(
            "Envoie un clic gauche a la position actuelle du pointeur. "
            "Ce tool ne confirme pas l'effet applicatif du clic."
        ),
    )
    @registry._desktop_access
    async def click() -> dict:
        """Send one left click at the current mouse position."""
        debug_live("tool_call", tool="click")
        async with registry.mouse_lock:
            result = await asyncio.to_thread(registry.mouse.click)
        registry._debug_mouse_result("click", result)
        return result.to_livekit_dict()

    @function_tool(
        name="double_click",
        description=(
            "Envoie un double clic gauche a la position actuelle du "
            "pointeur. Ce tool ne confirme pas l'effet applicatif."
        ),
    )
    @registry._desktop_access
    async def double_click() -> dict:
        """Send one double left click at the current mouse position."""
        debug_live("tool_call", tool="double_click")
        async with registry.mouse_lock:
            result = await asyncio.to_thread(registry.mouse.double_click)
        registry._debug_mouse_result("double_click", result)
        return result.to_livekit_dict()

    @function_tool(
        name="right_click",
        description=(
            "Envoie un clic droit a la position actuelle du pointeur. "
            "Ce tool ne confirme pas l'effet applicatif du clic."
        ),
    )
    @registry._desktop_access
    async def right_click() -> dict:
        """Send one right click at the current mouse position."""
        debug_live("tool_call", tool="right_click")
        async with registry.mouse_lock:
            result = await asyncio.to_thread(registry.mouse.right_click)
        registry._debug_mouse_result("right_click", result)
        return result.to_livekit_dict()

    @function_tool(
        name="scroll",
        description=(
            "Envoie un scroll souris dans une direction explicite : up, "
            "down, left ou right, avec amount entre 1 et 10."
        ),
    )
    @registry._desktop_access
    async def scroll(direction: str, amount: int = 3) -> dict:
        """Send a bounded mouse scroll command."""
        debug_live(
            "tool_call",
            tool="scroll",
            direction=direction,
            amount=amount,
        )
        async with registry.mouse_lock:
            result = await asyncio.to_thread(
                registry.mouse.scroll,
                direction,
                amount,
            )
        registry._debug_mouse_result("scroll", result)
        return result.to_livekit_dict()

    return {
        "get_clipboard_text": get_clipboard_text,
        "set_clipboard_text": set_clipboard_text,
        "clear_clipboard": clear_clipboard,
        "rewrite_clipboard": rewrite_clipboard,
        "type_text": type_text,
        "press_key": press_key,
        "hotkey": hotkey,
        "get_mouse_position": get_mouse_position,
        "move_mouse": move_mouse,
        "click": click,
        "double_click": double_click,
        "right_click": right_click,
        "scroll": scroll,
    }
