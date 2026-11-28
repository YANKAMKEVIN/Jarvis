"""Debug logging helpers of the Live tool registry."""
from jarvis.live.config import debug_live, is_vision_enabled
from jarvis.live.registry_base import RegistryCapabilities


class ToolResultDebug(RegistryCapabilities):
    """Metadata-only debug logging of tool results, plus small guards.

    Never logs message content, typed text, full paths or full URLs.
    """

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
            "active_host": ToolResultDebug._debug_host(result.data.get("active_url")),
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

    def _messaging_check(self, name: str, app_name: str) -> bool:
        """Ask the messaging capability a per-app question (is_api_app,
        requires_recipient, supports_verified_send). A capability without the
        newer API-aware checks is treated as UI-only (composer send)."""
        check = getattr(self.messaging, name, None)
        if callable(check):
            return bool(check(app_name))
        if name == "supports_verified_send":
            return bool(self.messaging.supports_composer_send(app_name))
        return False

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

