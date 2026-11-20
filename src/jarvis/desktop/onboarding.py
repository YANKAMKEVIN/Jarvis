"""First-launch permission onboarding for the desktop app.

macOS only grants TCC permissions when the matching API is first exercised, so
without guidance the user meets Microphone, Calendar, Reminders and Automation
prompts scattered across their first few sentences. This module gathers them
into one explained first-run walkthrough, one permission per step: what Jarvis
will ask for, why, the current status, a button to request what can be requested
programmatically, and a deep link to the right System Settings pane for the
rest. Only the microphone matters up front; every other step can wait until its
first use.

The logic is split so it stays testable off a real Mac:
- needs_onboarding / mark_done persist a version in QSettings (pure).
- permission_items merges the permission specs with an injected status
  snapshot (pure); onboarding_steps orders them into the walkthrough (pure).
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


# The only permission the voice needs from the first sentence.
ESSENTIAL = "microphone"


def onboarding_steps(snapshot: dict | None = None) -> list[dict]:
    """Walkthrough steps: the microphone first, then what can wait, then a recap.

    Each permission step is its display row plus `essential` and a `note` that
    tells whether it is needed now or only asked at first use. The last step has
    key "done" and carries no permission.
    """
    rows = permission_items(snapshot)
    rows.sort(key=lambda row: row["key"] != ESSENTIAL)  # stable: keeps the declared order
    steps = []
    for row in rows:
        essential = row["key"] == ESSENTIAL
        steps.append({
            **row,
            "essential": essential,
            "note": (
                "Déjà accordé." if row["status"] is True
                else "Indispensable pour parler à Jarvis. macOS le demande au premier démarrage du vocal."
                if essential else "Peut attendre : plus tard, au premier usage."
            ),
        })
    steps.append({"key": "done", "title": "Tout est prêt", "essential": False, "note": ""})
    return steps


def step_caption(index: int, steps: list[dict]) -> str:
    """« Étape 2 sur 7 · Calendrier » for the progress line."""
    return f"Étape {index + 1} sur {len(steps)} · {steps[index]['title']}"


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
#onboarding QLabel#ob_why { color: #c4d6e8; font-size: 13px; }
#onboarding QLabel#ob_step { color: #7794af; font-size: 10px; font-weight: 600; }
#onboarding QLabel#ob_note { color: #91a9c1; font-size: 12px; }
#onboarding QLabel#ob_recap { color: #c4d6e8; font-size: 12px; }
#onboarding QProgressBar { background: #192c3d; border: 1px solid #314b60; border-radius: 4px; min-height: 6px; max-height: 6px; }
#onboarding QProgressBar::chunk { background: #87d9ff; border-radius: 3px; }
#onboarding QFrame#ob_row { background: rgba(26, 43, 61, 130); border: 1px solid #243a4e; border-radius: 12px; }
#onboarding QPushButton { background: #1a2a3d; border: 1px solid #2b435c; border-radius: 9px; padding: 8px 13px; color: #dce8f6; }
#onboarding QPushButton:hover { background: #243d57; border-color: #517ca2; }
#onboarding QPushButton:pressed { background: #131f2e; }
#onboarding QPushButton:disabled { color: #647b90; background: #152030; }
#onboarding QPushButton#ob_later { background: transparent; border: 1px solid #304659; color: #a7c1d6; }
#onboarding QPushButton#primary { background: #82caff; color: #081421; border: 0; font-weight: 600; padding: 9px 20px; }
#onboarding QPushButton#primary:hover { background: #b8e4ff; }
#onboarding QPushButton#primary:pressed { background: #5fa9de; }
"""

_STATUS_CHIP = {True: "#7fd1a6", False: "#e8b971", None: "#8fa6bd"}


def _chip(status) -> str:
    return _STATUS_CHIP.get(status, "#8fa6bd")


def _header_html(title: str, status_text: str, chip: str) -> str:
    return (
        f"<span style='font-size:20px;font-weight:600;color:#eef7ff'>{title}</span>"
        f"&nbsp;&nbsp;<span style='font-size:12px;color:{chip}'>{status_text}</span>"
    )


