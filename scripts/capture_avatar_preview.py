"""Capture real demo widgets, with isolated settings and no voice/model activity.

QT_QPA_PLATFORM=offscreen python scripts/capture_avatar_preview.py
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import QSettings, QTemporaryDir
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from jarvis.desktop.app import Controller, DesktopShell, STYLE
from jarvis.desktop.presentation import project_task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--animation-frames', type=Path, help='Optional PNG frames of the real demo widget')
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / 'docs/screenshots/avatars'
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyleSheet(STYLE)
    temporary = QTemporaryDir()
    settings = QSettings(temporary.path() + '/demo.ini', QSettings.Format.IniFormat)
    controller = Controller(demo=True)
    controller.reduced_motion = True
    shell = DesktopShell(app, controller, settings)
    def save(widget, name):
        app.processEvents()
        QTest.qWait(80)
        if not widget.grab().save(str(output / name)):
            raise RuntimeError(name)
    try:
        shell.show_full()
        save(shell.full, 'nova-bot.png')
        shell.show_appearances()
        save(shell.appearance_dialog, 'selector.png')
        shell.appearance_dialog.hide()
        shell.set_appearance('kitsune')
        save(shell.full, 'kitsune.png')
        shell.set_appearance('nova_bot')
        controller.voice_event({'type': 'missions', 'missions': [project_task({
            'id': str(i), 'objective': objective, 'status': 'running',
            'current_tool': 'web_answer', 'steps': []}) for i, objective in enumerate((
            'Exemple simulé · Comparer deux solutions audio',
            'Exemple simulé · Préparer une synthèse'))]})
        save(shell.full, 'two-missions.png')
        shell.show_compact()
        save(shell.compact, 'compact.png')
        shell.show_orb()
        save(shell.orb_window, 'floating.png')
        shell.set_appearance('aurora_light')
        shell.show_full()
        save(shell.full, 'aura-light.png')
        if args.animation_frames:
            args.animation_frames.mkdir(parents=True, exist_ok=True)
            controller.voice_event({'type': 'missions', 'missions': []})
            shell.set_appearance('nova_bot')
            controller.reduced_motion = False
            for frame in range(60):
                state = ('listening', 'thinking', 'speaking', 'off')[frame // 15]
                if frame % 15 == 0:
                    controller.voice_event({'type': 'state', 'state': state})
                    if frame == 45:
                        controller.voice_event({'type': 'activity', 'id': 'demo-success',
                            'label': 'Exemple simulé', 'status': 'verified'})
                controller.audio_levels.emit(0.03 if state == 'listening' else 0,
                                              0.08 if state == 'speaking' else 0)
                QTest.qWait(67)
                shell.full.grab().save(str(args.animation_frames / f'{frame:03d}.png'))
    finally:
        shell.finish_transfer()
        for widget in (shell.full, shell.compact, shell.orb_window): widget.hide()
        if shell.tray: shell.tray.hide()
    print(output)

if __name__ == '__main__':
    main()
