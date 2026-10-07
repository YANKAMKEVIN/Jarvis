import asyncio
from typing import Any

from livekit.agents import function_tool

from jarvis.capabilities.apps import AppCapability
from jarvis.capabilities.audio import AudioCapability
from jarvis.capabilities.browser import BrowserCapability
from jarvis.capabilities.clipboard import ClipboardCapability
from jarvis.capabilities.files import FilesCapability
from jarvis.capabilities.interaction import InteractionCapability
from jarvis.capabilities.keyboard import KeyboardCapability
from jarvis.capabilities.media import MediaCapability
from jarvis.capabilities.mouse import MouseCapability
from jarvis.capabilities.screenshot import ScreenshotCapability
from jarvis.capabilities.system import SystemCapability
from jarvis.capabilities.ui_accessibility import UIAccessibilityCapability
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
        files_capability=None,
        clipboard_capability=None,
        keyboard_capability=None,
        mouse_capability=None,
        ui_accessibility_capability=None,
        interaction_capability=None,
        browser_capability=None,
        screenshot_capability=None,
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
        self.files = (
            files_capability
            if files_capability is not None
            else FilesCapability()
        )
        self.clipboard = (
            clipboard_capability
            if clipboard_capability is not None
            else ClipboardCapability()
        )
        self.keyboard = (
            keyboard_capability
            if keyboard_capability is not None
            else KeyboardCapability()
        )
        self.mouse = (
            mouse_capability
            if mouse_capability is not None
            else MouseCapability()
        )
        self.ui_accessibility = (
            ui_accessibility_capability
            if ui_accessibility_capability is not None
            else UIAccessibilityCapability()
        )
        self.interaction = (
            interaction_capability
            if interaction_capability is not None
            else InteractionCapability(
                apps=self.apps,
                windows=self.windows,
                ui_accessibility=self.ui_accessibility,
                keyboard=self.keyboard,
                clipboard=self.clipboard,
            )
        )
        self.browser = (
            browser_capability
            if browser_capability is not None
            else BrowserCapability()
        )
        self.screenshot = (
            screenshot_capability
            if screenshot_capability is not None
            else ScreenshotCapability()
        )
        self.media_lock = asyncio.Lock()
        self.clipboard_lock = asyncio.Lock()
        self.keyboard_lock = asyncio.Lock()
        self.mouse_lock = asyncio.Lock()
        self.ui_lock = asyncio.Lock()
        self.interaction_lock = asyncio.Lock()
        self.browser_lock = asyncio.Lock()
        self.screenshot_lock = asyncio.Lock()

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

        @function_tool(
            name="list_files",
            description=(
                "Liste les fichiers et dossiers d'un chemin local macOS. "
                "Utilise ce tool pour connaitre le contenu actuel d'un dossier."
            ),
        )
        async def list_files(path: str | None = None) -> dict:
            """List files in a local folder."""
            debug_live("tool_call", tool="list_files", path=path)
            result = await asyncio.to_thread(self.files.list_files, path)
            self._debug_tool_result("list_files", result)
            return result.to_livekit_dict()

        @function_tool(
            name="find_files",
            description=(
                "Recherche de maniere bornee des fichiers ou dossiers locaux "
                "par nom, correspondance partielle ou extension."
            ),
        )
        async def find_files(query: str, path: str | None = None) -> dict:
            """Find files or folders by name in a local folder."""
            debug_live("tool_call", tool="find_files", query=query, path=path)
            result = await asyncio.to_thread(self.files.find_files, query, path)
            self._debug_tool_result("find_files", result)
            return result.to_livekit_dict()

        @function_tool(
            name="get_file_info",
            description=(
                "Lit les informations actuelles d'un fichier ou dossier local : "
                "type, taille, date de modification et chemin absolu."
            ),
        )
        async def get_file_info(path: str) -> dict:
            """Read metadata for a local file or folder."""
            debug_live("tool_call", tool="get_file_info", path=path)
            result = await asyncio.to_thread(self.files.get_file_info, path)
            self._debug_tool_result("get_file_info", result)
            return result.to_livekit_dict()

        @function_tool(
            name="open_file",
            description=(
                "Ouvre un fichier local avec l'application macOS associee. "
                "Le chemin doit etre exact, idealement un chemin absolu retourne "
                "par un tool Files."
            ),
        )
        async def open_file(path: str) -> dict:
            """Open a local file with macOS."""
            debug_live("tool_call", tool="open_file", path=path)
            result = await asyncio.to_thread(self.files.open_file, path)
            self._debug_tool_result("open_file", result)
            return result.to_livekit_dict()

        @function_tool(
            name="open_folder",
            description=(
                "Ouvre un dossier local dans Finder. Le chemin doit etre exact, "
                "idealement un chemin absolu retourne par un tool Files."
            ),
        )
        async def open_folder(path: str) -> dict:
            """Open a local folder in Finder."""
            debug_live("tool_call", tool="open_folder", path=path)
            result = await asyncio.to_thread(self.files.open_folder, path)
            self._debug_tool_result("open_folder", result)
            return result.to_livekit_dict()

        @function_tool(
            name="create_folder",
            description=(
                "Cree un dossier local sans ecraser de chemin existant, puis "
                "verifie son existence."
            ),
        )
        async def create_folder(path: str) -> dict:
            """Create a local folder without overwriting."""
            debug_live("tool_call", tool="create_folder", path=path)
            result = await asyncio.to_thread(self.files.create_folder, path)
            self._debug_tool_result("create_folder", result)
            return result.to_livekit_dict()

        @function_tool(
            name="rename_file",
            description=(
                "Renomme un fichier ou dossier local sans ecraser une destination "
                "existante, puis verifie le resultat."
            ),
        )
        async def rename_file(path: str, new_name: str) -> dict:
            """Rename a local file or folder without overwriting."""
            debug_live(
                "tool_call",
                tool="rename_file",
                path=path,
                new_name=new_name,
            )
            result = await asyncio.to_thread(
                self.files.rename_file,
                path,
                new_name,
            )
            self._debug_tool_result("rename_file", result)
            return result.to_livekit_dict()

        @function_tool(
            name="move_file",
            description=(
                "Deplace un fichier ou dossier local vers une destination exacte "
                "sans jamais ecraser de chemin existant."
            ),
        )
        async def move_file(source: str, destination: str) -> dict:
            """Move a local file or folder without overwriting."""
            debug_live(
                "tool_call",
                tool="move_file",
                source=source,
                destination=destination,
            )
            result = await asyncio.to_thread(
                self.files.move_file,
                source,
                destination,
            )
            self._debug_tool_result("move_file", result)
            return result.to_livekit_dict()

        @function_tool(
            name="get_clipboard_text",
            description=(
                "Lit le texte actuellement disponible dans le presse-papiers "
                "du Mac. Utilise ce tool pour savoir ce qui a ete copie ou "
                "si le presse-papiers contient du texte."
            ),
        )
        async def get_clipboard_text() -> dict:
            """Read current readable text from the Mac clipboard."""
            debug_live("tool_call", tool="get_clipboard_text")
            async with self.clipboard_lock:
                result = await asyncio.to_thread(
                    self.clipboard.get_clipboard_text,
                )
            self._debug_clipboard_result("get_clipboard_text", result)
            return result.to_livekit_dict()

        @function_tool(
            name="set_clipboard_text",
            description=(
                "Remplace le contenu texte du presse-papiers du Mac par le "
                "texte fourni, puis verifie que le texte relu est identique."
            ),
        )
        async def set_clipboard_text(text: str) -> dict:
            """Set Mac clipboard text and verify the result."""
            debug_live(
                "tool_call",
                tool="set_clipboard_text",
                length=len(text) if isinstance(text, str) else None,
            )
            async with self.clipboard_lock:
                result = await asyncio.to_thread(
                    self.clipboard.set_clipboard_text,
                    text,
                )
            self._debug_clipboard_result("set_clipboard_text", result)
            return result.to_livekit_dict()

        @function_tool(
            name="clear_clipboard",
            description=(
                "Efface le texte lisible du presse-papiers du Mac, puis "
                "verifie prudemment qu'aucun texte lisible n'est detecte."
            ),
        )
        async def clear_clipboard() -> dict:
            """Clear readable text from the Mac clipboard."""
            debug_live("tool_call", tool="clear_clipboard")
            async with self.clipboard_lock:
                result = await asyncio.to_thread(
                    self.clipboard.clear_clipboard,
                )
            self._debug_clipboard_result("clear_clipboard", result)
            return result.to_livekit_dict()

        @function_tool(
            name="type_text",
            description=(
                "Saisit le texte fourni dans la fenetre macOS actuellement "
                "active. N'appuie jamais automatiquement sur Entree."
            ),
        )
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
            name="select_all_and_copy",
            description=(
                "Selectionne tout puis copie dans la fenetre active avec une "
                "sequence mecanique command+a puis command+c. Utilise ce tool "
                "pour les demandes naturelles comme selectionne tout et copie."
            ),
        )
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
            async with self.browser_lock:
                result = await asyncio.to_thread(
                    self.browser.open_url,
                    url,
                    browser,
                    new_tab,
                )
            self._debug_browser_result("browse_open_url", result)
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
            async with self.browser_lock:
                result = await asyncio.to_thread(
                    self.browser.search_web,
                    query,
                    browser,
                    engine,
                )
            self._debug_browser_result("browse_search_web", result)
            return result.to_livekit_dict()

        @function_tool(
            name="browse_get_active_tab",
            description=(
                "Lit l'onglet actif (URL et titre) de Safari ou Google Chrome. "
                "Utilise ce tool pour savoir quelle page est affichee au lieu de "
                "le deduire. browser=None choisit automatiquement le navigateur."
            ),
        )
        async def browse_get_active_tab(browser: str | None = None) -> dict:
            """Read the active tab of a browser."""
            debug_live("tool_call", tool="browse_get_active_tab", browser=browser)
            async with self.browser_lock:
                result = await asyncio.to_thread(
                    self.browser.get_active_tab,
                    browser,
                )
            self._debug_browser_result("browse_get_active_tab", result)
            return result.to_livekit_dict()

        @function_tool(
            name="browse_list_tabs",
            description=(
                "Liste les onglets ouverts (index, URL, titre) de la fenetre "
                "active de Safari ou Google Chrome. Utile avant d'activer un "
                "onglet precis. browser=None choisit automatiquement."
            ),
        )
        async def browse_list_tabs(browser: str | None = None) -> dict:
            """List the tabs of a browser's front window."""
            debug_live("tool_call", tool="browse_list_tabs", browser=browser)
            async with self.browser_lock:
                result = await asyncio.to_thread(
                    self.browser.list_tabs,
                    browser,
                )
            self._debug_browser_result("browse_list_tabs", result)
            return result.to_livekit_dict()

        @function_tool(
            name="browse_activate_tab",
            description=(
                "Active l'onglet dont l'URL ou le titre contient query, dans "
                "Safari ou Google Chrome, puis verifie qu'il est au premier plan. "
                "Si plusieurs onglets correspondent, retourne ambiguous_tab sans "
                "choisir : demande une precision. browser=None choisit "
                "automatiquement."
            ),
        )
        async def browse_activate_tab(
            query: str,
            browser: str | None = None,
        ) -> dict:
            """Activate the single tab matching query, then verify it."""
            debug_live(
                "tool_call",
                tool="browse_activate_tab",
                browser=browser,
                query_length=len(query) if isinstance(query, str) else None,
            )
            async with self.browser_lock:
                result = await asyncio.to_thread(
                    self.browser.activate_tab,
                    query,
                    browser,
                )
            self._debug_browser_result("browse_activate_tab", result)
            return result.to_livekit_dict()

        @function_tool(
            name="capture_screen",
            description=(
                "Prend une capture d'ecran complete et l'enregistre dans un "
                "fichier PNG, puis relit le fichier pour confirmer "
                "l'enregistrement. Utilise ce tool quand l'utilisateur demande "
                "une capture d'ecran. path=None genere un nom horodate dans le "
                "dossier des captures ; display cible un ecran precis (1 par "
                "defaut). state_confirmed=true seulement si le fichier existe et "
                "n'est pas vide. Le resultat ne contient pas l'image, seulement "
                "son chemin et sa taille."
            ),
        )
        async def capture_screen(
            path: str | None = None,
            display: int | None = None,
        ) -> dict:
            """Capture the full screen to a PNG file and verify it."""
            debug_live("tool_call", tool="capture_screen", display=display)
            async with self.screenshot_lock:
                result = await asyncio.to_thread(
                    self.screenshot.capture_screen,
                    path,
                    display,
                )
            self._debug_screenshot_result("capture_screen", result)
            return result.to_livekit_dict()

        @function_tool(
            name="capture_region",
            description=(
                "Prend une capture d'une region rectangulaire de l'ecran "
                "(x, y, largeur, hauteur en points, origine en haut a gauche) et "
                "l'enregistre en PNG, puis verifie le fichier. N'invente jamais "
                "de coordonnees : utilise ce tool uniquement avec une region "
                "fournie par l'utilisateur ou par un tool fiable. state_confirmed "
                "=true seulement si le fichier a bien ete ecrit."
            ),
        )
        async def capture_region(
            x: int,
            y: int,
            width: int,
            height: int,
            path: str | None = None,
        ) -> dict:
            """Capture a rectangular region to a PNG file and verify it."""
            debug_live(
                "tool_call",
                tool="capture_region",
                width=width,
                height=height,
            )
            async with self.screenshot_lock:
                result = await asyncio.to_thread(
                    self.screenshot.capture_region,
                    x,
                    y,
                    width,
                    height,
                    path,
                )
            self._debug_screenshot_result("capture_region", result)
            return result.to_livekit_dict()

        @function_tool(
            name="capture_window",
            description=(
                "Prend une capture de la fenetre active, ou de la fenetre d'une "
                "application nommee (elle est d'abord mise au premier plan et "
                "verifiee), puis enregistre un PNG et relit le fichier. Utilise ce "
                "tool pour capturer une fenetre precise. Si la fenetre active ne "
                "correspond pas a l'application demandee, la capture est arretee "
                "(active_window_mismatch)."
            ),
        )
        async def capture_window(
            app_name: str | None = None,
            path: str | None = None,
        ) -> dict:
            """Capture the active or a named window to a PNG file and verify it."""
            debug_live("tool_call", tool="capture_window", app_name=app_name)
            async with self.screenshot_lock:
                result = await asyncio.to_thread(
                    self.screenshot.capture_window,
                    app_name,
                    path,
                )
            self._debug_screenshot_result("capture_window", result)
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
            list_files,
            find_files,
            get_file_info,
            open_file,
            open_folder,
            create_folder,
            rename_file,
            move_file,
            get_clipboard_text,
            set_clipboard_text,
            clear_clipboard,
            type_text,
            press_key,
            hotkey,
            get_mouse_position,
            move_mouse,
            click,
            double_click,
            right_click,
            scroll,
            inspect_ui,
            find_ui_elements,
            focus_ui_element,
            activate_ui_element,
            select_all_and_copy,
            focus_app_ui_and_type,
            open_app_and_focus_ui,
            select_all_and_delete,
            browse_open_url,
            browse_search_web,
            browse_get_active_tab,
            browse_list_tabs,
            browse_activate_tab,
            capture_screen,
            capture_region,
            capture_window,
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

    @staticmethod
    def _debug_clipboard_result(tool_name: str, result) -> None:
        fields = {
            "tool": tool_name,
            "has_text": result.data.get("has_text"),
            "length": result.data.get("length"),
            "returned_length": result.data.get("returned_length"),
            "truncated": result.data.get("truncated"),
            "content_type": result.data.get("content_type"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                error=result.error_code,
            )

    @staticmethod
    def _debug_keyboard_result(tool_name: str, result) -> None:
        fields = {
            "tool": tool_name,
            "length": result.data.get("length"),
            "key": result.data.get("key"),
            "keys": result.data.get("keys"),
            "target_app": result.data.get("target_app"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                error=result.error_code,
            )

    @staticmethod
    def _debug_mouse_result(tool_name: str, result) -> None:
        fields = {
            "tool": tool_name,
            "x": result.data.get("x"),
            "y": result.data.get("y"),
            "direction": result.data.get("direction"),
            "amount": result.data.get("amount"),
            "button": result.data.get("button"),
            "click_count": result.data.get("click_count"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                error=result.error_code,
            )

    @staticmethod
    def _debug_ui_result(tool_name: str, result) -> None:
        fields = {
            "tool": tool_name,
            "count": result.data.get("count"),
            "truncated": result.data.get("truncated"),
            "role": result.data.get("role"),
            "query_length": result.data.get("query_length"),
            "candidate_count": result.data.get("candidate_count"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                error=result.error_code,
            )

    @staticmethod
    def _debug_interaction_result(tool_name: str, result) -> None:
        fields = {
            "tool": tool_name,
            "target_app": result.data.get("target_app"),
            "query_length": result.data.get("query_length"),
            "text_length": result.data.get("text_length"),
            "press_enter": result.data.get("press_enter"),
            "failed_step": result.data.get("failed_step"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
            "step_count": len(result.data.get("steps", [])),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                error=result.error_code,
                failed_step=result.data.get("failed_step"),
            )

    @staticmethod
    def _debug_browser_result(tool_name: str, result) -> None:
        # Log host and counts only; never the full URL or page title.
        fields = {
            "tool": tool_name,
            "browser": result.data.get("browser"),
            "active_host": ToolRegistry._debug_host(result.data.get("active_url")),
            "has_window": result.data.get("has_window"),
            "tab_count": result.data.get("count"),
            "new_tab": result.data.get("new_tab"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                browser=result.data.get("browser"),
                error=result.error_code,
            )

    @staticmethod
    def _debug_host(url) -> str | None:
        if not isinstance(url, str) or not url:
            return None

        from urllib.parse import urlparse

        return urlparse(url).netloc or None

    @staticmethod
    def _debug_screenshot_result(tool_name: str, result) -> None:
        # Log the file basename and metadata only, never the full path.
        import os as _os

        path = result.data.get("path")
        fields = {
            "tool": tool_name,
            "file": _os.path.basename(path) if isinstance(path, str) else None,
            "bytes": result.data.get("bytes"),
            "width": result.data.get("width"),
            "height": result.data.get("height"),
            "target_app": result.data.get("target_app"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live("tool_failed", tool=tool_name, error=result.error_code)


def create_live_tools(
    security=None,
    macos_tools=None,
    filesystem_tools=None,
    clipboard_tools=None,
    keyboard_tools=None,
    mouse_tools=None,
    accessibility_tools=None,
    audio_capability=None,
    app_capability=None,
    media_capability=None,
    system_capability=None,
    window_capability=None,
    files_capability=None,
    clipboard_capability=None,
    keyboard_capability=None,
    mouse_capability=None,
    ui_accessibility_capability=None,
    interaction_capability=None,
    browser_capability=None,
    screenshot_capability=None,
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

    if files_capability is None:
        files_capability = FilesCapability(
            security=security,
            filesystem_tools=filesystem_tools,
        )

    if clipboard_capability is None:
        clipboard_capability = ClipboardCapability(
            security=security,
            clipboard_tools=clipboard_tools,
        )

    if keyboard_capability is None:
        keyboard_capability = KeyboardCapability(
            security=security,
            keyboard_tools=keyboard_tools,
        )

    if mouse_capability is None:
        mouse_capability = MouseCapability(
            security=security,
            mouse_tools=mouse_tools,
        )

    if ui_accessibility_capability is None:
        ui_accessibility_capability = UIAccessibilityCapability(
            security=security,
            accessibility_tools=accessibility_tools,
        )

    if interaction_capability is None:
        interaction_capability = InteractionCapability(
            apps=app_capability,
            windows=window_capability,
            ui_accessibility=ui_accessibility_capability,
            keyboard=keyboard_capability,
            clipboard=clipboard_capability,
        )

    if browser_capability is None:
        browser_capability = BrowserCapability()

    if screenshot_capability is None:
        screenshot_capability = ScreenshotCapability(windows=window_capability)

    return ToolRegistry(
        audio_capability=audio_capability,
        app_capability=app_capability,
        media_capability=media_capability,
        system_capability=system_capability,
        window_capability=window_capability,
        files_capability=files_capability,
        clipboard_capability=clipboard_capability,
        keyboard_capability=keyboard_capability,
        mouse_capability=mouse_capability,
        ui_accessibility_capability=ui_accessibility_capability,
        interaction_capability=interaction_capability,
        browser_capability=browser_capability,
        screenshot_capability=screenshot_capability,
    ).livekit_tools()
