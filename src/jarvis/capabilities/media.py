from jarvis.capabilities.results import ToolResult
from jarvis.intents import create_intent
from jarvis.security import SecurityManager
from jarvis.tools.macos import MacOSTools


class MediaCapability:
    def __init__(
        self,
        security=None,
        macos_tools=None,
    ):
        self.security = security if security is not None else SecurityManager()
        self.macos_tools = macos_tools if macos_tools is not None else MacOSTools()

    def play_pause(self) -> ToolResult:
        decision = self.security.evaluate(create_intent("play_pause"))

        if not decision.allowed:
            return self._security_denied_result(
                action="play_pause",
                reason=decision.reason,
            )

        if decision.requires_confirmation:
            return self._confirmation_required_result(
                action="play_pause",
                reason=decision.reason,
            )

        try:
            state = self.macos_tools.play_pause()
        except Exception as error:
            return self._system_error_result("play_pause", error)

        message = self._message_from_state(
            state,
            playing_message="La lecture est en cours.",
            paused_message="La lecture est en pause.",
        )
        return ToolResult.success(
            action="play_pause",
            message=message,
            **state,
        )

    def next_track(self) -> ToolResult:
        decision = self.security.evaluate(create_intent("next_track"))

        if not decision.allowed:
            return self._security_denied_result(
                action="next_track",
                reason=decision.reason,
            )

        if decision.requires_confirmation:
            return self._confirmation_required_result(
                action="next_track",
                reason=decision.reason,
            )

        try:
            state = self.macos_tools.next_track()
        except Exception as error:
            return self._system_error_result("next_track", error)

        message = self._track_message(
            state,
            fallback="Je suis passe au morceau suivant.",
        )
        return ToolResult.success(
            action="next_track",
            message=message,
            **state,
        )

    def previous_track(self) -> ToolResult:
        decision = self.security.evaluate(create_intent("previous_track"))

        if not decision.allowed:
            return self._security_denied_result(
                action="previous_track",
                reason=decision.reason,
            )

        if decision.requires_confirmation:
            return self._confirmation_required_result(
                action="previous_track",
                reason=decision.reason,
            )

        try:
            state = self.macos_tools.previous_track()
        except Exception as error:
            return self._system_error_result("previous_track", error)

        message = self._track_message(
            state,
            fallback="Je suis revenu au morceau precedent.",
        )
        return ToolResult.success(
            action="previous_track",
            message=message,
            **state,
        )

    def get_media_state(self) -> ToolResult:
        try:
            state = self.macos_tools.get_media_state()
        except Exception as error:
            return self._system_error_result("get_media_state", error)

        if not state.get("media_available"):
            return ToolResult.success(
                action="get_media_state",
                message="Aucun media compatible n'est actif actuellement.",
                **state,
            )

        return ToolResult.success(
            action="get_media_state",
            message=self._media_state_message(state),
            **state,
        )

    @staticmethod
    def _media_state_message(state: dict) -> str:
        title = state.get("title")
        artist = state.get("artist")
        app = state.get("app")
        playing = state.get("playing")

        if title and artist:
            status = "en cours de lecture" if playing else "en pause"
            return f"{title} de {artist} est {status} dans {app}."

        if title:
            status = "en cours de lecture" if playing else "en pause"
            return f"{title} est {status} dans {app}."

        if playing:
            return f"Un media est en cours de lecture dans {app}."

        return f"Un media est en pause dans {app}."

    @classmethod
    def _track_message(cls, state: dict, fallback: str) -> str:
        if state.get("track_changed") is False:
            return (
                "La commande media a ete executee, mais aucun changement "
                "de piste n'a ete observe."
            )

        if state.get("title"):
            return cls._media_state_message(state)

        return fallback

    @staticmethod
    def _message_from_state(
        state: dict,
        playing_message: str,
        paused_message: str,
    ) -> str:
        if state.get("title"):
            return MediaCapability._media_state_message(state)

        if state.get("playing"):
            return playing_message

        return paused_message

    @staticmethod
    def _security_denied_result(action: str, reason: str) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message="Jarvis n'est pas autorise a controler la lecture media.",
            error_code="security_denied",
            reason=reason,
        )

    @staticmethod
    def _confirmation_required_result(action: str, reason: str) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message=(
                "Cette action necessite une confirmation non disponible "
                "en mode Live."
            ),
            error_code="confirmation_required",
            requires_confirmation=True,
            reason=reason,
        )

    @staticmethod
    def _system_error_result(action: str, error: Exception) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message=f"Echec du controle media : {error}",
            error_code="system_error",
        )
