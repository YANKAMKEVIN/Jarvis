"""Live tool registry: the tools Jarvis exposes to the voice model and planner.

``ToolRegistry`` assembles the tool groups of ``jarvis.live.toolsets`` on top
of its capability wiring (``registry_base``), session runtime
(``registry_runtime``) and debug helpers (``debug_results``). This module
stays the public entry point: ``ToolRegistry``, ``create_live_registry``,
``create_live_tools``, ``SAFE_MODE_ALLOWED`` and ``DIRECT_PROMPT_APPS`` are
importable from here as before.
"""
import asyncio  # noqa: F401 -- tests patch "jarvis.live.registry.asyncio.to_thread"
import functools
from typing import Any

from livekit.agents import function_tool

from jarvis.activity import log_event
from jarvis.capabilities.results import ToolResult
from jarvis.live.debug_results import ToolResultDebug
from jarvis.live.extensions import extension_tools
from jarvis.live.policy import DIRECT_PROMPT_APPS, SAFE_MODE_ALLOWED
from jarvis.live.productivity import productivity_tools
from jarvis.live.registry_factory import create_live_registry
from jarvis.live.registry_runtime import RegistryRuntime
from jarvis.live.toolsets import PLANNER_ONLY_TOOLS, VOICE_TOOL_ORDER, build_tools
from jarvis.planner.engine import PlannerEngine
from jarvis.planner.models import build_planner_model
from jarvis.planner.resources import DesktopGate
from jarvis.planner.tasks import TaskManager

__all__ = [
    "DIRECT_PROMPT_APPS",
    "SAFE_MODE_ALLOWED",
    "ToolRegistry",
    "create_live_registry",
    "create_live_tools",
]


class ToolRegistry(ToolResultDebug, RegistryRuntime):
    def _guard_read_only(self, tool):
        """Return a copy of a voice/planner tool that refuses in safe mode.

        Single enforcement point for safe (read-only) mode. A tool whose name
        is in SAFE_MODE_ALLOWED is returned unchanged; any other tool is wrapped
        so that, while self.read_only_mode is on, it refuses with no side effect
        and nothing sent. The wrapper keeps the original name, description and
        signature, so the schema the model sees is identical — the model simply
        gets a refusal result if it calls a blocked tool in safe mode. The flag
        is read live, so entering safe mode also stops a mission's outward
        sub-actions already in flight (they share these guarded tools).

        Every call is also logged by name (never its arguments) to the local
        activity journal behind the dashboard's Jarvis tab.
        """
        name = tool.info.name
        allowed = name in SAFE_MODE_ALLOWED
        inner = tool._func

        @functools.wraps(inner)
        async def wrapper(*args, **kwargs):
            log_event("tool", name)
            if not allowed and getattr(self, "read_only_mode", False):
                return ToolResult.failure(
                    action=name,
                    message=(
                        "Mode securite actif (lecture seule) : cette action "
                        "modifierait le Mac ou enverrait quelque chose vers "
                        "l'exterieur, donc elle est bloquee et rien n'a ete fait. "
                        "Dis « quitte le mode securite » pour la reactiver."
                    ),
                    error_code="read_only_mode",
                ).to_livekit_dict()
            return await inner(*args, **kwargs)

        return function_tool(name=name, description=tool.info.description)(wrapper)

    def livekit_tools(self) -> list[Any]:
        built = build_tools(self)
        tools = [built[name] for name in VOICE_TOOL_ORDER]

        tools.append(built["dance_avatar"])
        tools.extend(productivity_tools(self))
        tools.extend(extension_tools(self))

        # Single safe-mode enforcement point: every voice and planner tool is
        # routed through the read-only guard, so a mission cannot perform an
        # outward action in safe mode any more than the voice can.
        tools = [self._guard_read_only(tool) for tool in tools]

        # The planner drives these very tools (same locks, journal and pending
        # action store), so a message it prepares is confirmable by voice. It
        # also gets web_answer, a blocking web search kept out of the voice
        # tool set (the voice uses the background search_the_web instead).
        self.planner_tools = [tool for tool in tools if tool.info.name != "dance_avatar"] + [
            self._guard_read_only(built[name]) for name in PLANNER_ONLY_TOOLS]
        if not hasattr(self, "desktop_gate"):
            self.desktop_gate = DesktopGate()
        self.tasks = TaskManager(
            lambda: PlannerEngine(
                self.planner_model or build_planner_model(), self.planner_tools
            ),
            on_finished=self._on_task_finished,
            desktop_gate=self.desktop_gate,
        )
        return tools


def create_live_tools(*args, **kwargs) -> list[Any]:
    return create_live_registry(*args, **kwargs).livekit_tools()
