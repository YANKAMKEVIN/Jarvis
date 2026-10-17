"""Shared Live model/assistant factories, without starting a server on import."""
from jarvis.live.config import LiveConfig, debug_live
from jarvis.live.prompts import LIVE_SYSTEM_PROMPT
from jarvis.live.tools import create_live_registry


def create_realtime_model(google_module, config: LiveConfig):
    debug_live(
        "create_realtime_model",
        model=config.model,
        voice=config.voice,
        temperature=config.temperature,
    )
    return google_module.realtime.RealtimeModel(
        model=config.model,
        voice=config.voice,
        temperature=config.temperature,
        instructions=LIVE_SYSTEM_PROMPT,
    )


def create_assistant_class(agent_base_class, registry_factory=create_live_registry):
    class JarvisLiveAssistant(agent_base_class):
        def __init__(self) -> None:
            self.registry = registry_factory()
            super().__init__(
                instructions=LIVE_SYSTEM_PROMPT,
                tools=self.registry.livekit_tools(),
            )
            # Background tasks finish later: let them speak their result.
            self.registry.set_task_notifier(self.announce)

        async def announce(self, instructions: str) -> None:
            try:
                session = self.session
            except Exception:  # LiveKit raises when no session is running
                session = None
            if session is None:
                debug_live("task_announcement_dropped", reason="no_session")
                return
            try:
                session.generate_reply(instructions=instructions)
            except Exception as error:
                debug_live("task_announcement_failed", error=type(error).__name__)

    return JarvisLiveAssistant


