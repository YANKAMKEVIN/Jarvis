"""First-launch permission onboarding for the desktop app.

macOS only grants TCC permissions when the matching API is first exercised, so
without guidance the user meets Microphone, Calendar, Reminders and Automation
prompts scattered across their first few sentences. This module gathers them
into one explained first-run screen: what Jarvis will ask for, why, the current
status, a button to request what can be requested programmatically, and a deep
link to the right System Settings pane for the rest.

The logic is split so it stays testable off a real Mac:
- needs_onboarding / mark_done persist a version in QSettings (pure).
- permission_items merges the permission specs with an injected status
  snapshot (pure).
- default_snapshot / request_permission / open_settings are the native,
  best-effort side (never raise); the dialog takes them injected so tests pass
  fakes and never touch TCC.
"""
from __future__ import annotations

from dataclasses import dataclass


# Bump when the set of onboarding permissions changes so returning users see the
# screen again for the new item.
ONBOARDING_VERSION = 1
_SETTINGS_KEY = "onboarding/version"

_SETTINGS_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_"


@dataclass(frozen=True)
class PermissionSpec:
    key: str
    title: str
    why: str
    pane: str          # System Settings privacy pane suffix
    requestable: bool  # can be triggered programmatically (else: manual toggle)

    @property
    def settings_url(self) -> str:
        return _SETTINGS_PANE + self.pane


# Order shown to the user: the voice/agenda core first, system control last.
PERMISSIONS: tuple[PermissionSpec, ...] = (
    PermissionSpec(
        "microphone", "Microphone",
        "Pour vous entendre quand vous activez le vocal. Le micro ne s'ouvre "
        "que pendant une session vocale.",
        "Microphone", False,
    ),
    PermissionSpec(
        "calendar", "Calendrier",
        "Pour lire votre agenda et proposer des créneaux, uniquement à votre "
        "demande.",
        "Calendars", True,
    ),
    PermissionSpec(
        "reminders", "Rappels",
        "Pour lire et créer des rappels, uniquement à votre demande.",
        "Reminders", True,
    ),
    PermissionSpec(
        "automation", "Automatisation",
        "Pour piloter d'autres apps (Mail, WhatsApp, Calendrier...) afin "
        "d'exécuter ce que vous demandez.",
        "Automation", False,
    ),
    PermissionSpec(
        "accessibility", "Accessibilité",
        "Pour contrôler les fenêtres, le clavier et la souris quand une action "
        "le nécessite.",
        "Accessibility", False,
    ),
    PermissionSpec(
        "screen_recording", "Enregistrement de l'écran",
        "Pour lire ou décrire votre écran quand vous le demandez.",
        "ScreenCapture", True,
    ),
)


def needs_onboarding(settings) -> bool:
    """True until the user has gone through the current onboarding version."""
    try:
        seen = settings.value(_SETTINGS_KEY)
    except Exception:
        return False
    try:
        return int(seen) < ONBOARDING_VERSION
    except (TypeError, ValueError):
        return True


def mark_done(settings) -> None:
    try:
        settings.setValue(_SETTINGS_KEY, ONBOARDING_VERSION)
    except Exception:
        pass


def permission_items(snapshot: dict | None = None) -> list[dict]:
    """Display rows merging each permission spec with its status.

    status is True (granted), False (to authorize) or None (unknown — e.g. a
    grant macOS does not let us read, such as Automation). snapshot maps a
    permission key to that tri-state; missing keys are unknown.
    """
    snapshot = snapshot or {}
    rows = []
    for spec in PERMISSIONS:
        status = snapshot.get(spec.key)
        rows.append({
            "key": spec.key,
            "title": spec.title,
            "why": spec.why,
            "requestable": spec.requestable,
            "settings_url": spec.settings_url,
            "status": status,
            "status_text": (
                "accordé" if status is True
                else "à autoriser" if status is False
                else "au premier usage"
            ),
        })
    return rows


# --- native, best-effort side (never raises) -------------------------------


def _accessibility_granted() -> bool | None:
    try:
        import ctypes

        ax = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        ax.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(ax.AXIsProcessTrusted())
    except Exception:
        return None


