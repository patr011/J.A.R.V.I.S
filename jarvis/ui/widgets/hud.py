"""Fondo tipo HUD (rejilla, linea de barrido, esquinas) y barras de estado."""

from __future__ import annotations

import math

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ...config import config
from ..theme import theme


class HudBackground(QWidget):
    """Rejilla + linea de barrido que se dibuja detras de todo lo demas."""

    GRID = 34  # separacion de la rejilla en pixeles

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._scan = 0.0
        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        if config.get("ui.animations", True):
            self._timer.start(50)  # 20 fps: es fondo, no necesita mas

    def _tick(self) -> None:
        self._scan = (self._scan + 0.0045) % 1.0
        self._phase = (self._phase + 0.02) % (2 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:            # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()

        p.fillRect(self.rect(), QColor(theme.background))

        # --- rejilla ---
        grid_color = QColor(theme.grid)
        grid_color.setAlpha(120)
        p.setPen(QPen(grid_color, 1))
        for x in range(0, w, self.GRID):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, self.GRID):
            p.drawLine(0, y, w, y)

        # --- linea de barrido horizontal ---
        accent = QColor(theme.accent)
        y_scan = int(self._scan * h)
        accent.setAlpha(26)
        p.setPen(QPen(accent, 2))
        p.drawLine(0, y_scan, w, y_scan)
        accent.setAlpha(10)
        p.setPen(QPen(accent, 14))
        p.drawLine(0, y_scan, w, y_scan)

        # --- esquinas ---
        self._draw_corners(p, w, h)
        p.end()

    def _draw_corners(self, p: QPainter, w: int, h: int) -> None:
        color = QColor(theme.accent)
        color.setAlpha(int(90 + 40 * (0.5 + 0.5 * math.sin(self._phase))))
        p.setPen(QPen(color, 2))
        size, margin = 26, 10
        for cx, cy, dx, dy in (
            (margin, margin, 1, 1),
            (w - margin, margin, -1, 1),
            (margin, h - margin, 1, -1),
            (w - margin, h - margin, -1, -1),
        ):
            p.drawLine(cx, cy, cx + size * dx, cy)
            p.drawLine(cx, cy, cx, cy + size * dy)


class StatBar(QWidget):
    """Barra horizontal etiquetada (CPU, RAM, volumen, brillo...)."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = label
        self._value = 0.0
        self._target = 0.0
        self._suffix = "%"
        self._enabled_text = ""
        self.setFixedHeight(30)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(40)

    def set_value(self, value: float, suffix: str = "%", text: str = "") -> None:
        self._target = max(0.0, min(100.0, float(value)))
        self._suffix = suffix
        self._enabled_text = text

    def _animate(self) -> None:
        if abs(self._value - self._target) < 0.4:
            self._value = self._target
            return
        self._value += (self._target - self._value) * 0.20
        self.update()

    def paintEvent(self, event) -> None:            # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()

        font = QFont(theme.font_family, max(7, theme.font_size - 3))
        p.setFont(font)

        # etiqueta y valor
        p.setPen(QColor(theme.muted))
        p.drawText(QRectF(0, 0, w * 0.5, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.label)
        p.setPen(QColor(theme.accent))
        texto = self._enabled_text or f"{self._value:.0f}{self._suffix}"
        p.drawText(QRectF(w * 0.5, 0, w * 0.5, 14),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, texto)

        # riel
        bar_y, bar_h = 19.0, 6.0
        rail = QColor(theme.accent)
        rail.setAlpha(38)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(rail)
        p.drawRoundedRect(QRectF(0, bar_y, w, bar_h), 2, 2)

        # relleno segmentado (aspecto tecnologico)
        filled = w * self._value / 100.0
        color = QColor(theme.accent)
        if self._value >= 85:
            color = QColor(theme.danger)
        elif self._value >= 65:
            color = QColor(theme.warn)
        color.setAlpha(215)
        p.setBrush(color)

        seg_w, gap = 6.0, 2.0
        x = 0.0
        while x < filled:
            width = min(seg_w, filled - x)
            p.drawRoundedRect(QRectF(x, bar_y, width, bar_h), 1, 1)
            x += seg_w + gap
        p.end()
