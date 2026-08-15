"""Onda de audio animada bajo el reactor.

No analiza el microfono de verdad: es un indicador visual que se agita
cuando el asistente escucha o habla, y queda casi plano en reposo.
"""

from __future__ import annotations

import math
import random

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget

from ...config import config
from ..theme import theme


class Waveform(QWidget):
    BARS = 38

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(34)
        self._levels = [0.06] * self.BARS
        self._targets = [0.06] * self.BARS
        self._phase = 0.0
        self._active = False
        self._color = QColor(theme.accent)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        if config.get("ui.animations", True):
            self._timer.start(45)

    # -- API ------------------------------------------------------------

    def set_active(self, active: bool, color: str | None = None) -> None:
        self._active = active
        if color:
            self._color = QColor(color)

    # -- animacion --------------------------------------------------------

    def _tick(self) -> None:
        self._phase += 0.30
        for i in range(self.BARS):
            if self._active:
                envelope = math.sin(math.pi * i / (self.BARS - 1))  # mas alto en el centro
                wave = 0.5 + 0.5 * math.sin(self._phase + i * 0.42)
                self._targets[i] = 0.15 + envelope * wave * random.uniform(0.55, 1.0)
            else:
                self._targets[i] = 0.05 + 0.04 * (0.5 + 0.5 * math.sin(self._phase * 0.3 + i * 0.5))
            self._levels[i] += (self._targets[i] - self._levels[i]) * 0.35
        self.update()

    def paintEvent(self, event) -> None:            # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        mid = h / 2
        slot = w / self.BARS
        bar_w = max(2.0, slot * 0.52)

        p.setPen(Qt.PenStyle.NoPen)
        for i, level in enumerate(self._levels):
            bar_h = max(2.0, level * (h - 6))
            x = i * slot + (slot - bar_w) / 2
            color = QColor(self._color)
            color.setAlpha(int(90 + 150 * min(1.0, level * 1.6)))
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, mid - bar_h / 2, bar_w, bar_h), 1.5, 1.5)
        p.end()
