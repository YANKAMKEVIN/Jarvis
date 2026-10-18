"""Capture the real Qt UI, with optional explicitly labelled sample results.

No microphone, network, native tools or user preferences are used.
QT_QPA_PLATFORM=offscreen python scripts/capture_desktop_preview.py --samples
"""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/screenshots')
    parser.add_argument('--samples', action='store_true', help='Include labelled simulated cards and task progress')
    args = parser.parse_args()
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QLabel
    from jarvis.desktop.app import Controller, DesktopShell, STYLE
    from jarvis.desktop.presentation import project_activity

    class Settings:
        def value(self, key, default=None): return default
        def setValue(self, key, value): pass

    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyleSheet(STYLE)
    controller = Controller(demo=True)
    controller.reduced_motion = True
    shell = DesktopShell(app, controller, settings=Settings())

    def save(window, name):
        app.processEvents()
        if not window.grab().save(str(args.output / name)):
            raise RuntimeError('Cannot write screenshot: ' + name)

    try:
        shell.show_full()
        save(shell.full, 'desktop-home.png')
        shell.show_compact()
        save(shell.compact, 'compact-idle.png')
        shell.show_orb()
        app.processEvents()
        # A plain canvas makes the captured widget's transparency readable in image viewers.
        canvas = QPixmap(240, 272)
        canvas.fill(QColor('#0b111b'))
        painter = QPainter(canvas)
        painter.drawPixmap(26, 14, shell.orb_window.grab())
        painter.end()
        if not canvas.save(str(args.output / 'orb-only.png')):
            raise RuntimeError('Cannot write orb screenshot')
        shell.show_full()
        shell.full.navigate(3)
        app.processEvents()
        settings = shell.full.pages.widget(3)
        settings.verticalScrollBar().setValue(settings.verticalScrollBar().maximum())
        save(shell.full, 'audio-settings.png')
        if args.samples:
            controller.voice_event(project_activity('list_calendar_events', {'ok': True, 'events': [
                {'title': 'Exemple · Point équipe', 'start': '2026-10-18T10:00'},
                {'title': 'Exemple · Préparer la semaine', 'start': '2026-10-18T15:00'}]}, 'sample-calendar'))
            controller.voice_event(project_activity('web_answer', {'ok': True,
                'external_knowledge_retrieved': True,
                'message': 'Exemple de résultat structuré. Aucune recherche réelle n’a été effectuée pour cette démonstration.',
                'sources': [{'title': 'Exemple de source', 'url': 'https://example.com/'}]}, 'sample-web'))
            shell.show_details()
            header = next(w for w in shell.full.findChildren(QLabel)
                          if w.text() == 'COMPAGNON VOCAL     /     JARVIS')
            header.setText('DÉMONSTRATION · RÉSULTATS SIMULÉS')
            save(shell.full, 'context-cards.png')
            controller.voice_event({'type': 'task_progress', 'id': 'sample-task',
                'status': 'running', 'step_count': 2, 'steps': [
                    {'label': 'Fichiers', 'status': 'received'},
                    {'label': 'Recherche web', 'status': 'verified'}]})
            shell.full.navigate(2)
            save(shell.full, 'task-progress.png')
    finally:
        shell.finish_transfer()
        for window in (shell.full, shell.compact, shell.orb_window):
            window.hide()
        if shell.tray:
            shell.tray.hide()
    print('Qt captures saved to', args.output)


if __name__ == '__main__':
    main()
