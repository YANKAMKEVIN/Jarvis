import asyncio
import functools
import inspect
from typing import Any, Callable

from livekit.agents import function_tool

from jarvis.capabilities.apps import AppCapability
from jarvis.capabilities.audio import AudioCapability
from jarvis.capabilities.browser import BrowserCapability
from jarvis.capabilities.clipboard import ClipboardCapability
from jarvis.capabilities.files import FilesCapability
from jarvis.capabilities.interaction import InteractionCapability
from jarvis.capabilities.keyboard import KeyboardCapability
from jarvis.capabilities.knowledge import KnowledgeCapability, web_announcement_for
from jarvis.capabilities.media import MediaCapability
from jarvis.capabilities.memory import MemoryCapability
from jarvis.capabilities.messaging import MessagingCapability
from jarvis.capabilities.mouse import MouseCapability
from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.screenshot import ScreenshotCapability
from jarvis.capabilities.system import SystemCapability
from jarvis.capabilities.ui_accessibility import UIAccessibilityCapability
from jarvis.capabilities.vision import VisionCapability
from jarvis.capabilities.windows import WindowCapability
from jarvis.live.config import debug_live, get_vision_model, is_vision_enabled
from jarvis.live.confirmation import PendingActionStore
from jarvis.planner.engine import PlannerEngine, TaskOutcome
from jarvis.planner.models import build_planner_model
from jarvis.planner.tasks import TaskManager, announcement_for
from jarvis.tools.vision import VisionTools


