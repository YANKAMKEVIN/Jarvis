import asyncio
from typing import Any

from livekit.agents import function_tool

from jarvis.capabilities.audio import AudioCapability
from jarvis.live.config import debug_live


class ToolRegistry:
    def __init__(self, audio_capability=None):
        self.audio = (
            audio_capability
            if audio_capability is not None
            else AudioCapability()
        )

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

        return [set_volume, get_volume]


def create_live_tools(
    security=None,
    macos_tools=None,
    audio_capability=None,
) -> list[Any]:
    if audio_capability is None:
        audio_capability = AudioCapability(
            security=security,
            macos_tools=macos_tools,
        )

    return ToolRegistry(audio_capability=audio_capability).livekit_tools()
