"""Screenshot, vision and camera tools.

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
    @registry._journaled("capture_screen")
    @registry._desktop_access
    async def capture_screen(
        path: str | None = None,
        display: int | None = None,
    ) -> dict:
        """Capture the full screen to a PNG file and verify it."""
        debug_live("tool_call", tool="capture_screen", display=display)
        async with registry.screenshot_lock:
            result = await asyncio.to_thread(
                registry.screenshot.capture_screen,
                path,
                display,
            )
        registry._debug_screenshot_result("capture_screen", result)
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
    @registry._journaled("capture_region")
    @registry._desktop_access
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
        async with registry.screenshot_lock:
            result = await asyncio.to_thread(
                registry.screenshot.capture_region,
                x,
                y,
                width,
                height,
                path,
            )
        registry._debug_screenshot_result("capture_region", result)
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
    @registry._journaled("capture_window", "app_name")
    @registry._desktop_access
    async def capture_window(
        app_name: str | None = None,
        path: str | None = None,
    ) -> dict:
        """Capture the active or a named window to a PNG file and verify it."""
        debug_live("tool_call", tool="capture_window", app_name=app_name)
        async with registry.screenshot_lock:
            result = await asyncio.to_thread(
                registry.screenshot.capture_window,
                app_name,
                path,
            )
        registry._debug_screenshot_result("capture_window", result)
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
    @registry._journaled('describe_screen')
    @registry._desktop_access
    async def describe_screen(
        target: str = "window",
        app_name: str | None = None,
    ) -> dict:
        """Capture then describe what is visible (read-only)."""
        guard = registry._vision_guard("describe_screen")
        if guard is not None:
            return guard
        debug_live("tool_call", tool="describe_screen", source=target)
        async with registry.vision_lock:
            result = await asyncio.to_thread(
                registry.vision.describe_screen,
                target,
                app_name,
            )
        registry._debug_vision_result("describe_screen", result)
        return result.to_livekit_dict()

    @function_tool(
        name="describe_camera",
        description=(
            "Regarde a travers la camera du Mac et decrit ce qui est visible : "
            "'qu'est-ce que tu vois', 'regarde ce que je tiens', 'decris la "
            "piece'. question : optionnelle, ce que l'utilisateur veut savoir "
            "sur la scene. Prend UNE seule photo au moment de l'appel, l'analyse "
            "puis la supprime ; aucun flux, rien n'est garde. Decrit les "
            "personnes sans jamais les identifier. N'appelle ce tool que sur "
            "demande explicite de regarder par la camera, jamais pour l'ecran."
        ),
    )
    @registry._journaled('describe_camera')
    async def describe_camera(question: str | None = None) -> dict:
        """Take one camera still, describe it, delete it (read-only)."""
        guard = registry._vision_guard("describe_camera")
        if guard is not None:
            return guard
        debug_live("tool_call", tool="describe_camera",
                   question_length=len(question) if isinstance(question, str) else None)
        async with registry.vision_lock:
            result = await asyncio.to_thread(registry.camera.describe, question)
        registry._debug_tool_result("describe_camera", result)
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
    @registry._journaled('ask_about_screen')
    @registry._desktop_access
    async def ask_about_screen(
        question: str,
        target: str = "window",
        app_name: str | None = None,
    ) -> dict:
        """Capture then answer a question about the screen (read-only)."""
        guard = registry._vision_guard("ask_about_screen")
        if guard is not None:
            return guard
        debug_live(
            "tool_call",
            tool="ask_about_screen",
            source=target,
            question_length=len(question) if isinstance(question, str) else None,
        )
        async with registry.vision_lock:
            result = await asyncio.to_thread(
                registry.vision.ask_about_screen,
                question,
                target,
                app_name,
            )
        registry._debug_vision_result("ask_about_screen", result)
        return result.to_livekit_dict()

    return {
        "capture_screen": capture_screen,
        "capture_region": capture_region,
        "capture_window": capture_window,
        "describe_screen": describe_screen,
        "describe_camera": describe_camera,
        "ask_about_screen": ask_about_screen,
    }