# Assistant apps whose input field is not introspectable via Accessibility
# (Electron/web, e.g. Claude): send_prompt_to_app types directly into the
# frontmost app instead of verifying an AX field. Low-risk prompt apps only;
# outward messaging never uses this path.
DIRECT_PROMPT_APPS = {"claude"}


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
        vision_capability=None,
        messaging_capability=None,
        memory_capability=None,
        knowledge_capability=None,
        pending_actions=None,
        planner_model=None,
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
        self.vision = (
            vision_capability
            if vision_capability is not None
            else VisionCapability()
        )
        self.messaging = (
            messaging_capability
            if messaging_capability is not None
            else MessagingCapability()
        )
        self.memory = (
            memory_capability
            if memory_capability is not None
            else MemoryCapability()
        )
        self.knowledge = (
            knowledge_capability
            if knowledge_capability is not None
            else self._default_knowledge()
        )
        self.pending_actions = (
            pending_actions
            if pending_actions is not None
            else PendingActionStore()
        )
        self.media_lock = asyncio.Lock()
        self.clipboard_lock = asyncio.Lock()
        self.keyboard_lock = asyncio.Lock()
        self.mouse_lock = asyncio.Lock()
        self.ui_lock = asyncio.Lock()
        self.interaction_lock = asyncio.Lock()
        self.browser_lock = asyncio.Lock()
        self.screenshot_lock = asyncio.Lock()
        self.vision_lock = asyncio.Lock()
        self.confirmation_lock = asyncio.Lock()
        self.memory_lock = asyncio.Lock()
        # Brain of background tasks; local Ollama unless injected (tests).
        self.planner_model = planner_model
        # Set by the voice agent: async callable speaking an announcement.
        self.task_notifier = None
        self.tasks: TaskManager | None = None
        # The planner's tool set (voice tools + planner-only web_answer); filled
        # by livekit_tools().
        self.planner_tools: list[Any] = []
        # Single-shot web search runs in the background so the voice model can
        # acknowledge at once and announce the result when it lands.
        self._web_task: asyncio.Task | None = None

    @staticmethod
    def _default_knowledge() -> KnowledgeCapability:
        # Free and local: a running SearXNG if present, else keyless web search
        # (Google News RSS / DuckDuckGo). Synthesis uses the local Ollama brain.
        # Imported lazily so the registry stays light for callers that inject.
        from jarvis.brain import LocalBrain
        from jarvis.knowledge.keyless import FallbackProvider, KeylessWebProvider
        from jarvis.knowledge.searxng import SearXNGProvider
        from jarvis.knowledge.service import KnowledgeService

        provider = FallbackProvider(SearXNGProvider(), KeylessWebProvider())
        return KnowledgeCapability(KnowledgeService(brain=LocalBrain(), provider=provider))

    def set_task_notifier(self, notifier) -> None:
        self.task_notifier = notifier

    async def _on_task_finished(self, goal: str, outcome: TaskOutcome) -> None:
        await self._log_action(
            f"task_{outcome.status}",
            None,
            {"ok": outcome.status in ("completed", "needs_confirmation")},
        )
        if self.task_notifier is not None:
            await self.task_notifier(announcement_for(goal, outcome))

    def _web_running(self) -> bool:
        return self._web_task is not None and not self._web_task.done()

    async def _run_web_search(self, question: str) -> None:
        try:
            result = await asyncio.to_thread(self.knowledge.answer, question)
        except Exception as error:
            result = ToolResult.failure(
                action="web_answer",
                message=f"La recherche web a echoue : {error}",
                error_code="system_error",
            )
        # Journal the outcome only (never the question or the content).
        await self._log_action("search_the_web", None, result)
        if self.task_notifier is not None:
            await self.task_notifier(web_announcement_for(result))

    async def _preferred_media_app(self) -> str | None:
        # Memory applied locally: the model never sees the preference.
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.memory.preferred_media_app)

    async def _log_action(self, tool_name: str, target: str | None, result) -> None:
        # Off the event loop, but kept apart from asyncio.to_thread which is
        # reserved for capability calls.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self.memory.log_action, tool_name, target, result,
        )

    def _journaled(
        self,
        tool_name: str,
        target_arg: str | None = None,
        target_from: Callable[[Any], str | None] | None = None,
    ):
        """Record the action in the activity journal after it ran.

        Only the tool name, a non-sensitive target (app name, URL host) and
        the outcome are kept; never text, message content or paths.
        """
        def decorate(fn):
            signature = inspect.signature(fn)

            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                result = await fn(*args, **kwargs)
                target = None
                if target_arg is not None:
                    try:
                        value = signature.bind_partial(*args, **kwargs).arguments.get(target_arg)
                        target = target_from(value) if target_from else value
                    except Exception:
                        target = None
                await self._log_action(
                    tool_name,
                    target if isinstance(target, str) else None,
                    result,
                )
                return result

            return wrapper

        return decorate

    def livekit_tools(self) -> list[Any]:
        @function_tool(
            name="set_volume",
            description=(
                "Modifie réellement le volume de sortie du Mac de l'utilisateur. "
                "Utilise ce tool quand l'utilisateur demande de mettre, régler, "
                "monter ou baisser le volume à un niveau précis entre 0 et 100."
            ),
        )
        @self._journaled("set_volume")
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
        @self._journaled("open_app", "app_name")
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
        @self._journaled("close_app", "app_name")
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
        @self._journaled("play_pause")
        async def play_pause() -> dict:
            """Toggle play/pause for the active supported media app."""
            debug_live("tool_call", tool="play_pause")
            async with self.media_lock:
                # Inside the lock so concurrent media calls keep their order.
                preferred = await self._preferred_media_app()
                result = await (
                    asyncio.to_thread(self.media.play_pause, preferred)
                    if preferred
                    else asyncio.to_thread(self.media.play_pause)
                )
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
        @self._journaled("next_track")
        async def next_track() -> dict:
            """Skip to the next track in the active supported media app."""
            debug_live("tool_call", tool="next_track")
            async with self.media_lock:
                # Inside the lock so concurrent media calls keep their order.
                preferred = await self._preferred_media_app()
                result = await (
                    asyncio.to_thread(self.media.next_track, preferred)
                    if preferred
                    else asyncio.to_thread(self.media.next_track)
                )
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
        @self._journaled("previous_track")
        async def previous_track() -> dict:
            """Go back to the previous track in the active supported media app."""
            debug_live("tool_call", tool="previous_track")
            async with self.media_lock:
                # Inside the lock so concurrent media calls keep their order.
                preferred = await self._preferred_media_app()
                result = await (
                    asyncio.to_thread(self.media.previous_track, preferred)
                    if preferred
                    else asyncio.to_thread(self.media.previous_track)
                )
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
        @self._journaled("focus_window", "app_name")
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
        @self._journaled("open_file")
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
        @self._journaled("open_folder")
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
        @self._journaled("create_folder")
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
        @self._journaled("rename_file")
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
                "Deplace un fichier ou dossier local sans jamais ecraser de "
                "chemin existant. destination est soit le chemin final exact, "
                "soit un dossier existant (par exemple Documents ou Bureau) : "
                "l'element y est alors place en gardant son nom."
            ),
        )
        @self._journaled("move_file")
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
        @self._journaled("focus_app_ui_and_type", "app_name")
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

        @function_tool(
            name="prepare_send_message",
            description=(
                "PREPARE l'envoi d'un message a un destinataire dans une "
                "application de messagerie (par exemple WhatsApp), SANS l'envoyer. "
                "Enregistre l'envoi et renvoie un token et requires_confirmation. "
                "Utilise ce tool des que l'utilisateur veut envoyer un message a "
                "une personne, un contact ou un groupe. Apres l'avoir appele, "
                "annonce clairement a l'utilisateur l'application, le destinataire "
                "et le contenu exact, puis attends une confirmation orale "
                "explicite. N'envoie rien ici ; l'envoi reel se fait uniquement "
                "ensuite via confirm_action(token). query cible un champ de saisie "
                "nomme si besoin. Fournis recipient (le nom du destinataire) pour "
                "que Jarvis verifie d'abord que la conversation ouverte correspond "
                "bien ; si recipient_not_verified est retourne, rien n'est prepare "
                "et il faut ouvrir la bonne conversation. N'utilise pas ce tool "
                "pour un simple prompt a un assistant comme Claude : utilise "
                "send_prompt_to_app pour cela."
            ),
        )
        @self._journaled("prepare_send_message", "app_name")
        async def prepare_send_message(
            app_name: str,
            text: str,
            recipient: str | None = None,
            query: str | None = None,
        ) -> dict:
            """Register a message send for confirmation; no side effect here."""
            if not isinstance(app_name, str) or not app_name.strip():
                return ToolResult.failure(
                    action="prepare_send_message",
                    message="Le nom de l'application de messagerie est obligatoire.",
                    error_code="invalid_app_name",
                ).to_livekit_dict()

            if not isinstance(text, str) or not text.strip():
                return ToolResult.failure(
                    action="prepare_send_message",
                    message="Le message a envoyer est obligatoire.",
                    error_code="invalid_text",
                ).to_livekit_dict()

            recipient_from_memory = False
            if isinstance(recipient, str) and recipient.strip():
                # Apply memory locally: "ma mere" -> stored contact name. The
                # model never needs (nor receives) the stored name.
                async with self.memory_lock:
                    resolved = await asyncio.to_thread(
                        self.memory.resolve_person, recipient,
                    )
                if resolved:
                    recipient = resolved
                    recipient_from_memory = True

                verification = await asyncio.to_thread(
                    self.messaging.ensure_recipient,
                    app_name,
                    recipient,
                )
                self._debug_interaction_result("ensure_recipient", verification)
                if not verification.ok:
                    # Fail safe: never prepare a send against an unverified chat.
                    return verification.to_livekit_dict()

            # Target the app's composer by default (e.g. WhatsApp's is not
            # focused on its own); an explicit query still wins.
            effective_query = (
                query
                if isinstance(query, str) and query.strip()
                else self.messaging.composer_query(app_name)
            )

            def _executor():
                return self.interaction.focus_app_ui_and_type(
                    app_name, text, effective_query, None, True,
                )

            async with self.confirmation_lock:
                token = self.pending_actions.register("send_message", _executor)

            debug_live(
                "tool_call",
                tool="prepare_send_message",
                app_name=app_name,
                text_length=len(text),
                query_length=len(query) if isinstance(query, str) else None,
                token=token,
            )
            return ToolResult.success(
                action="prepare_send_message",
                message=(
                    "Envoi prepare. Annonce le destinataire et le contenu a "
                    "l'utilisateur et attends sa confirmation avant confirm_action."
                ),
                requires_confirmation=True,
                token=token,
                target_app=app_name,
                text_length=len(text),
                query_length=len(query) if isinstance(query, str) else None,
                recipient_verified=bool(isinstance(recipient, str) and recipient.strip()),
                recipient_from_memory=recipient_from_memory,
            ).to_livekit_dict()

        @function_tool(
            name="remember",
            description=(
                "Enregistre un souvenir durable UNIQUEMENT quand l'utilisateur "
                "demande explicitement de retenir quelque chose (souviens-toi, "
                "retiens, note que...). kind : profile (infos sur l'utilisateur), "
                "person (subject = surnom ou relation comme 'ma mere', content = "
                "nom exact du contact dans les apps), preference (subject = "
                "domaine comme 'musique', content = la preference, par exemple "
                "'Spotify' ou 'Apple Music'), fact (autre "
                "information utile). Un souvenir de meme kind et subject est mis "
                "a jour. Pour une information que tu as seulement deduite, "
                "utilise propose_memory. Les secrets sont toujours refuses."
            ),
        )
        @self._journaled("remember")
        async def remember(kind: str, subject: str, content: str) -> dict:
            """Store an explicitly requested long-term memory."""
            debug_live("tool_call", tool="remember", kind=kind)
            async with self.memory_lock:
                result = await asyncio.to_thread(
                    self.memory.remember, kind, subject, content, "user",
                )
            self._debug_tool_result("remember", result)
            return result.to_livekit_dict()

        @function_tool(
            name="propose_memory",
            description=(
                "Propose de retenir une information que tu as DEDUITE sans que "
                "l'utilisateur demande de la retenir (par exemple il corrige deux "
                "fois le meme nom de contact). N'enregistre rien : renvoie un "
                "token et requires_confirmation. Demande alors a l'utilisateur, "
                "en une phrase, s'il veut que tu retiennes cette information ; "
                "seulement apres un oui clair, appelle confirm_action(token). "
                "Sinon cancel_action(token). Memes kind que remember."
            ),
        )
        async def propose_memory(kind: str, subject: str, content: str) -> dict:
            """Register an inferred memory that is stored only on confirmation."""
            debug_live("tool_call", tool="propose_memory", kind=kind)
            refusal = self.memory.check_proposal(kind, subject, content)
            if refusal is not None:
                return refusal.to_livekit_dict()

            def _executor():
                return self.memory.remember(kind, subject, content, "inferred")

            async with self.confirmation_lock:
                token = self.pending_actions.register("remember_inferred", _executor)

            return ToolResult.success(
                action="propose_memory",
                message=(
                    "Rien n'est enregistre. Demande a l'utilisateur s'il veut que "
                    "tu retiennes cette information, puis confirm_action ou "
                    "cancel_action."
                ),
                requires_confirmation=True,
                token=token,
            ).to_livekit_dict()

        @function_tool(
            name="recall",
            description=(
                "Cherche dans la memoire durable de l'utilisateur (profil, "
                "personnes, preferences, faits). Utilise ce tool quand "
                "l'utilisateur pose une question sur ce qu'il t'a demande de "
                "retenir, ou quand une information personnelle manque pour "
                "repondre (par exemple le nom de son dentiste). kind optionnel "
                "pour filtrer. Ne reponds jamais 'je ne sais pas' sur un sujet "
                "personnel sans avoir appele recall."
            ),
        )
        async def recall(query: str, kind: str | None = None) -> dict:
            """Search long-term memory."""
            debug_live("tool_call", tool="recall", kind=kind)
            async with self.memory_lock:
                result = await asyncio.to_thread(self.memory.recall, query, kind)
            self._debug_tool_result("recall", result)
            return result.to_livekit_dict()

        @function_tool(
            name="list_memories",
            description=(
                "Liste les souvenirs enregistres, eventuellement filtres par kind. "
                "Utilise ce tool pour 'qu'est-ce que tu sais sur moi' ou 'quels "
                "contacts tu connais'."
            ),
        )
        async def list_memories(kind: str | None = None) -> dict:
            """List stored memories."""
            debug_live("tool_call", tool="list_memories", kind=kind)
            async with self.memory_lock:
                result = await asyncio.to_thread(self.memory.list_memories, kind)
            self._debug_tool_result("list_memories", result)
            return result.to_livekit_dict()

        @function_tool(
            name="forget",
            description=(
                "Oublie definitivement un souvenir quand l'utilisateur le demande "
                "(oublie que..., efface ce que tu sais sur...). Fournis memory_id "
                "si tu le connais, sinon query. Si ambiguous_memory est retourne, "
                "rien n'est efface : presente les candidats et demande lequel."
            ),
        )
        @self._journaled("forget")
        async def forget(memory_id: int | None = None, query: str | None = None) -> dict:
            """Delete one memory by id or unambiguous query."""
            debug_live("tool_call", tool="forget", memory_id=memory_id)
            async with self.memory_lock:
                result = await asyncio.to_thread(self.memory.forget, memory_id, query)
            self._debug_tool_result("forget", result)
            return result.to_livekit_dict()

        @function_tool(
            name="recent_activity",
            description=(
                "Relit le journal des dernieres actions realisees par Jarvis "
                "(ouvrir une app, changer le volume, preparer ou envoyer un "
                "message, ouvrir un site...), avec l'heure et le resultat. Le "
                "journal ne contient jamais le texte des messages ni le contenu "
                "manipule. Utilise ce tool pour 'qu'est-ce que tu as fait', "
                "'tu as bien envoye le message ?' ou 'refais comme tout a l'heure'."
            ),
        )
        async def recent_activity(limit: int = 10) -> dict:
            """Read the most recent journaled actions."""
            debug_live("tool_call", tool="recent_activity", limit=limit)
            async with self.memory_lock:
                result = await asyncio.to_thread(self.memory.recent_activity, limit)
            self._debug_tool_result("recent_activity", result)
            return result.to_livekit_dict()

        @function_tool(
            name="confirm_action",
            description=(
                "Execute reellement une action preparee (envoi de message ou "
                "souvenir deduit a enregistrer) en utilisant le token renvoye par "
                "prepare_send_message ou propose_memory. N'appelle ce tool "
                "qu'APRES une confirmation orale explicite de l'utilisateur. "
                "N'invente jamais de token et ne l'appelle jamais sans preparation "
                "prealable. Si aucune action n'est en attente, il retourne "
                "no_pending_action."
            ),
        )
        async def confirm_action(token: str) -> dict:
            """Execute a previously prepared outward action after confirmation."""
            debug_live("tool_call", tool="confirm_action", token=token)
            async with self.confirmation_lock:
                pending = self.pending_actions.confirm(token)

            if pending is None:
                debug_live("tool_failed", tool="confirm_action", error="no_pending_action")
                return ToolResult.failure(
                    action="confirm_action",
                    message=(
                        "Aucune action en attente de confirmation (ou expiree). "
                        "Rien n'a ete envoye."
                    ),
                    error_code="no_pending_action",
                ).to_livekit_dict()

            result = await asyncio.to_thread(pending.executor)
            self._debug_interaction_result(f"confirm_action:{pending.action}", result)
            payload = result.to_livekit_dict()
            await self._log_action(f"confirm_{pending.action}", None, payload)
            return payload

        @function_tool(
            name="cancel_action",
            description=(
                "Annule une action sortante preparee (par exemple un envoi de "
                "message) sans l'executer, en utilisant son token. Utilise ce tool "
                "si l'utilisateur refuse, hesite ou se retracte apres une "
                "preparation. Rien n'est envoye."
            ),
        )
        async def cancel_action(token: str) -> dict:
            """Discard a prepared outward action without executing it."""
            debug_live("tool_call", tool="cancel_action", token=token)
            async with self.confirmation_lock:
                pending = self.pending_actions.cancel(token)

            cancelled = pending is not None
            debug_live(
                "tool_succeeded" if cancelled else "tool_failed",
                tool="cancel_action",
                cancelled=cancelled,
            )
            return ToolResult.success(
                action="cancel_action",
                message=(
                    "Action annulee, rien n'a ete envoye."
                    if cancelled
                    else "Aucune action en attente a annuler."
                ),
                cancelled=cancelled,
            ).to_livekit_dict()

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
        @self._journaled("browse_open_url", "url", self._journal_host)
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
        @self._journaled("browse_search_web")
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
            async with self.browser_lock:
                result = await asyncio.to_thread(
                    self.browser.activate_tab,
                    query,
                    index,
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
        @self._journaled("capture_screen")
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
        @self._journaled("capture_region")
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
        @self._journaled("capture_window", "app_name")
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

        @function_tool(
            name="describe_screen",
            description=(
                "Regarde l'ecran et decrit ce qui est visible. Capture (fenetre "
                "active par defaut, ou tout l'ecran avec target='screen') puis "
                "analyse l'image avec un modele multimodal, et renvoie une "
                "description. Utilise ce tool pour une demande comme qu'est-ce "
                "qu'il y a sur mon ecran. Rapporte seulement ce que l'analyse "
                "renvoie ; n'invente rien. Ce tool observe uniquement : il ne "
                "fournit aucune coordonnee et ne declenche aucune action. Pour "
                "cliquer ou taper, utilise Accessibility, jamais ce tool."
            ),
        )
        async def describe_screen(
            target: str = "window",
            app_name: str | None = None,
        ) -> dict:
            """Capture then describe what is visible (read-only)."""
            guard = self._vision_guard("describe_screen")
            if guard is not None:
                return guard
            debug_live("tool_call", tool="describe_screen", source=target)
            async with self.vision_lock:
                result = await asyncio.to_thread(
                    self.vision.describe_screen,
                    target,
                    app_name,
                )
            self._debug_vision_result("describe_screen", result)
            return result.to_livekit_dict()

        @function_tool(
            name="ask_about_screen",
            description=(
                "Regarde l'ecran et repond a une question sur ce qui est affiche "
                "(par exemple quelle temperature / quel prix est affiche, que dit "
                "cette page). Capture (fenetre active par defaut, ou tout l'ecran "
                "avec target='screen') puis analyse l'image. Si l'information "
                "n'est pas visible ou lisible, dis-le, n'invente jamais une "
                "valeur. Ce tool observe uniquement : aucune coordonnee, aucune "
                "action. Pour agir, utilise Accessibility."
            ),
        )
        async def ask_about_screen(
            question: str,
            target: str = "window",
            app_name: str | None = None,
        ) -> dict:
            """Capture then answer a question about the screen (read-only)."""
            guard = self._vision_guard("ask_about_screen")
            if guard is not None:
                return guard
            debug_live(
                "tool_call",
                tool="ask_about_screen",
                source=target,
                question_length=len(question) if isinstance(question, str) else None,
            )
            async with self.vision_lock:
                result = await asyncio.to_thread(
                    self.vision.ask_about_screen,
                    question,
                    target,
                    app_name,
                )
            self._debug_vision_result("ask_about_screen", result)
            return result.to_livekit_dict()

        @function_tool(
            name="search_the_web",
            description=(
                "Cherche une information a jour sur le web et la synthetise a voix "
                "haute : actualites, meteo, prix, cours, resultats, 'qui est', 'quelles "
                "sont les nouvelles', 'quoi de neuf sur X'. La recherche tourne en "
                "arriere-plan (quelques secondes) ; des que tu appelles ce tool, dis a "
                "l'utilisateur que tu regardes, puis le resultat sera annonce tout seul. "
                "Si l'utilisateur ne precise pas de domaine pour 'les nouvelles', ne "
                "bloque pas : prends les grands titres a la une et propose d'affiner. "
                "N'utilise pas ce tool pour agir sur le Mac ni pour une question dont la "
                "reponse ne depend pas d'une information actuelle. question : la question "
                "complete en francais."
            ),
        )
        @self._journaled("search_the_web")
        async def search_the_web(question: str) -> dict:
            """Start a background web search; its result is announced by voice."""
            debug_live(
                "tool_call",
                tool="search_the_web",
                question_length=len(question) if isinstance(question, str) else None,
            )
            if not isinstance(question, str) or not question.strip():
                return ToolResult.failure(
                    action="search_the_web",
                    message="La question de recherche est vide.",
                    error_code="invalid_question",
                ).to_livekit_dict()
            if self._web_running():
                return ToolResult.failure(
                    action="search_the_web",
                    message="Une recherche web est deja en cours ; attends son resultat.",
                    error_code="web_search_running",
                ).to_livekit_dict()
            self._web_task = asyncio.get_running_loop().create_task(
                self._run_web_search(question.strip())
            )
            return ToolResult.success(
                action="search_the_web",
                message=(
                    "Recherche lancee. Dis simplement a l'utilisateur que tu regardes ; "
                    "le resultat sera annonce dans un instant."
                ),
                search_started=True,
            ).to_livekit_dict()

        @function_tool(
            name="web_answer",
            description=(
                "Recherche une information a jour sur le web et renvoie une reponse "
                "synthetisee avec ses sources. Outil reserve aux taches longues : il "
                "BLOQUE le temps de la recherche (quelques secondes). Appuie-toi "
                "uniquement sur sa reponse et ses sources, n'invente rien. question : "
                "la question complete en francais."
            ),
        )
        @self._journaled("web_answer")
        async def web_answer(question: str) -> dict:
            """Blocking web search for the planner (not exposed to the voice model)."""
            debug_live(
                "tool_call",
                tool="web_answer",
                question_length=len(question) if isinstance(question, str) else None,
            )
            result = await asyncio.to_thread(self.knowledge.answer, question)
            return result.to_livekit_dict()

        @function_tool(
            name="run_task",
            description=(
                "Confie a Jarvis une TACHE LONGUE en plusieurs etapes qui demande "
                "de chercher, verifier et enchainer plusieurs actions (par exemple : "
                "retrouve le dernier PDF telecharge, renomme-le et range-le dans "
                "Documents). La tache tourne en arriere-plan avec un planificateur "
                "local plus lent (souvent une minute) ; le resultat sera annonce a la "
                "fin. N'utilise PAS ce tool pour une demande simple ou un enchainement "
                "court que tu peux faire directement avec tes autres tools (volume, "
                "media, ouvrir une app ou un site, envoyer un message). goal : "
                "l'objectif complet et autonome, en francais."
            ),
        )
        @self._journaled("run_task")
        async def run_task(goal: str) -> dict:
            """Start a multi-step planner task in the background."""
            debug_live(
                "tool_call",
                tool="run_task",
                goal_length=len(goal) if isinstance(goal, str) else None,
            )
            return self.tasks.start(goal)

        @function_tool(
            name="task_status",
            description=(
                "Donne l'avancement de la tache en arriere-plan (en cours, nombre "
                "d'etapes, duree) ou le resultat de la derniere tache. Utilise ce "
                "tool pour 'ou en est la tache', 'c'est bientot fini ?'."
            ),
        )
        async def task_status() -> dict:
            """Report the background task progress or last result."""
            debug_live("tool_call", tool="task_status")
            return self.tasks.status()

        @function_tool(
            name="cancel_task",
            description=(
                "Annule la tache en arriere-plan quand l'utilisateur dit stop, "
                "annule ou laisse tomber pendant qu'une tache tourne. Elle s'arrete "
                "avant l'etape suivante."
            ),
        )
        @self._journaled("cancel_task")
        async def cancel_task() -> dict:
            """Request cancellation of the running background task."""
            debug_live("tool_call", tool="cancel_task")
            return self.tasks.cancel()

        @function_tool(
            name="save_task_procedure",
            description=(
                "Retient la DERNIERE tache reussie comme procedure reutilisable "
                "sous un nom (par exemple 'preparer ma reunion'), pour pouvoir "
                "dire ensuite 'refais comme d'habitude'. N'enregistre que "
                "l'enchainement des outils, jamais le contenu. Utilise ce tool "
                "quand l'utilisateur dit 'retiens cette tache' ou 'garde ca comme "
                "procedure'. S'il n'y a pas de tache reussie recente, dis-le."
            ),
        )
        @self._journaled("save_task_procedure", target_arg="name")
        async def save_task_procedure(name: str) -> dict:
            """Learn the last successful task as a named, reusable procedure."""
            debug_live("tool_call", tool="save_task_procedure")
            last = self.tasks.last_completed()
            if last is None:
                return ToolResult.failure(
                    action="save_task_procedure",
                    message="Aucune tache recente reussie a retenir comme procedure.",
                    error_code="no_completed_task",
                ).to_livekit_dict()
            _goal, tool_names = last
            steps = [{"tool": name_, "target": None} for name_ in tool_names]
            async with self.memory_lock:
                result = await asyncio.to_thread(
                    self.memory.save_procedure, name, steps, "user",
                )
            self._debug_tool_result("save_task_procedure", result)
            return result.to_livekit_dict()

        @function_tool(
            name="run_procedure",
            description=(
                "Rejoue une procedure enregistree par son nom (par exemple 'refais "
                "comme d'habitude pour preparer ma reunion'). Charge l'enchainement "
                "habituel et lance une tache en arriere-plan qui l'adapte et verifie "
                "chaque etape. Si aucune procedure ne porte ce nom, dis-le sans rien "
                "lancer."
            ),
        )
        @self._journaled("run_procedure", target_arg="name")
        async def run_procedure(name: str) -> dict:
            """Replay a saved procedure as a background task seeded by its steps."""
            debug_live("tool_call", tool="run_procedure")
            async with self.memory_lock:
                got = await asyncio.to_thread(self.memory.get_procedure, name)
            if not got.ok:
                return got.to_livekit_dict()
            steps = got.data.get("procedure", {}).get("steps") or []
            skeleton = ", ".join(
                step["tool"] for step in steps if isinstance(step, dict) and step.get("tool")
            )
            goal = (
                f"Refais la procedure habituelle « {name} ». Enchainement habituel "
                f"des outils (adapte si besoin et verifie chaque etape) : {skeleton}."
            )
            return self.tasks.start(goal)

        tools = [
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
            send_prompt_to_app,
            prepare_send_message,
            confirm_action,
            cancel_action,
            remember,
            propose_memory,
            recall,
            list_memories,
            forget,
            recent_activity,
            browse_open_url,
            browse_search_web,
            browse_get_active_tab,
            browse_list_tabs,
            browse_activate_tab,
            capture_screen,
            capture_region,
            capture_window,
            describe_screen,
            ask_about_screen,
            search_the_web,
            run_task,
            task_status,
            cancel_task,
            save_task_procedure,
            run_procedure,
        ]

        # The planner drives these very tools (same locks, journal and pending
        # action store), so a message it prepares is confirmable by voice. It
        # also gets web_answer, a blocking web search kept out of the voice
        # tool set (the voice uses the background search_the_web instead).
        self.planner_tools = tools + [web_answer]
        self.tasks = TaskManager(
            lambda: PlannerEngine(
                self.planner_model or build_planner_model(), self.planner_tools
            ),
            on_finished=self._on_task_finished,
        )
        return tools

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
    def _journal_host(url) -> str | None:
        """Bare host for the journal: no credentials, port, path or query."""
        if not isinstance(url, str) or not url.strip():
            return None

        from urllib.parse import urlparse

        text = url.strip()
        parsed = urlparse(text if "://" in text else f"//{text}")
        try:
            host = parsed.hostname
        except ValueError:
            return None
        if not host:
            return None
        return host[4:] if host.startswith("www.") else host

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

    @staticmethod
    def _vision_guard(tool_name: str) -> dict | None:
        # Opt-in gate: Vision sends a screen capture to an external service.
        if is_vision_enabled():
            return None

        debug_live("tool_failed", tool=tool_name, error="vision_disabled")
        return {
            "ok": False,
            "action": tool_name,
            "message": (
                "La vision est desactivee. Active JARVIS_VISION_ENABLED pour "
                "autoriser Jarvis a analyser une capture d'ecran."
            ),
            "error_code": "vision_disabled",
        }

    @staticmethod
    def _debug_vision_result(tool_name: str, result) -> None:
        # Metadata only: never the analysis text, the raw question, the image
        # bytes/base64, or the full path.
        import os as _os

        path = result.data.get("image_path")
        fields = {
            "tool": tool_name,
            "source": result.data.get("source"),
            "target_app": result.data.get("target_app"),
            "model": result.data.get("model"),
            "image_file": _os.path.basename(path) if isinstance(path, str) else None,
            "image_bytes": result.data.get("image_bytes"),
            "image_width": result.data.get("image_width"),
            "image_height": result.data.get("image_height"),
            "question_length": result.data.get("question_length"),
            "duration_ms": result.data.get("duration_ms"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live("tool_failed", tool=tool_name, error=result.error_code)


def create_live_tools(*args, **kwargs) -> list[Any]:
    return create_live_registry(*args, **kwargs).livekit_tools()


def create_live_registry(
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
    vision_capability=None,
    messaging_capability=None,
    memory_capability=None,
    knowledge_capability=None,
    planner_model=None,
) -> "ToolRegistry":
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

    if vision_capability is None:
        vision_capability = VisionCapability(
            screenshot=screenshot_capability,
            vision_tools=VisionTools(model=get_vision_model()),
        )

    if messaging_capability is None:
        messaging_capability = MessagingCapability(
            windows=window_capability,
            ui_accessibility=ui_accessibility_capability,
            apps=app_capability,
            keyboard=keyboard_capability,
        )

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
        vision_capability=vision_capability,
        messaging_capability=messaging_capability,
        memory_capability=memory_capability,
        knowledge_capability=knowledge_capability,
        planner_model=planner_model,
    )
