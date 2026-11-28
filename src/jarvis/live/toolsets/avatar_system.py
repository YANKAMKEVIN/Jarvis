"""Avatar, volume, applications and media playback tools.

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
    # The avatar on screen IS Jarvis: results are worded so the model says
    # "je danse", never that a command or request was sent to something else.
    @function_tool(name="dance_avatar", description="Te fait danser toi-même, Jarvis, à l'écran pendant huit secondes, quand l'utilisateur te demande de danser ou si tu sais danser. stop=True arrête ta danse, sans couper le vocal. Aucune musique. Si les animations sont réduites ou ton apparence est abstraite, l'écran l'indique.")
    async def dance_avatar(stop: bool = False) -> dict:
        observer = registry.presentation_observer
        if observer is None:
            return {"ok": False, "error": "desktop_unavailable",
                    "message": "Tu ne peux pas danser ici : ton avatar n'est pas affiché. Dis-le simplement, à la première personne."}
        observer({"type": "avatar_dance", "action": "stop" if stop else "start"})
        if stop:
            return {"ok": True, "status": "stopped",
                    "message": "Tu t'arrêtes de danser. Dis-le en quelques mots, à la première personne."}
        return {"ok": True, "status": "dancing",
                "message": "Tu danses maintenant, pendant huit secondes. Dis-le tout de suite à la première personne, avec une phrase courte et joueuse (« Et je danse ! »). Ne parle ni de commande, ni de demande, ni de compagnon."}

    @function_tool(
        name="set_volume",
        description=(
            "Modifie réellement le volume de sortie du Mac de l'utilisateur. "
            "Utilise ce tool quand l'utilisateur demande de mettre, régler, "
            "monter ou baisser le volume à un niveau précis entre 0 et 100."
        ),
    )
    @registry._journaled("set_volume")
    async def set_volume(volume: int) -> dict:
        """Set the Mac output volume to a value between 0 and 100."""
        debug_live("tool_call", tool="set_volume", volume=volume)
        result = await asyncio.to_thread(registry.audio.set_volume, volume)

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
        result = await asyncio.to_thread(registry.audio.get_volume)

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
    @registry._journaled("open_app", "app_name")
    @registry._desktop_access
    async def open_app(app_name: str) -> dict:
        """Open a macOS application by name."""
        debug_live("tool_call", tool="open_app", app_name=app_name)
        result = await asyncio.to_thread(registry.apps.open_app, app_name)

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
    @registry._journaled("close_app", "app_name")
    @registry._desktop_access
    async def close_app(app_name: str) -> dict:
        """Close a macOS application by name."""
        debug_live("tool_call", tool="close_app", app_name=app_name)
        result = await asyncio.to_thread(registry.apps.close_app, app_name)

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
            registry.apps.is_app_running,
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
    @registry._journaled("play_pause")
    @registry._desktop_access
    async def play_pause() -> dict:
        """Toggle play/pause for the active supported media app."""
        debug_live("tool_call", tool="play_pause")
        async with registry.media_lock:
            # Inside the lock so concurrent media calls keep their order.
            preferred = await registry._preferred_media_app()
            result = await (
                asyncio.to_thread(registry.media.play_pause, preferred)
                if preferred
                else asyncio.to_thread(registry.media.play_pause)
            )
        registry._debug_tool_result("play_pause", result)
        return result.to_livekit_dict()

    @function_tool(
        name="next_track",
        description=(
            "Passe au morceau suivant dans l'application média compatible "
            "active. Utilise ce tool quand l'utilisateur demande la "
            "suivante, le titre suivant ou de passer au prochain morceau."
        ),
    )
    @registry._journaled("next_track")
    @registry._desktop_access
    async def next_track() -> dict:
        """Skip to the next track in the active supported media app."""
        debug_live("tool_call", tool="next_track")
        async with registry.media_lock:
            # Inside the lock so concurrent media calls keep their order.
            preferred = await registry._preferred_media_app()
            result = await (
                asyncio.to_thread(registry.media.next_track, preferred)
                if preferred
                else asyncio.to_thread(registry.media.next_track)
            )
        registry._debug_tool_result("next_track", result)
        return result.to_livekit_dict()

    @function_tool(
        name="previous_track",
        description=(
            "Revient au morceau précédent dans l'application média "
            "compatible active. Utilise ce tool quand l'utilisateur "
            "demande la chanson précédente ou de revenir en arrière."
        ),
    )
    @registry._journaled("previous_track")
    @registry._desktop_access
    async def previous_track() -> dict:
        """Go back to the previous track in the active supported media app."""
        debug_live("tool_call", tool="previous_track")
        async with registry.media_lock:
            # Inside the lock so concurrent media calls keep their order.
            preferred = await registry._preferred_media_app()
            result = await (
                asyncio.to_thread(registry.media.previous_track, preferred)
                if preferred
                else asyncio.to_thread(registry.media.previous_track)
            )
        registry._debug_tool_result("previous_track", result)
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
        async with registry.media_lock:
            result = await asyncio.to_thread(registry.media.get_media_state)
        registry._debug_tool_result("get_media_state", result)
        return result.to_livekit_dict()

    return {
        "dance_avatar": dance_avatar,
        "set_volume": set_volume,
        "get_volume": get_volume,
        "open_app": open_app,
        "close_app": close_app,
        "is_app_running": is_app_running,
        "play_pause": play_pause,
        "next_track": next_track,
        "previous_track": previous_track,
        "get_media_state": get_media_state,
    }
