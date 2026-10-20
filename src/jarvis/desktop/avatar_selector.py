"""Native icon grid: arrows, Tab, Space/Return, Escape; no animated thumbnails."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QAbstractItemView, QDialogButtonBox
from jarvis.desktop.appearances import CATALOG
from jarvis.desktop.avatar_assets import pose_image

class AppearanceGrid(QListWidget):
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and self.currentItem() is not None:
            self.itemActivated.emit(self.currentItem())
            event.accept()
        else:
            super().keyPressEvent(event)

class AvatarSelector(QDialog):
    chosen = Signal(str)
    def __init__(self, current, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Apparence de Jarvis')
        self.resize(700, 600)
        self.setStyleSheet('QDialog, QListWidget { background: #0d1c2b; color: #e4f4ff; } QListWidget::item:selected { background: #29485f; border: 1px solid #83cfff; }')
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Choisissez une apparence · le même assistant, la même session'))
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
            self.grid.addItem(item)
            if appearance.id == current:
                self.grid.setCurrentItem(item)
        self.grid.itemClicked.connect(self.choose)
        self.grid.itemActivated.connect(self.choose)
        layout.addWidget(self.grid)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.close)
        layout.addWidget(close)
        self.grid.setFocus()
    def choose(self, item):
        self.chosen.emit(item.data(Qt.ItemDataRole.UserRole))
