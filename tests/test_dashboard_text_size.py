"""« Taille des textes » also enlarges the dashboards (idea 47)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from jarvis.desktop import charts
from jarvis.desktop.dashboard import make_jarvis_dashboard


def sizes(widget):
    return [w.styleSheet() for w in (widget, *widget.findChildren(QLabel)) if "font-size" in w.styleSheet()]


def test_scaled_style_and_bounds():
    assert charts.scaled_style("font-size: 13px; color: red", 4) == "font-size: 17px; color: red"
    charts.set_text_delta(40)
    assert charts.TEXT_SCALE["delta"] == 12
    charts.set_text_delta(0)


def test_dashboard_pages_follow_the_text_size_and_can_go_back():
    QApplication.instance() or QApplication([])
    page = charts.TextScaledWindow()
    try:
        charts.set_text_delta(4)
        page.setCentralWidget(make_jarvis_dashboard([], [], {}))
        assert any("font-size: 23px" in style for style in sizes(page.centralWidget()))  # title 19px + 4
        charts.set_text_delta(0)
        widget = charts.apply_text_scale(page.centralWidget())
        assert any("font-size: 19px" in style for style in sizes(widget))
    finally:
        charts.set_text_delta(0)
        page.close()
