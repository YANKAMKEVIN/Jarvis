"""« Refaire » on a finished mission or a procedure of the history (idea 37)."""
import os
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from jarvis.desktop.history_dialog import HistoryDialog


class Store:
    def recent_missions(self, limit):
        return [NS(goal="Range le bureau", status="completed", step_count=3),
                NS(goal="Envoie le rapport", status="failed", step_count=2)]

    def list(self, kind=None, limit=100):
        return [NS(subject="revue-hebdo", content="Etapes")]


def dialog():
    QApplication.instance() or QApplication([])
    submitted = []
    experience = NS(c=NS(mission_list=lambda: [], cards={}, voice_worker=None),
                    submit=lambda tool, arguments: submitted.append((tool, arguments)) or True)
    return HistoryDialog(experience, store=Store()), submitted


def select(d, goal):
    for index in range(d.list.count()):
        if d.list.item(index).text().startswith(goal):
            d.list.setCurrentRow(index)
            return
    raise AssertionError(goal)


def test_redo_runs_the_exact_goal_of_a_completed_mission():
    d, submitted = dialog()
    try:
        assert not d.redo_button.isEnabled()
        select(d, "Range le bureau")
        assert d.redo_button.isEnabled()
        d.redo_button.click()
        assert submitted == [("run_task", {"goal": "Range le bureau"})]
        select(d, "Envoie le rapport")
        assert not d.redo_button.isEnabled()
        d.redo()
        assert len(submitted) == 1 and "terminée" in d.status.text()
    finally:
        d.close()


def test_redo_a_procedure_uses_run_procedure():
    d, submitted = dialog()
    try:
        d.filter.setCurrentIndex(d.filter.findData("procedures"))
        select(d, "revue-hebdo")
        d.redo_button.click()
        assert submitted == [("run_procedure", {"name": "revue-hebdo"})]
    finally:
        d.close()
