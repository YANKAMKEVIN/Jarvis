"""QtCharts building blocks: styled axes, views, panels and the daily, ranking and line charts."""
from __future__ import annotations

from PySide6.QtCharts import (
    QAreaSeries,
    QBarCategoryAxis,
    QBarSet,
    QChart,
    QChartView,
    QDateTimeAxis,
    QHorizontalBarSeries,
    QLineSeries,
    QStackedBarSeries,
    QValueAxis,
)
from PySide6.QtCore import QDateTime, QMargins, QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGradient,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsSimpleTextItem,
    QHBoxLayout,
    QLabel,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from typing import Any, Sequence

from jarvis.capabilities.usage import _human
from jarvis.desktop.charts_format import (
    _ACCENTS,
    _ALERT,
    _MUTED,
    _PANEL,
    _PEAK,
    _TEXT,
    _TODAY,
    _unit,
)


def _show_tip(text: str) -> None:
    QToolTip.showText(QCursor.pos(), text)


def _style_chart(chart: QChart) -> None:
    """Bare chart: the panel around it carries the title, the plot uses the
    whole area."""
    chart.setBackgroundVisible(False)
    chart.setPlotAreaBackgroundVisible(False)
    chart.setBackgroundRoundness(0)
    chart.legend().setVisible(False)
    chart.setMargins(QMargins(2, 6, 8, 2))
    chart.layout().setContentsMargins(0, 0, 0, 0)
    chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)


def _small_font(size: int = 11) -> QFont:
    # Pixels, like the panel stylesheets ("font-size: 12px"), so chart text
    # stays in proportion with the labels around it.
    font = QFont()
    font.setPixelSize(size)
    return font


def _style_axes(*axes) -> None:
    for axis in axes:
        axis.setLabelsFont(_small_font(11))
        axis.setLabelsColor(QColor(_MUTED))
        axis.setGridLineColor(QColor(255, 255, 255, 16))
        axis.setLinePenColor(QColor(255, 255, 255, 36))
        axis.setTitleVisible(False)


def _value_axis(top: float) -> QValueAxis:
    axis = QValueAxis()
    axis.setRange(0, top or 1)
    axis.applyNiceNumbers()  # round ticks (0, 500, 1000…) instead of 0, 546, 1092…
    axis.setLabelFormat("%.1f" if axis.max() < 5 else "%.0f")
    return axis


def _view(chart: QChart) -> QChartView:
    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setStyleSheet("background: transparent;")
    view.setMinimumHeight(170)
    return view


def _panel(title: str, body: QWidget, legend: str = "") -> QFrame:
    """Rounded panel with a left-aligned title (and an optional legend on the
    right) above a chart or a list."""
    panel = QFrame()
    panel.setObjectName("chartPanel")
    panel.setStyleSheet(f"#chartPanel {{ background: {_PANEL}; border-radius: 14px; }}")
    box = QVBoxLayout(panel)
    box.setContentsMargins(16, 12, 12, 10)
    box.setSpacing(4)
    head = QHBoxLayout()
    title_label = QLabel(title)
    title_label.setObjectName("panelTitle")
    title_label.setStyleSheet(f"color: {_TEXT}; font-size: 14px; font-weight: 600;")
    head.addWidget(title_label)
    head.addStretch(1)
    if legend:
        legend_label = QLabel(legend)
        legend_label.setObjectName("panelLegend")
        legend_label.setTextFormat(Qt.TextFormat.RichText)
        legend_label.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        head.addWidget(legend_label)
    box.addLayout(head)
    box.addWidget(body, 1)
    return panel


def _swatch(color: str, text: str) -> str:
    return f"<span style='color:{color}; font-size:15px'>●</span> {text}"


