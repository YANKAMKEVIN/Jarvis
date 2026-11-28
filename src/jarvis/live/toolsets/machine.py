"""Machine status, shortcuts, calculation, brightness and screen lock tools.

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
        name="get_battery_status",
        description=(
            "Lit l'etat reel de la batterie du Mac : pourcentage, charge "
            "en cours et alimentation secteur."
        ),
    )
    async def get_battery_status() -> dict:
        """Read the current Mac battery status."""
        debug_live("tool_call", tool="get_battery_status")
        result = await asyncio.to_thread(registry.system.get_battery_status)
        registry._debug_tool_result("get_battery_status", result)
        return result.to_livekit_dict()

    @function_tool(
        name="get_system_info",
        description=(
            "Lit les informations materielles reelles du Mac utilise, "
            "comme le modele, l'identifiant modele, la puce et la memoire."
        ),
    )
    async def get_system_info() -> dict:
        """Read current Mac hardware information."""
        debug_live("tool_call", tool="get_system_info")
        result = await asyncio.to_thread(registry.system.get_system_info)
        registry._debug_tool_result("get_system_info", result)
        return result.to_livekit_dict()

    @function_tool(
        name="get_storage_status",
        description=(
            "Lit l'espace disque reel du Mac (libre, utilise, total) et signale "
            "si l'espace est faible. Utilise ce tool pour 'combien de place il me "
            "reste', 'mon disque est-il plein'."
        ),
    )
    async def get_storage_status() -> dict:
        """Read current disk space."""
        debug_live("tool_call", tool="get_storage_status")
        result = await asyncio.to_thread(registry.system.get_storage_status)
        registry._debug_tool_result("get_storage_status", result)
        return result.to_livekit_dict()

    @function_tool(
        name="self_check",
        description=(
            "Diagnostic : indique quelles capacites et permissions sont "
            "disponibles (accessibilite, enregistrement d'ecran, vision, modele "
            "local Ollama, IMAP) et ce qui manque, avec une piste de correction. "
            "Pour 'fais un check', 'qu'est-ce qui fonctionne', 'tes permissions'."
        ),
    )
    async def self_check() -> dict:
        """Report available capabilities and permissions."""
        debug_live("tool_call", tool="self_check")
        result = await asyncio.to_thread(registry.diagnostics.self_check)
        return result.to_livekit_dict()

    @function_tool(
        name="run_shortcut",
        description=(
            "Lance un Raccourci (Shortcuts) macOS par son nom : 'active Ne pas "
            "deranger', 'lance mon raccourci Focus travail'. C'est le moyen "
            "fiable d'activer des automatisations que l'utilisateur a creees "
            "(Focus/DND, luminosite, etc.). name : le nom exact du raccourci. "
            "Utilise list_shortcuts si tu n'es pas sur du nom."
        ),
    )
    @registry._journaled("run_shortcut", "name")
    @registry._desktop_access
    async def run_shortcut(name: str) -> dict:
        """Run a macOS Shortcut by name."""
        debug_live("tool_call", tool="run_shortcut")
        result = await asyncio.to_thread(registry.shortcuts.run_shortcut, name)
        registry._debug_tool_result("run_shortcut", result)
        return result.to_livekit_dict()

    @function_tool(
        name="list_shortcuts",
        description=(
            "Liste les Raccourcis (Shortcuts) macOS disponibles, par leur nom. "
            "Pour 'quels raccourcis j'ai', ou pour trouver le bon nom avant "
            "run_shortcut."
        ),
    )
    async def list_shortcuts() -> dict:
        """List available macOS Shortcuts."""
        debug_live("tool_call", tool="list_shortcuts")
        result = await asyncio.to_thread(registry.shortcuts.list_shortcuts)
        registry._debug_tool_result("list_shortcuts", result)
        return result.to_livekit_dict()

    @function_tool(
        name="calculate",
        description=(
            "Calcule une expression arithmetique en local (de maniere sure) : "
            "'combien font 15% de 240', '(12+8)*3', 'racine de 2'. expression : "
            "l'expression mathematique (nombres, + - * / %, puissance **, "
            "parentheses, fonctions sqrt/log/sin/cos/min/max, constantes pi/e)."
        ),
    )
    async def calculate(expression: str) -> dict:
        """Evaluate a safe arithmetic expression locally."""
        debug_live("tool_call", tool="calculate")
        result = await asyncio.to_thread(registry.compute.calculate, expression)
        registry._debug_tool_result("calculate", result)
        return result.to_livekit_dict()

    @function_tool(
        name="convert_units",
        description=(
            "Convertit une valeur entre unites (longueur, masse, volume, "
            "temperature) en local : 'convertis 10 km en miles', '180 livres en "
            "kg', '72 F en C'. value : le nombre ; from_unit et to_unit : les "
            "unites (km, mi, kg, lb, l, gal, C, F, K...). Pas de devises."
        ),
    )
    async def convert_units(value: float, from_unit: str, to_unit: str) -> dict:
        """Convert a value between units locally."""
        debug_live("tool_call", tool="convert_units")
        result = await asyncio.to_thread(
            registry.compute.convert_units, value, from_unit, to_unit,
        )
        registry._debug_tool_result("convert_units", result)
        return result.to_livekit_dict()

    @function_tool(
        name="get_brightness",
        description=(
            "Lit la luminosite actuelle de l'ecran principal du Mac. "
            "Utilise ce tool quand l'utilisateur demande la luminosite actuelle."
        ),
    )
    async def get_brightness() -> dict:
        """Read the current main display brightness."""
        debug_live("tool_call", tool="get_brightness")
        result = await asyncio.to_thread(registry.system.get_brightness)
        registry._debug_tool_result("get_brightness", result)
        return result.to_livekit_dict()

    @function_tool(
        name="set_brightness",
        description=(
            "Regle la luminosite de l'ecran principal du Mac a une valeur "
            "entiere entre 0 et 100, puis retourne la luminosite observee."
        ),
    )
    @registry._journaled("set_brightness")
    async def set_brightness(level: int) -> dict:
        """Set the main display brightness to a value between 0 and 100."""
        debug_live("tool_call", tool="set_brightness", level=level)
        result = await asyncio.to_thread(registry.system.set_brightness, level)
        registry._debug_tool_result("set_brightness", result)
        return result.to_livekit_dict()

    @function_tool(
        name="lock_screen",
        description=(
            "Verrouille la session du Mac. Utilise ce tool uniquement "
            "quand l'utilisateur demande explicitement de verrouiller son Mac."
        ),
    )
    @registry._journaled("lock_screen")
    @registry._desktop_access
    async def lock_screen() -> dict:
        """Lock the current Mac session."""
        debug_live("tool_call", tool="lock_screen")
        result = await asyncio.to_thread(registry.system.lock_screen)
        registry._debug_tool_result("lock_screen", result)
        return result.to_livekit_dict()

    return {
        "get_battery_status": get_battery_status,
        "get_system_info": get_system_info,
        "get_storage_status": get_storage_status,
        "self_check": self_check,
        "run_shortcut": run_shortcut,
        "list_shortcuts": list_shortcuts,
        "calculate": calculate,
        "convert_units": convert_units,
        "get_brightness": get_brightness,
        "set_brightness": set_brightness,
        "lock_screen": lock_screen,
    }
