"""Capture the real avatar widgets together; simulated audio, no microphone.

QT_QPA_PLATFORM=offscreen python scripts/capture_avatar_motion.py --frames /tmp/avatar-motion
"""
import argparse
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QGridLayout, QLabel
from jarvis.desktop.app import STYLE
from jarvis.desktop.appearances import CATALOG
from jarvis.desktop.visuals import Orb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=Path, required=True)
    args = parser.parse_args()
    args.frames.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyleSheet(STYLE)
    window = QWidget()
    window.setStyleSheet('background: #0d1c2b; color: #e4f4ff;')
    window.setWindowTitle('Jarvis · Animations des 16 apparences')
    layout = QVBoxLayout(window)
    title = QLabel('DÉMO DU RENDU QT · 16 chorégraphies · audio simulé · micro fermé')
    layout.addWidget(title)
    grid = QGridLayout()
    layout.addLayout(grid)
    orbs = []
    for i, appearance in enumerate(CATALOG):
        cell = QWidget()
        box = QVBoxLayout(cell)
        orb = Orb(180)
        orb.set_appearance(appearance.id)
        box.addWidget(orb, 0, Qt.AlignmentFlag.AlignCenter)
        label = QLabel(appearance.name)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(label)
        grid.addWidget(cell, i//4, i%4)
        orbs.append(orb)
    window.show()
    try:
        for frame in range(60):
            state = ('listening', 'thinking', 'speaking')[frame//20]
            title.setText(f'DÉMO DU RENDU QT · {state} · audio simulé · micro fermé')
            for orb in orbs:
                orb.state = state
                orb.set_levels(.025 if state == 'listening' else 0,
                               .025*(1+math.sin(frame*.7)) if state == 'speaking' else 0)
            QTest.qWait(100)
            if not window.grab().save(str(args.frames / f'{frame:03d}.png')):
                raise RuntimeError('Could not save capture')
    finally:
        window.hide()
    print(args.frames)

if __name__ == '__main__':
    main()