def _daily_chart(labels: Sequence[str], values: Sequence[float], tips: Sequence[str],
                 today: int | None, peak: int | None) -> QChartView:
    """Vertical token bars in an automatic unit. Today and the peak get their
    own colour through a stacked series (Qt colours per set, not per bar)."""
    divisor, _ = _unit(values)
    scaled = [v / divisor for v in values]
    layers = (
        (_ACCENTS[0], [v if i not in (today, peak) else 0 for i, v in enumerate(scaled)]),
        (_PEAK, [v if i == peak and i != today else 0 for i, v in enumerate(scaled)]),
        (_TODAY, [v if i == today else 0 for i, v in enumerate(scaled)]),
    )
    series = QStackedBarSeries()
    series.setBarWidth(0.78)
    for color, layer in layers:
        bar_set = QBarSet("")
        bar_set.append(layer)
        bar_set.setColor(QColor(color))
        bar_set.setBorderColor(QColor(color))
        bar_set.hovered.connect(
            lambda on, index: _show_tip(tips[index]) if on else QToolTip.hideText())
        series.append(bar_set)

    chart = QChart()
    chart.addSeries(series)
    _style_chart(chart)
    cat_axis = QBarCategoryAxis()
    cat_axis.append(list(labels))
    cat_axis.setTruncateLabels(False)  # Qt elides short labels like "16" to "…" otherwise
    cat_axis.setGridLineVisible(False)
    val_axis = _value_axis(max(scaled, default=0) * 1.1)
    chart.addAxis(cat_axis, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(val_axis, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(cat_axis)
    series.attachAxis(val_axis)
    _style_axes(cat_axis, val_axis)
    return _view(chart)


def _ranking_chart(names: Sequence[str], values: Sequence[float], color: str,
                   tips: Sequence[str]) -> QChartView:
    """Horizontal bars, largest on top, each with its value written at its
    end; no value axis, the numbers say it."""
    names, values, tips = list(names)[::-1], list(values)[::-1], list(tips)[::-1]
    divisor, _ = _unit(values)
    scaled = [v / divisor for v in values]
    bar_set = QBarSet("")
    bar_set.append(scaled)
    bar_set.setColor(QColor(color))
    bar_set.setBorderColor(QColor(color))
    bar_set.hovered.connect(
        lambda on, index: _show_tip(tips[index]) if on else QToolTip.hideText())
    series = QHorizontalBarSeries()
    series.append(bar_set)
    series.setBarWidth(0.62)

    chart = QChart()
    chart.addSeries(series)
    _style_chart(chart)
    chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)  # labels sit at the final length
    cat_axis = QBarCategoryAxis()
    cat_axis.append(names)
    cat_axis.setTruncateLabels(False)
    cat_axis.setGridLineVisible(False)
    cat_axis.setLineVisible(False)
    val_axis = QValueAxis()
    val_axis.setRange(0, (max(scaled, default=0) or 1) * 1.3)  # room for the end labels
    val_axis.setVisible(False)
    chart.addAxis(cat_axis, Qt.AlignmentFlag.AlignLeft)
    chart.addAxis(val_axis, Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(cat_axis)
    series.attachAxis(val_axis)
    _style_axes(cat_axis)
    cat_axis.setLabelsColor(QColor(_TEXT))
    cat_axis.setLabelsFont(_small_font(13))

    texts = [_human(v) for v in values]
    items = []
    for text in texts:
        item = QGraphicsSimpleTextItem(text, chart)
        item.setBrush(QColor(_MUTED))
        item.setFont(_small_font(12))
        items.append(item)

    def place() -> None:
        for index, (value, item) in enumerate(zip(scaled, items)):
            point = chart.mapToPosition(QPointF(value, index), series)
            item.setPos(point.x() + 6, point.y() - item.boundingRect().height() / 2)

    chart.plotAreaChanged.connect(lambda _area: place())
    place()
    return _view(chart)


def _line_chart(series: Sequence[dict[str, Any]], color: str, period: str = "24h",
                threshold: float | None = None) -> QChartView:
    """Percentage over time as a filled curve, with real clock labels and,
    when given, the alert threshold as a dashed line."""
    upper = QLineSeries()
    points = [(float(p["ts"]) * 1000, float(p["value"])) for p in series]
    for x, y in points:
        upper.append(x, y)
    area = QAreaSeries(upper)
    upper.setParent(area)  # the area does not own its boundary series
    pen = QPen(QColor(color))
    pen.setWidth(2)
    area.setPen(pen)
    gradient = QLinearGradient(0, 0, 0, 1)
    gradient.setCoordinateMode(QGradient.CoordinateMode.ObjectBoundingMode)
    top, bottom = QColor(color), QColor(color)
    top.setAlpha(110)
    bottom.setAlpha(0)
    gradient.setColorAt(0, top)
    gradient.setColorAt(1, bottom)
    area.setBrush(gradient)
    clock = "dd/MM HH:mm" if period == "7d" else "HH:mm"

    def hover(point: QPointF, on: bool) -> None:
        if not on:
            QToolTip.hideText()
            return
        x, y = min(points, key=lambda p: abs(p[0] - point.x()))
        when = QDateTime.fromMSecsSinceEpoch(int(x)).toString(clock)
        _show_tip(f"{when} · {y:.0f} %")

    area.hovered.connect(hover)

    chart = QChart()
    chart.addSeries(area)
    _style_chart(chart)

    first, last = points[0][0], points[-1][0]
    if last <= first:
        last = first + 60_000
    axis_x = QDateTimeAxis()
    axis_x.setFormat("dd/MM" if period == "7d" else "HH:mm")
    axis_x.setTickCount(6)
    axis_x.setRange(QDateTime.fromMSecsSinceEpoch(int(first)),
                    QDateTime.fromMSecsSinceEpoch(int(last)))
    axis_x.setGridLineVisible(False)
    axis_y = QValueAxis()
    axis_y.setRange(0, 100)
    axis_y.setTickCount(5)
    axis_y.setLabelFormat("%.0f")
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    area.attachAxis(axis_x)
    area.attachAxis(axis_y)

    if threshold is not None:
        limit = QLineSeries()
        limit.append(first, threshold)
        limit.append(last, threshold)
        dash = QPen(QColor(_ALERT))
        dash.setWidth(1)
        dash.setStyle(Qt.PenStyle.DashLine)
        chart.addSeries(limit)
        limit.setPen(dash)  # after addSeries, or the chart theme repaints it
        limit.attachAxis(axis_x)
        limit.attachAxis(axis_y)

    _style_axes(axis_x, axis_y)
    return _view(chart)
