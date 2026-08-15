"""Reactor Arc: el circulo animado del centro del panel.

Se dibuja entero con QPainter (no hace falta ninguna imagen). Cambia de
color y de velocidad segun lo que este haciendo el asistente:

    idle       -> cian, giro lento
    listening  -> verde, giro rapido y nucleo palpitante
    thinking   -> ambar, anillos acelerados
    speaking   -> cian brillante, pulso al ritmo de la voz
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from ...config import config
from ..theme import theme

STATE_COLORS = {
    "idle": theme.accent,
    "listening": "#7CFFCB",
    "thinking": theme.warn,
    "speaking": "#5CE1FF",
    "error": theme.danger,
}

STATE_SPEED = {
    "idle": 1.0,
    "listening": 2.4,
    "thinking": 3.6,
    "speaking": 2.0,
    "error": 0.6,
}


class ArcReactor(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Minimo pequeño y tamaño preferido grande: el reactor es lo unico
        # de la columna que puede encogerse sin perder informacion, asi que
        # en una pantalla baja cede su sitio a los textos en vez de
        # recortarlos.
        self.setMinimumSize(110, 110)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._angle = 0.0
        self._pulse = 0.0
        self._state = "idle"
        self._level = 0.0          # 0..1, intensidad del nucleo

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        if config.get("ui.animations", True):
            self._timer.start(33)  # ~30 fps

    # -- API ------------------------------------------------------------

    def set_state(self, state: str) -> None:
        if state in STATE_COLORS and state != self._state:
            self._state = state
            self.update()

    def state(self) -> str:
        return self._state

    def set_level(self, level: float) -> None:
        """Intensidad extra del nucleo (0..1), util al hablar o escuchar."""
        self._level = max(0.0, min(1.0, level))

    def sizeHint(self) -> QSize:                    # noqa: N802 (nombre de Qt)
        """Tamaño al que aspira cuando hay sitio de sobra."""
        return QSize(210, 210)

    # -- animacion -------------------------------------------------------

    def _tick(self) -> None:
        speed = STATE_SPEED.get(self._state, 1.0)
        self._angle = (self._angle + 1.1 * speed) % 360.0
        self._pulse = (self._pulse + 0.06 * speed) % (2 * math.pi)
        self.update()

    # -- dibujo ----------------------------------------------------------

    def paintEvent(self, event) -> None:            # noqa: N802 (nombre de Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        side = min(self.width(), self.height())
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = side / 2 - 6
        base = QColor(STATE_COLORS.get(self._state, theme.accent))
        breath = 0.5 + 0.5 * math.sin(self._pulse)

        self._draw_glow(painter, center, radius, base, breath)
        self._draw_outer_ticks(painter, center, radius, base)
        self._draw_rotating_arcs(painter, center, radius, base)
        self._draw_inner_frame(painter, center, radius, base, breath)
        self._draw_core(painter, center, radius, base, breath)
        painter.end()

    # cada parte por separado para que se lea facil ------------------------

    def _draw_glow(self, p: QPainter, c: QPointF, r: float, color: QColor, breath: float) -> None:
        halo = QRadialGradient(c, r)
        alpha = int(38 + 34 * breath + 40 * self._level)
        inner = QColor(color)
        inner.setAlpha(alpha)
        mid = QColor(color)
        mid.setAlpha(int(alpha * 0.35))
        halo.setColorAt(0.0, inner)
        halo.setColorAt(0.55, mid)
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(c, r, r)

    def _draw_outer_ticks(self, p: QPainter, c: QPointF, r: float, color: QColor) -> None:
        pen = QPen(QColor(color.red(), color.green(), color.blue(), 150), 1.4)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(60):
            angle = math.radians(i * 6 - self._angle * 0.25)
            long_tick = (i % 5 == 0)
            r1 = r * (0.90 if long_tick else 0.94)
            r2 = r * 0.99
            p.drawLine(
                QPointF(c.x() + r1 * math.cos(angle), c.y() + r1 * math.sin(angle)),
                QPointF(c.x() + r2 * math.cos(angle), c.y() + r2 * math.sin(angle)),
            )

    def _draw_rotating_arcs(self, p: QPainter, c: QPointF, r: float, color: QColor) -> None:
        # Anillo exterior: cuatro arcos girando en un sentido.
        rect = QRectF(c.x() - r * 0.86, c.y() - r * 0.86, r * 1.72, r * 1.72)
        p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 220), 2.4,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i in range(4):
            start = int((self._angle + i * 90) * 16)
            p.drawArc(rect, start, 58 * 16)

        # Anillo medio: dos arcos largos girando al reves.
        rect2 = QRectF(c.x() - r * 0.68, c.y() - r * 0.68, r * 1.36, r * 1.36)
        p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 130), 1.6))
        for i in range(2):
            start = int((-self._angle * 1.6 + i * 180) * 16)
            p.drawArc(rect2, start, 120 * 16)

        # Anillo fino intermitente.
        rect3 = QRectF(c.x() - r * 0.55, c.y() - r * 0.55, r * 1.10, r * 1.10)
        pen = QPen(QColor(color.red(), color.green(), color.blue(), 90), 1.0)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawEllipse(rect3)

    def _draw_inner_frame(self, p: QPainter, c: QPointF, r: float,
                          color: QColor, breath: float) -> None:
        """Hexagono girando dentro del reactor."""
        p.setPen(QPen(QColor(color.red(), color.green(), color.blue(),
                             int(110 + 60 * breath)), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        hex_r = r * 0.40
        for i in range(6):
            angle = math.radians(i * 60 + self._angle * 0.8)
            point = QPointF(c.x() + hex_r * math.cos(angle), c.y() + hex_r * math.sin(angle))
            if i == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()
        p.drawPath(path)

    def _draw_core(self, p: QPainter, c: QPointF, r: float,
                   color: QColor, breath: float) -> None:
        core_r = r * (0.20 + 0.05 * breath + 0.06 * self._level)
        gradient = QRadialGradient(c, core_r * 2.2)
        bright = QColor(255, 255, 255, int(200 + 40 * breath))
        gradient.setColorAt(0.0, bright)
        mid = QColor(color)
        mid.setAlpha(200)
        gradient.setColorAt(0.35, mid)
        edge = QColor(color)
        edge.setAlpha(0)
        gradient.setColorAt(1.0, edge)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gradient)
        p.drawEllipse(c, core_r * 2.2, core_r * 2.2)

        p.setBrush(QColor(255, 255, 255, 235))
        p.drawEllipse(c, core_r * 0.5, core_r * 0.5)
