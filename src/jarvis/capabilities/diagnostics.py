"""Self-check: report which capabilities and permissions are available.

Read-only. Each check is a callable returning (ok, detail); defaults probe the
real system (TCC grants, vision toggle, local model, IMAP config) but every
check is injectable so the capability is fully testable offline.
"""

from __future__ import annotations

from typing import Callable

from jarvis.capabilities.results import ToolResult


Check = Callable[[], "tuple[bool, str]"]


class DiagnosticsCapability:
    def __init__(self, checks: dict[str, Check] | None = None):
        self._checks = checks if checks is not None else _default_checks()

    def self_check(self) -> ToolResult:
        results: dict[str, dict] = {}
        missing: list[str] = []
        for name, check in self._checks.items():
            try:
                ok, detail = check()
            except Exception as error:
                ok, detail = False, f"erreur : {error}"
            results[name] = {"ok": bool(ok), "detail": detail}
            if not ok:
                missing.append(name)

        available = [n for n in results if results[n]["ok"]]
        if missing:
            message = (
                f"{len(available)} capacite(s) disponible(s). "
                f"A verifier : {', '.join(missing)}."
            )
        else:
            message = f"Tout est operationnel ({len(available)} verifications OK)."

        return ToolResult.success(
            action="self_check",
            message=message,
            checks=results,
            available=available,
            missing=missing,
        )


def _default_checks() -> dict[str, Check]:
    return {
        "accessibility": _accessibility,
        "screen_recording": _screen_recording,
        "vision": _vision,
        "local_model": _local_model,
        "imap_mail": _imap,
    }


def _accessibility() -> tuple[bool, str]:
    import ctypes

    ax = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    )
    ax.AXIsProcessTrusted.restype = ctypes.c_bool
    ok = bool(ax.AXIsProcessTrusted())
    return ok, "accorde" if ok else "a autoriser dans Confidentialite > Accessibilite"


def _screen_recording() -> tuple[bool, str]:
    import ctypes

    cg = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )
    cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
    ok = bool(cg.CGPreflightScreenCaptureAccess())
    return ok, "accorde" if ok else "a autoriser dans Confidentialite > Enregistrement de l'ecran"


def _vision() -> tuple[bool, str]:
    from jarvis.live.config import is_vision_enabled

    ok = is_vision_enabled()
    return ok, "activee" if ok else "desactivee (JARVIS_VISION_ENABLED=1 pour l'activer)"


def _local_model() -> tuple[bool, str]:
    import socket

    try:
        with socket.create_connection(("localhost", 11434), timeout=1.5):
            return True, "Ollama repond sur le port 11434"
    except Exception:
        return False, "Ollama injoignable (lance Ollama pour le planner/local)"


def _imap() -> tuple[bool, str]:
    from jarvis.tools.imap_mail import ImapMailReader

    ok = ImapMailReader().configured()
    return ok, "configure" if ok else "non configure (JARVIS_IMAP_HOST / JARVIS_IMAP_USER)"
