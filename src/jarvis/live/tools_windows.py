"""Live tools, family « windows » : Écran (luminosité, verrouillage) et fenêtres.

Part of ToolRegistry.livekit_tools(): `self` is the registry; tools keep its
locks, journal, pending-action store and read-only guard.
"""
from jarvis.live.config import debug_live
from livekit.agents import function_tool
import asyncio


def windows_tools(self) -> dict:
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
        result = await asyncio.to_thread(self.system.get_brightness)
        self._debug_tool_result("get_brightness", result)
        return result.to_livekit_dict()

    @function_tool(
        name="set_brightness",
        description=(
            "Regle la luminosite de l'ecran principal du Mac a une valeur "
            "entiere entre 0 et 100, puis retourne la luminosite observee."
        ),
    )
    @self._journaled("set_brightness")
    async def set_brightness(level: int) -> dict:
        """Set the main display brightness to a value between 0 and 100."""
        debug_live("tool_call", tool="set_brightness", level=level)
        result = await asyncio.to_thread(self.system.set_brightness, level)
        self._debug_tool_result("set_brightness", result)
        return result.to_livekit_dict()

    @function_tool(
        name="lock_screen",
        description=(
            "Verrouille la session du Mac. Utilise ce tool uniquement "
            "quand l'utilisateur demande explicitement de verrouiller son Mac."
        ),
    )
    @self._journaled("lock_screen")
    @self._desktop_access
    async def lock_screen() -> dict:
        """Lock the current Mac session."""
        debug_live("tool_call", tool="lock_screen")
        result = await asyncio.to_thread(self.system.lock_screen)
        self._debug_tool_result("lock_screen", result)
        return result.to_livekit_dict()

    @function_tool(
        name="get_active_window",
        description=(
            "Lit la fenetre active reelle du Mac : application, titre, "
            "position, taille, et etats minimise ou plein ecran."
        ),
    )
    @self._desktop_access
    async def get_active_window() -> dict:
        """Read the currently active Mac window."""
        debug_live("tool_call", tool="get_active_window")
        result = await asyncio.to_thread(self.windows.get_active_window)
        self._debug_tool_result("get_active_window", result)
        return result.to_livekit_dict()

    @function_tool(
        name="focus_window",
        description=(
            "Met au premier plan une fenetre d'application macOS par nom "
            "d'application, puis verifie l'etat observe."
        ),
    )
    @self._journaled("focus_window", "app_name")
    @self._desktop_access
    async def focus_window(app_name: str) -> dict:
        """Focus a macOS application window."""
        debug_live("tool_call", tool="focus_window", app_name=app_name)
        result = await asyncio.to_thread(self.windows.focus_window, app_name)
        self._debug_tool_result("focus_window", result)
        return result.to_livekit_dict()

    @function_tool(
        name="minimize_window",
        description=(
            "Minimise la fenetre active, ou la fenetre d'une application "
            "si app_name est fourni, puis verifie l'etat observe."
        ),
    )
    @self._journaled("minimize_window", "app_name")
    @self._desktop_access
    async def minimize_window(app_name: str | None = None) -> dict:
        """Minimize the active window or an app window."""
        debug_live("tool_call", tool="minimize_window", app_name=app_name)
        result = await asyncio.to_thread(self.windows.minimize_window, app_name)
        self._debug_tool_result("minimize_window", result)
        return result.to_livekit_dict()

    @function_tool(
        name="maximize_window",
        description=(
            "Agrandit la fenetre active, ou la fenetre d'une application "
            "si app_name est fourni, dans le cadre utilisable sans activer "
            "le plein ecran macOS."
        ),
    )
    @self._journaled("maximize_window", "app_name")
    @self._desktop_access
    async def maximize_window(app_name: str | None = None) -> dict:
        """Maximize the active window or an app window without fullscreen."""
        debug_live("tool_call", tool="maximize_window", app_name=app_name)
        result = await asyncio.to_thread(self.windows.maximize_window, app_name)
        self._debug_tool_result("maximize_window", result)
        return result.to_livekit_dict()

    @function_tool(
        name="move_window",
        description=(
            "Deplace la fenetre active, ou la fenetre d'une application "
            "si app_name est fourni. position accepte uniquement left, "
            "right, center ou fullscreen."
        ),
    )
    @self._journaled("move_window", "app_name")
    @self._desktop_access
    async def move_window(position: str, app_name: str | None = None) -> dict:
        """Move the active window or an app window."""
        debug_live(
            "tool_call",
            tool="move_window",
            position=position,
            app_name=app_name,
        )
        result = await asyncio.to_thread(
            self.windows.move_window,
            position,
            app_name,
        )
        self._debug_tool_result("move_window", result)
        return result.to_livekit_dict()

    @function_tool(
        name="arrange_windows",
        description=(
            "Place deux applications cote a cote : la premiere sur la moitie "
            "gauche de l'ecran, la seconde sur la moitie droite ('mets Safari a "
            "gauche et Notes a droite', 'range ces deux fenetres'). left_app et "
            "right_app : les noms des applications."
        ),
    )
    @self._desktop_access
    async def arrange_windows(left_app: str, right_app: str) -> dict:
        """Tile two apps side by side."""
        debug_live("tool_call", tool="arrange_windows")
        result = await asyncio.to_thread(
            self.windows.arrange_side_by_side, left_app, right_app,
        )
        self._debug_tool_result("arrange_windows", result)
        return result.to_livekit_dict()

    return {
        "get_brightness": get_brightness,
        "set_brightness": set_brightness,
        "lock_screen": lock_screen,
        "get_active_window": get_active_window,
        "focus_window": focus_window,
        "minimize_window": minimize_window,
        "maximize_window": maximize_window,
        "move_window": move_window,
        "arrange_windows": arrange_windows,
    }