def _screen_recording_granted() -> bool | None:
    try:
        import ctypes

        cg = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        return bool(cg.CGPreflightScreenCaptureAccess())
    except Exception:
        return None


def _eventkit_granted(entity: int) -> bool | None:
    try:
        import EventKit  # type: ignore

        from jarvis.tools.eventkit_calendar import AUTHORIZED_STATUSES

        status = int(EventKit.EKEventStore.authorizationStatusForEntityType_(entity))
        return status in AUTHORIZED_STATUSES
    except Exception:
        return None


def default_snapshot() -> dict:
    """Best-effort current status of each permission. Never raises.

    Microphone and Automation have no readable preflight here, so they stay
    unknown (None) and are presented as "asked at first use".
    """
    return {
        "accessibility": _accessibility_granted(),
        "screen_recording": _screen_recording_granted(),
        "calendar": _eventkit_granted(0),
        "reminders": _eventkit_granted(1),
        "microphone": None,
        "automation": None,
    }


def open_settings(url: str) -> bool:
    """Open a System Settings privacy pane. Returns whether it was attempted."""
    try:
        import subprocess

        subprocess.run(["open", url], check=False, timeout=5)
        return True
    except Exception:
        return False


def request_permission(key: str) -> bool:
    """Trigger the TCC prompt for a requestable permission, best effort.

    Calendar, Reminders and Screen Recording can be requested programmatically;
    the rest (Microphone, Automation, Accessibility) only prompt from their own
    API path or a manual toggle, so those open the System Settings pane instead.
    Returns whether a request/open was attempted. Never raises.
    """
    try:
        if key in ("calendar", "reminders"):
            import EventKit  # type: ignore

            entity = 0 if key == "calendar" else 1
            store = EventKit.EKEventStore.alloc().init()
            # Fire and forget: the system shows the prompt; the result is read
            # back later through default_snapshot / the calendar tools.
            store.requestAccessToEntityType_completion_(entity, lambda granted, error: None)
            return True
        if key == "screen_recording":
            import ctypes

            cg = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            cg.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
            cg.CGRequestScreenCaptureAccess()
            return True
    except Exception:
        return False
    # Microphone / Automation / Accessibility: send the user to the pane.
    spec = {spec.key: spec for spec in PERMISSIONS}.get(key)
    return open_settings(spec.settings_url) if spec is not None else False


# --- Qt dialog (imported lazily so the logic above needs no PySide6) --------


# Dark theme matching the app, so the dialog is never pale text on a white
# window (QDialog's default background).
_DIALOG_STYLE = """
#onboarding { background: #0c1826; }
#onboarding QLabel { color: #c4d6e8; background: transparent; }
#onboarding QLabel#ob_heading { color: #eef7ff; font-size: 16px; font-weight: 600; }
#onboarding QLabel#ob_intro { color: #91a9c1; font-size: 12px; }
#onboarding QLabel#ob_why { color: #9fb6cc; font-size: 12px; }
#onboarding QFrame#ob_row { background: rgba(26, 43, 61, 130); border: 1px solid #243a4e; border-radius: 12px; }
#onboarding QScrollArea { background: transparent; border: 0; }
#onboarding QPushButton { background: #1a2a3d; border: 1px solid #2b435c; border-radius: 9px; padding: 8px 13px; color: #dce8f6; }
#onboarding QPushButton:hover { background: #243d57; border-color: #517ca2; }
#onboarding QPushButton#primary { background: #82caff; color: #081421; border: 0; font-weight: 600; padding: 9px 20px; }
#onboarding QPushButton#primary:hover { background: #b8e4ff; }
#onboarding QScrollBar:vertical { background: #101927; width: 8px; margin: 0; }
#onboarding QScrollBar::handle:vertical { background: #344c63; border-radius: 4px; min-height: 24px; }
#onboarding QScrollBar::add-line:vertical, #onboarding QScrollBar::sub-line:vertical { height: 0; }
"""

_STATUS_CHIP = {True: "#7fd1a6", False: "#e8b971", None: "#8fa6bd"}


