from jarvis.live.config import (
    LiveConfig,
    debug_live,
    get_live_config,
)
from jarvis.live.logging import install_livekit_pii_log_filter
from jarvis.live.prompts import LIVE_SESSION_GREETING, LIVE_SYSTEM_PROMPT
from jarvis.live.tools import create_live_registry


LIVEKIT_RECORDING_OPTIONS = {
    "redaction": True,
}


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


def build_live_server(config: LiveConfig | None = None):
    install_livekit_pii_log_filter()

    try:
        from livekit.agents import (
            Agent,
            AgentServer,
            AgentSession,
            JobContext,
        )
        from livekit.plugins import google
    except ImportError as error:
        raise RuntimeError(
            "Le POC LiveKit/Gemini Live nécessite les dépendances "
            "LiveKit. Installe-les avec : "
            'python -m pip install -r requirements-live.txt'
        ) from error

    config = config or get_live_config()
    assistant_class = create_assistant_class(Agent)
    server = AgentServer()

    @server.rtc_session(agent_name=config.agent_name)
    async def jarvis_live_agent(ctx: JobContext):
        debug_live(
            "session_starting",
            agent_name=config.agent_name,
            model=config.model,
        )
        session = AgentSession(
            llm=create_realtime_model(google, config),
        )

        await session.start(
            agent=assistant_class(),
            room=ctx.room,
            record=LIVEKIT_RECORDING_OPTIONS,
        )
        debug_live("session_started", agent_name=config.agent_name)

        await session.generate_reply(
            instructions=LIVE_SESSION_GREETING,
        )
        debug_live("initial_reply_requested", agent_name=config.agent_name)

    return server


def main() -> None:
    try:
        from livekit.agents import cli
    except ImportError as error:
        raise RuntimeError(
            "Le POC LiveKit/Gemini Live nécessite les dépendances "
            "LiveKit. Installe-les avec : "
            'python -m pip install -r requirements-live.txt'
        ) from error

    config = get_live_config()
    debug_live(
        "server_boot",
        agent_name=config.agent_name,
        model=config.model,
    )
    cli.run_app(server)


server = build_live_server()


if __name__ == "__main__":
    main()
