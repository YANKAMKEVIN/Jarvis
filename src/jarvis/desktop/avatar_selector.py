"""Native icon grid: arrows, Tab, Space to preview, Return to validate, Escape to
cancel; no animated thumbnails. A click previews the appearance live; Valider
keeps it, Annuler (or Escape, or closing the window) restores the one Jarvis had
when the dialog opened."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QAbstractItemView, QDialogButtonBox
from jarvis.desktop.appearances import CATALOG
from jarvis.desktop.avatar_assets import pose_image
from jarvis.desktop.avatar_motion import PROFILES

class AppearanceGrid(QListWidget):
    previewed = Signal(QListWidgetItem)
    def keyPressEvent(self, event):
        item = self.currentItem()
        if item is not None and event.key() == Qt.Key.Key_Space:
            self.previewed.emit(item)
            event.accept()
        elif item is not None and event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self.itemActivated.emit(item)
            event.accept()
        else:
            super().keyPressEvent(event)

class AvatarSelector(QDialog):
    chosen = Signal(str)
    def __init__(self, current, parent=None):
        super().__init__(parent)
        self.original = self.applied = current
        self.setWindowTitle('Apparence de Jarvis')
        self.resize(700, 680)
        self.setStyleSheet('QDialog, QListWidget { background: #0d1c2b; color: #e4f4ff; } QListWidget::item:selected { background: #29485f; border: 1px solid #83cfff; }')
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Cliquez pour essayer une apparence, puis validez · le même assistant, la même session'))
        self.grid = AppearanceGrid()
        self.grid.setAccessibleName('Les 16 apparences de Jarvis')
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.grid.setIconSize(QSize(112, 112))
        self.grid.setGridSize(QSize(150, 140))
        for appearance in CATALOG:
            item = QListWidgetItem(QIcon(QPixmap.fromImage(pose_image(appearance.id))), appearance.name)
            item.setData(Qt.ItemDataRole.UserRole, appearance.id)
            item.setToolTip(PROFILES[appearance.id].description)
            self.grid.addItem(item)
            if appearance.id == current:
                self.grid.setCurrentItem(item)
        self.grid.itemClicked.connect(self.preview)
        self.grid.previewed.connect(self.preview)
        self.grid.itemActivated.connect(self.validate)  # double-click or Return
        layout.addWidget(self.grid)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Valider')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Annuler')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.grid.setFocus()
    def preview(self, item):
        self.applied = item.data(Qt.ItemDataRole.UserRole)
        self.chosen.emit(self.applied)
    def validate(self, item):
        self.preview(item)
        self.accept()
    def reject(self):
        # Escape, Annuler and the window's close button all land here.
        if self.applied != self.original:
            self.applied = self.original
            self.chosen.emit(self.original)
        super().reject()