def _chip(status) -> str:
    return _STATUS_CHIP.get(status, "#8fa6bd")


def _header_html(title: str, status_text: str, chip: str) -> str:
    return (
        f"<span style='font-size:14px;font-weight:600;color:#eef7ff'>{title}</span>"
        f"&nbsp;&nbsp;<span style='font-size:12px;color:{chip}'>{status_text}</span>"
    )


def make_onboarding_dialog(
    settings,
    snapshot: dict | None = None,
    request=request_permission,
    open_settings_fn=open_settings,
    parent=None,
):
    """Build the first-run onboarding dialog.

    settings: a QSettings-like object (marked done on finish). snapshot/request/
    open_settings_fn are injectable so tests drive the dialog without touching
    TCC. Returns a QDialog. Call .exec() (blocking) or .show().
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
        QVBoxLayout, QWidget,
    )

    items = permission_items(snapshot if snapshot is not None else default_snapshot())

    dialog = QDialog(parent)
    dialog.setObjectName("onboarding")
    dialog.setWindowTitle("Jarvis — autorisations")
    dialog.setModal(True)
    dialog.setStyleSheet(_DIALOG_STYLE)
    dialog.setMinimumSize(500, 560)
    dialog.rows = {}

    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(22, 20, 22, 18)
    outer.setSpacing(12)

    heading = QLabel("Bienvenue. Voici ce que Jarvis peut demander — et pourquoi.")
    heading.setObjectName("ob_heading")
    heading.setWordWrap(True)
    outer.addWidget(heading)
    intro = QLabel(
        "Vous pouvez tout autoriser maintenant ou plus tard : rien n'est "
        "obligatoire, et chaque action reste sur demande. Les autorisations se "
        "règlent aussi à tout moment dans Réglages Système."
    )
    intro.setObjectName("ob_intro")
    intro.setWordWrap(True)
    outer.addWidget(intro)

    body = QWidget()
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(0, 2, 6, 2)
    body_layout.setSpacing(10)

    for item in items:
        row = QFrame()
        row.setObjectName("ob_row")
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(14, 12, 14, 12)
        row_layout.setSpacing(6)

        header = QLabel(_header_html(item["title"], item["status_text"], _chip(item["status"])))
        header.setTextFormat(Qt.TextFormat.RichText)
        row_layout.addWidget(header)

        why = QLabel(item["why"])
        why.setObjectName("ob_why")
        why.setWordWrap(True)
        row_layout.addWidget(why)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        request_button = None
        if item["status"] is not True:
            label = "Demander l'autorisation" if item["requestable"] else "Ouvrir les Réglages"
            request_button = QPushButton(label)

            def _make_request(key=item["key"], title=item["title"], header=header,
                              requestable=item["requestable"]):
                def handler():
                    if requestable:
                        request(key)
                        header.setText(_header_html(title, "demande envoyée · vérifiez Réglages", "#e8b971"))
                    else:
                        spec = {s.key: s for s in PERMISSIONS}[key]
                        open_settings_fn(spec.settings_url)
                return handler

            request_button.clicked.connect(_make_request())
            buttons.addWidget(request_button)

        settings_button = QPushButton("Réglages Système")

        def _make_open(url=item["settings_url"]):
            return lambda: open_settings_fn(url)

        settings_button.clicked.connect(_make_open())
        buttons.addWidget(settings_button)
        buttons.addStretch()
        row_layout.addLayout(buttons)

        body_layout.addWidget(row)
        dialog.rows[item["key"]] = {
            "title": header,
            "request": request_button,
            "settings": settings_button,
        }

    body_layout.addStretch()
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(body)
    outer.addWidget(scroll, 1)

    finish = QPushButton("Terminer")
    finish.setObjectName("primary")

    def _finish():
        mark_done(settings)
        dialog.accept()

    finish.clicked.connect(_finish)
    dialog.finish_button = finish

    footer = QHBoxLayout()
    footer.addStretch()
    footer.addWidget(finish)
    outer.addLayout(footer)
    return dialog
