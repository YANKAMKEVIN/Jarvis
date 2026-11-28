"""Desktop stylesheet, small widget factories and the peek card."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout
from importlib.resources import files as _resource_files


STYLE = """
QWidget { background: transparent; color: #dce8f6; font-family: '.AppleSystemUIFont', 'Inter', 'DejaVu Sans'; font-size: 13px; }
QMainWindow { background: #0b111b; }
QWidget#shell { background: qradialgradient(cx:0.60, cy:0.36, radius:0.8, fx:0.60, fy:0.36, stop:0 #182c3d, stop:0.42 #0c1826, stop:1 #070e18); }
QLabel#wordmark { color: #e4f3ff; font-size: 18px; font-weight: 600; }
QLabel#greeting { color: #eef7ff; font-size: 26px; font-weight: 500; }
QLabel#intro { color: #94abc1; font-size: 14px; }
QLabel#status { color: #a4cbe7; font-size: 12px; }
QPushButton#quiet { background: transparent; border: 1px solid #304659; color: #a7c1d6; }

QLabel { background: transparent; }
QLabel#eyebrow { color: #7794af; font-size: 10px; font-weight: 600; }
QLabel#title { font-size: 27px; font-weight: 600; }
QLabel#subtitle { color: #91a9c1; font-size: 12px; }
QFrame#sidebar { background: rgba(7, 14, 24, 175); border-right: 1px solid #1d3041; }
QFrame#controlDock { background: rgba(20, 36, 51, 105); border: 1px solid rgba(119, 180, 212, 30); border-radius: 17px; }
QFrame#card { background: rgba(26, 43, 61, 155); border: 1px solid #293e52; border-radius: 16px; }
QPushButton { background: #1a2a3d; border: 1px solid #2b435c; border-radius: 9px; padding: 10px 14px; }
QPushButton:hover { background: #243d57; border-color: #517ca2; }
QPushButton:pressed { background: #131f2e; border-color: #517ca2; padding: 11px 14px 9px 14px; }
QPushButton:focus { border: 1px solid #83cfff; }
QPushButton:disabled { color: #647b90; background: #152030; }
QPushButton#primary:hover { background: #b8e4ff; }
QPushButton#primary { background: #82caff; color: #081421; border: 0; font-weight: 600; }
QPushButton#primary:pressed { background: #5fa9de; }
QPushButton#quiet:hover { background: #17273a; border-color: #517ca2; color: #e0f1ff; }
QPushButton#quiet:pressed { background: #0f1a28; }
QPushButton#primary:disabled { background: #223247; color: #8096ab; }
QPushButton#cancelTask, QPushButton#cancelMission { background: transparent; border: 1px solid #7d4a5c; color: #f0b3c3; }
QPushButton#cancelTask:hover, QPushButton#cancelMission:hover { background: #3a2030; border-color: #ee99b9; }
QPushButton#cancelTask:pressed, QPushButton#cancelMission:pressed { background: #2a1722; }
QPushButton#cancelTask:disabled, QPushButton#cancelMission:disabled { background: transparent; border-color: #3d3442; color: #7d6873; }
QFrame#peek { background: rgba(36, 65, 86, 65); border: 1px solid #29465c; border-radius: 14px; }
QFrame#peek:hover { background: rgba(46, 80, 104, 90); border-color: #517ca2; }
QFrame#peek:focus { border-color: #83cfff; }
QLabel#peekTitle { color: #e4f3ff; font-size: 14px; font-weight: 600; }
QFrame#errorBanner { background: rgba(120, 40, 62, 70); border: 1px solid #7d4a5c; border-radius: 14px; }
QLabel#errorIcon { color: #1b0d14; background: #ee99b9; border-radius: 11px; font-weight: 700; }
QLabel#errorText { color: #f6ccd6; }
QPushButton#nav { text-align: left; background: transparent; border: 0; padding: 13px 13px 13px 44px; color: #91a9c1; }
QPushButton#nav:hover { color: #e0f1ff; background: #17273a; }
QPushButton#nav:pressed { background: #101b29; padding: 14px 13px 12px 44px; }
QPushButton#nav:checked { color: #e0f1ff; background: #22354b; }
QPushButton#nav:checked:hover { background: #283e57; }
QPushButton#copyCard { background: transparent; border: 1px solid #304659; color: #a7c1d6; padding: 6px 12px; font-size: 12px; }
QPushButton#copyCard:hover { background: #243d57; border-color: #517ca2; color: #e0f1ff; }
QPushButton#copyCard:pressed { background: #131f2e; padding: 7px 12px 5px 12px; }
QPushButton#chip:pressed { padding: 6px 12px 4px 12px; }
QPushButton#chip { border-radius: 13px; padding: 5px 12px; font-size: 12px; color: #bfdeed; }
QPushButton#tool { text-align: left; background: transparent; border: 0; padding: 8px 13px; color: #91a9c1; font-size: 12px; }
QPushButton#tool:hover { color: #e0f1ff; background: #17273a; }
QPushButton#tool:pressed { background: #101b29; padding: 9px 13px 7px 13px; }
QPushButton#tool:focus { border: 1px solid #83cfff; padding: 7px 12px; }
QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { background: #101927; width: 7px; }
QScrollBar::handle:vertical { background: #344c63; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox { spacing: 10px; padding: 8px 0; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #52708a; border-radius: 4px; background: #0b1825; }
QCheckBox::indicator:checked { background: #87dcff; border-color: #b5edff; }
QComboBox { background: #132537; border: 1px solid #31495f; border-radius: 8px; padding: 7px; min-height: 18px; }
QComboBox QAbstractItemView { background: #132537; color: #dce8f6; selection-background-color: #29485f; }
QProgressBar { background: #192c3d; border: 1px solid #314b60; border-radius: 4px; min-height: 8px; max-height: 8px; }
QProgressBar::chunk { background: #87d9ff; border-radius: 3px; }
QToolTip { background: #23384f; color: #e1efff; border: 1px solid #527494; }
QMenu { background: #152235; border: 1px solid #344d67; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #29435f; }
QMenu::item:disabled { color: #7b91a6; }
"""
STYLE += '\nQCheckBox::indicator:checked { image: url("'+str(_resource_files('jarvis.desktop').joinpath('assets','icons','check.svg'))+'"); }'

def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


def card(title, text):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(9)
    layout.addWidget(label(title, "eyebrow"))
    layout.addWidget(label(text))
    return frame


def section(title, parent):
    """Titled settings group; returns the layout that receives its controls."""
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 14, 18, 14)
    layout.setSpacing(6)
    layout.addWidget(label(title, "eyebrow"))
    parent.addWidget(frame)
    return layout


class PeekCard(QFrame):
    """Preview of the latest result card under the orb; the whole card opens Cartes."""
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName('peek')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setToolTip('Ouvrir cette carte')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 11)
        layout.setSpacing(3)
        self.title = label('', 'peekTitle')
        self.title.setWordWrap(False)
        self.summary = label('', 'subtitle')
        self.summary.setMaximumHeight(self.summary.fontMetrics().lineSpacing() * 2 + 2)
        for widget in (self.title, self.summary):
            widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(widget)

    def show_card(self, title, summary):
        self.title.setText(title)
        self.summary.setText(summary)
        self.summary.setVisible(bool(summary))
        self.setAccessibleName('Dernière carte : ' + title + ('. ' + summary if summary else '') + ' Ouvrir les cartes.')

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self.clicked.emit()
            event.accept()
        else:
            super().keyPressEvent(event)