def make_onboarding_dialog(
    settings,
    snapshot: dict | None = None,
    request=request_permission,
    open_settings_fn=open_settings,
    parent=None,
):
    """Build the first-run onboarding walkthrough.

    settings: a QSettings-like object (marked done on finish). snapshot/request/
    open_settings_fn are injectable so tests drive the dialog without touching
    TCC. Returns a QDialog. Call .exec() (blocking) or .show().

    One permission per page, the microphone first; `dialog.rows` maps each
    permission key to its widgets, `dialog.go(index)` moves between pages and
    `dialog.finish_button` (on the last page) marks the onboarding done.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
        QStackedWidget, QVBoxLayout,
    )

    steps = onboarding_steps(snapshot if snapshot is not None else default_snapshot())

    dialog = QDialog(parent)
    dialog.setObjectName("onboarding")
    dialog.setWindowTitle("Jarvis — autorisations")
    dialog.setModal(True)
    dialog.setStyleSheet(_DIALOG_STYLE)
    dialog.setMinimumSize(500, 430)
    dialog.rows = {}
    dialog.steps = steps

    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(22, 20, 22, 18)
    outer.setSpacing(12)

    heading = QLabel("Bienvenue. Préparons Jarvis, une autorisation à la fois.")
    heading.setObjectName("ob_heading")
    heading.setWordWrap(True)
    outer.addWidget(heading)
    intro = QLabel(
        "Seul le micro compte pour commencer. Le reste peut attendre : rien n'est "
        "obligatoire, chaque action reste sur demande, et tout se règle à tout "
        "moment dans Réglages Système."
    )
    intro.setObjectName("ob_intro")
    intro.setWordWrap(True)
    outer.addWidget(intro)

    progress = QProgressBar()
    progress.setRange(0, len(steps))
    progress.setTextVisible(False)
    progress.setAccessibleName("Avancement de l'accueil")
    outer.addWidget(progress)
    step_label = QLabel()
    step_label.setObjectName("ob_step")
    outer.addWidget(step_label)

    pages = QStackedWidget()
    recap = {}

    for item in steps[:-1]:
        row = QFrame()
        row.setObjectName("ob_row")
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(18, 16, 18, 16)
        row_layout.setSpacing(10)

        header = QLabel(_header_html(item["title"], item["status_text"], _chip(item["status"])))
        header.setTextFormat(Qt.TextFormat.RichText)
        row_layout.addWidget(header)

        why = QLabel(item["why"])
        why.setObjectName("ob_why")
        why.setWordWrap(True)
        row_layout.addWidget(why)

        note = QLabel(item["note"])
        note.setObjectName("ob_note")
        note.setWordWrap(True)
        row_layout.addWidget(note)
        row_layout.addStretch()

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
                        recap[key].setText(f"{title} · demande envoyée")
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

        pages.addWidget(row)
        dialog.rows[item["key"]] = {
            "title": header,
            "request": request_button,
            "settings": settings_button,
            "note": note,
        }

    # Last page: where each permission stands, and what to try first.
    done = QFrame()
    done.setObjectName("ob_row")
    done_layout = QVBoxLayout(done)
    done_layout.setContentsMargins(18, 16, 18, 16)
    done_layout.setSpacing(7)
    done_title = QLabel(_header_html("Tout est prêt", "", "#7fd1a6"))
    done_title.setTextFormat(Qt.TextFormat.RichText)
    done_layout.addWidget(done_title)
    for item in steps[:-1]:
        line = QLabel(f"{item['title']} · {item['status_text']}")
        line.setObjectName("ob_recap")
        done_layout.addWidget(line)
        recap[item["key"]] = line
    done_layout.addStretch()
    trial = QLabel(
        "Pour un premier essai : démarrez Jarvis, puis dites « Quelle heure est-il ? ». "
        "macOS demandera alors l'accès au micro."
    )
    trial.setObjectName("ob_why")
    trial.setWordWrap(True)
    done_layout.addWidget(trial)
    pages.addWidget(done)
    outer.addWidget(pages, 1)

    back = QPushButton("Précédent")
    later = QPushButton("Plus tard")
    later.setObjectName("ob_later")
    later.setToolTip("Passer cette autorisation : macOS la demandera au premier usage.")
    forward = QPushButton("Suivant")
    forward.setObjectName("primary")
    finish = QPushButton("Terminer")
    finish.setObjectName("primary")

    def go(index):
        index = max(0, min(index, len(steps) - 1))
        step = steps[index]
        last = index == len(steps) - 1
        pages.setCurrentIndex(index)
        progress.setValue(index + 1)
        step_label.setText(step_caption(index, steps).upper())
        back.setEnabled(index > 0)
        # "Plus tard" only where there is something to postpone.
        later.setVisible(not last and not step["essential"] and step.get("status") is not True)
        forward.setVisible(not last)
        finish.setVisible(last)
        (finish if last else forward).setDefault(True)

    def _finish():
        mark_done(settings)
        dialog.accept()

    back.clicked.connect(lambda: go(pages.currentIndex() - 1))
    later.clicked.connect(lambda: go(pages.currentIndex() + 1))
    forward.clicked.connect(lambda: go(pages.currentIndex() + 1))
    finish.clicked.connect(_finish)
    dialog.finish_button = finish
    dialog.back_button, dialog.later_button, dialog.next_button = back, later, forward
    dialog.pages, dialog.progress, dialog.step_label, dialog.go = pages, progress, step_label, go

    footer = QHBoxLayout()
    footer.addWidget(back)
    footer.addStretch()
    footer.addWidget(later)
    footer.addWidget(forward)
    footer.addWidget(finish)
    outer.addLayout(footer)
    go(0)
    return dialog
