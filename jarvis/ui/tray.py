"""Icono en la bandeja del sistema (junto al reloj de Windows).

Un asistente que hay que volver a abrir cada vez estorba más que ayuda. Con
esto se queda ahí discretamente: al cerrar la ventana se esconde en la
bandeja en lugar de terminar, y se recupera con un clic o desde su menú.

El icono se dibuja aquí mismo con QPainter, así que el proyecto no necesita
ningún archivo de imagen.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .theme import theme


def build_icon(color: str | None = None, size: int = 64) -> QIcon:
    """Dibuja un reactor arc en miniatura para usarlo como icono."""
    color = color or theme.accent
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    centro = QPointF(size / 2, size / 2)
    radio = size / 2 - 3
    base = QColor(color)

    # Halo
    halo = QRadialGradient(centro, radio)
    interior = QColor(base)
    interior.setAlpha(150)
    halo.setColorAt(0.0, interior)
    halo.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(halo)
    painter.drawEllipse(centro, radio, radio)

    # Anillo exterior
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(base, max(2.0, size / 22)))
    painter.drawEllipse(centro, radio * 0.82, radio * 0.82)

    # Hexágono interior
    painter.setPen(QPen(base, max(1.5, size / 32)))
    puntos = [
        QPointF(centro.x() + radio * 0.42 * math.cos(math.radians(i * 60)),
                centro.y() + radio * 0.42 * math.sin(math.radians(i * 60)))
        for i in range(6)
    ]
    for i in range(6):
        painter.drawLine(puntos[i], puntos[(i + 1) % 6])

    # Núcleo
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 235))
    painter.drawEllipse(centro, radio * 0.18, radio * 0.18)
    painter.end()

    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    """Icono de bandeja con su menú."""

    def __init__(self, ventana) -> None:
        super().__init__(build_icon(), ventana)
        self.ventana = ventana
        self.setToolTip("J.A.R.V.I.S. — en espera")

        menu = QMenu()

        self.accion_mostrar = QAction("Mostrar el panel", menu)
        self.accion_mostrar.triggered.connect(self.mostrar_ventana)
        menu.addAction(self.accion_mostrar)

        self.accion_escuchar = QAction("Escuchar una orden", menu)
        self.accion_escuchar.triggered.connect(ventana.start_listening)
        menu.addAction(self.accion_escuchar)

        self.accion_manos_libres = QAction("Manos libres", menu)
        self.accion_manos_libres.setCheckable(True)
        self.accion_manos_libres.triggered.connect(self._conmutar_manos_libres)
        menu.addAction(self.accion_manos_libres)

        menu.addSeparator()

        accion_ajustes = QAction("Ajustes…", menu)
        accion_ajustes.triggered.connect(ventana.open_settings)
        menu.addAction(accion_ajustes)

        menu.addSeparator()

        accion_salir = QAction("Salir", menu)
        accion_salir.triggered.connect(ventana.quit_completely)
        menu.addAction(accion_salir)

        self.setContextMenu(menu)
        self.activated.connect(self._al_pulsar)

    # ------------------------------------------------------------------

    def _al_pulsar(self, motivo) -> None:
        """Un clic normal muestra u oculta el panel."""
        if motivo in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.ventana.isVisible() and not self.ventana.isMinimized():
                self.ventana.hide()
            else:
                self.mostrar_ventana()

    def mostrar_ventana(self) -> None:
        self.ventana.showNormal()
        self.ventana.raise_()
        self.ventana.activateWindow()

    def _conmutar_manos_libres(self, activado: bool) -> None:
        self.ventana.wake_button.setChecked(activado)
        self.ventana._toggle_wake_word()

    def actualizar_estado(self, estado: str) -> None:
        textos = {
            "idle": "en espera",
            "listening": "escuchando…",
            "thinking": "procesando…",
            "speaking": "respondiendo…",
            "error": "con un problema",
        }
        self.setToolTip(f"J.A.R.V.I.S. — {textos.get(estado, estado)}")
