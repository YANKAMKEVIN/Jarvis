import asyncio
from typing import Any

from livekit.agents import function_tool

from jarvis.capabilities.apps import AppCapability
from jarvis.capabilities.audio import AudioCapability
from jarvis.capabilities.media import MediaCapability
from jarvis.capabilities.system import SystemCapability
from jarvis.capabilities.windows import WindowCapability
from jarvis.live.config import debug_live


class ToolRegistry:
    def __init__(
        self,
        audio_capability=None,
        app_capability=None,
        media_capability=None,
        system_capability=None,
        window_capability=None,
    ):
        self.audio = (
            audio_capability
            if audio_capability is not None
            else AudioCapability()
        )
        self.apps = (
            app_capability
            if app_capability is not None
            else AppCapability()
        )
        self.media = (
            media_capability
            if media_capability is not None
            else MediaCapability()
        )
        self.system = (
            system_capability
            if system_capability is not None
            else SystemCapability()
        )
        self.windows = (
            window_capability
            if window_capability is not None
            else WindowCapability()
        )
        self.media_lock = asyncio.Lock()

    def livekit_tools(self) -> list[Any]:
        @function_tool(
            name="set_volume",
            description=(
                "Modifie réellement le volume de sortie du Mac de l'utilisateur. "
                "Utilise ce tool quand l'utilisateur demande de mettre, régler, "
                "monter ou baisser le volume à un niveau précis entre 0 et 100."
            ),
        )
        async def set_volume(volume: int) -> dict:
            """Set the Mac output volume to a value between 0 and 100."""
            debug_live("tool_call", tool="set_volume", volume=volume)
            result = await asyncio.to_thread(self.audio.set_volume, volume)

            if result.ok:
                debug_live(
                    "tool_succeeded",
                    tool="set_volume",
                    volume=result.data.get("volume"),
                )
            else:
                debug_live(
                    "tool_failed",
                    tool="set_volume",
                    error=result.error_code,
                )

            return result.to_livekit_dict()

        @function_tool(
            name="get_volume",
            description=(
                "Lit le volume de sortie actuel du Mac de l'utilisateur. "
                "Utilise ce tool quand l'utilisateur demande le volume actuel."
            ),
        )
        async def get_volume() -> dict:
            """Read the current Mac output volume."""
            debug_live("tool_call", tool="get_volume")
            result = await asyncio.to_thread(self.audio.get_volume)

            if result.ok:
                debug_live(
                    "tool_succeeded",
                    tool="get_volume",
                    volume=result.data.get("volume"),
                )
            else:
                debug_live(
                    "tool_failed",
                    tool="get_volume",
                    error=result.error_code,
                )

            return result.to_livekit_dict()

        @function_tool(
            name="open_app",
            description=(
                "Ouvre réellement une application macOS par son nom exact. "
                "Utilise ce tool quand l'utilisateur demande d'ouvrir, lancer "
                "ou démarrer une application comme Safari, Spotify ou "
                "Visual Studio Code."
            ),
        )
        async def open_app(app_name: str) -> dict:
            """Open a macOS application by name."""
            debug_live("tool_call", tool="open_app", app_name=app_name)
            result = await asyncio.to_thread(self.apps.open_app, app_name)

            if result.ok:
                debug_live(
                    "tool_succeeded",
                    tool="open_app",
                    target=result.data.get("target"),
                )
            else:
                debug_live(
                    "tool_failed",
                    tool="open_app",
                    error=result.error_code,
                )

            return result.to_livekit_dict()

        @function_tool(
            name="close_app",
            description=(
                "Ferme réellement une application macOS par son nom exact. "
                "Utilise ce tool quand l'utilisateur demande de fermer, "
                "quitter ou arrêter une application."
            ),
        )
        async def close_app(app_name: str) -> dict:
            """Close a macOS application by name."""
            debug_live("tool_call", tool="close_app", app_name=app_name)
            result = await asyncio.to_thread(self.apps.close_app, app_name)

            if result.ok:
                debug_live(
                    "tool_succeeded",
                    tool="close_app",
                    target=result.data.get("target"),
                )
            else:
                debug_live(
                    "tool_failed",
                    tool="close_app",
                    error=result.error_code,
                )

            return result.to_livekit_dict()

        @function_tool(
            name="is_app_running",
            description=(
                "Vérifie si une application macOS est actuellement ouverte "
                "ou en cours d'exécution. Utilise ce tool quand l'utilisateur "
                "demande si une application est ouverte, lancée ou tourne."
            ),
        )
        async def is_app_running(app_name: str) -> dict:
            """Check whether a macOS application is currently running."""
            debug_live("tool_call", tool="is_app_running", app_name=app_name)
            result = await asyncio.to_thread(
                self.apps.is_app_running,
                app_name,
            )

            if result.ok:
                debug_live(
                    "tool_succeeded",
                    tool="is_app_running",
                    target=result.data.get("target"),
                    running=result.data.get("running"),
                )
            else:
                debug_live(
                    "tool_failed",
                    tool="is_app_running",
                    error=result.error_code,
                )

            return result.to_livekit_dict()

        @function_tool(
            name="play_pause",
            description=(
                "Met en pause ou reprend la lecture du média actif compatible "
                "sur le Mac. Utilise ce tool pour les demandes comme pause, "
                "reprends la lecture, play ou mets la musique en pause."
            ),
        )
        async def play_pause() -> dict:
            """Toggle play/pause for the active supported media app."""
            debug_live("tool_call", tool="play_pause")
            async with self.media_lock:
                result = await asyncio.to_thread(self.media.play_pause)
            self._debug_tool_result("play_pause", result)
            return result.to_livekit_dict()

        @function_tool(
            name="next_track",
            description=(
                "Passe au morceau suivant dans l'application média compatible "
                "active. Utilise ce tool quand l'utilisateur demande la "
                "suivante, le titre suivant ou de passer au prochain morceau."
            ),
        )
        async def next_track() -> dict:
            """Skip to the next track in the active supported media app."""
            debug_live("tool_call", tool="next_track")
            async with self.media_lock:
                result = await asyncio.to_thread(self.media.next_track)
            self._debug_tool_result("next_track", result)
            return result.to_livekit_dict()

        @function_tool(
            name="previous_track",
            description=(
                "Revient au morceau précédent dans l'application média "
                "compatible active. Utilise ce tool quand l'utilisateur "
                "demande la chanson précédente ou de revenir en arrière."
            ),
        )
        async def previous_track() -> dict:
            """Go back to the previous track in the active supported media app."""
            debug_live("tool_call", tool="previous_track")
            async with self.media_lock:
                result = await asyncio.to_thread(self.media.previous_track)
            self._debug_tool_result("previous_track", result)
            return result.to_livekit_dict()

        @function_tool(
            name="get_media_state",
            description=(
                "Lit l'état réel du média actif compatible sur le Mac. "
                "Utilise ce tool quand l'utilisateur demande ce qui joue, "
                "quel morceau est en cours ou si la lecture est active."
            ),
        )
        async def get_media_state() -> dict:
            """Read the current supported media playback state."""
            debug_live("tool_call", tool="get_media_state")
            async with self.media_lock:
                result = await asyncio.to_thread(self.media.get_media_state)
            self._debug_tool_result("get_media_state", result)
            return result.to_livekit_dict()

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
            result = await asyncio.to_thread(self.system.get_battery_status)
            self._debug_tool_result("get_battery_status", result)
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
            result = await asyncio.to_thread(self.system.get_system_info)
            self._debug_tool_result("get_system_info", result)
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

        return [
            set_volume,
            get_volume,
            open_app,
            close_app,
            is_app_running,
            play_pause,
            next_track,
            previous_track,
            get_media_state,
            get_battery_status,
            get_system_info,
            get_brightness,
            set_brightness,
            lock_screen,
            get_active_window,
            focus_window,
            minimize_window,
            maximize_window,
            move_window,
        ]

    @staticmethod
    def _debug_tool_result(tool_name: str, result) -> None:
        if result.ok:
            debug_live(
                "tool_succeeded",
                tool=tool_name,
                app=result.data.get("app"),
                title=result.data.get("title"),
                playing=result.data.get("playing"),
            )
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                error=result.error_code,
            )


def create_live_tools(
    security=None,
    macos_tools=None,
    audio_capability=None,
    app_capability=None,
    media_capability=None,
    system_capability=None,
    window_capability=None,
) -> list[Any]:
    if audio_capability is None:
        audio_capability = AudioCapability(
            security=security,
            macos_tools=macos_tools,
        )

    if app_capability is None:
        app_capability = AppCapability(
            security=security,
            macos_tools=macos_tools,
        )

    if media_capability is None:
        media_capability = MediaCapability(
            security=security,
            macos_tools=macos_tools,
        )

    if system_capability is None:
        system_capability = SystemCapability(
            security=security,
            macos_tools=macos_tools,
        )

    if window_capability is None:
        window_capability = WindowCapability(
            security=security,
            macos_tools=macos_tools,
        )

    return ToolRegistry(
        audio_capability=audio_capability,
        app_capability=app_capability,
        media_capability=media_capability,
        system_capability=system_capability,
        window_capability=window_capability,
    ).livekit_tools()
