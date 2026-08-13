"""Paleta de colores y hoja de estilos (QSS) del panel holografico."""

from __future__ import annotations

from PyQt6.QtGui import QColor

from ..config import config


class Theme:
    """Colores del tema. Se leen de la configuracion, con valores por defecto."""

    def __init__(self) -> None:
        ui = config.get("ui") or {}
        self.accent = ui.get("accent", "#00E5FF")
        self.accent_dim = ui.get("accent_dim", "#0097B2")
        self.warn = ui.get("warn", "#FFB000")
        self.danger = ui.get("danger", "#FF3B3B")
        self.background = ui.get("background", "#05080D")
        self.panel = ui.get("panel", "#0A121A")
        self.text = ui.get("text", "#CFEFF7")
        self.font_family = ui.get("font_family", "Consolas")
        self.font_size = int(ui.get("font_size", 11))

        self.muted = "#4E7A8A"
        self.user_color = "#7CFFCB"
        self.grid = "#0E2430"

    # -- helpers ---------------------------------------------------------

    def qcolor(self, hex_color: str, alpha: int = 255) -> QColor:
        color = QColor(hex_color)
        color.setAlpha(alpha)
        return color

    @property
    def accent_qc(self) -> QColor:
        return QColor(self.accent)

    def rgba(self, hex_color: str, alpha: float) -> str:
        c = QColor(hex_color)
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"

    # -- hoja de estilos --------------------------------------------------

    def stylesheet(self) -> str:
        a, ad, bg, panel, text = self.accent, self.accent_dim, self.background, self.panel, self.text
        return f"""
        QWidget {{
            background: transparent;
            color: {text};
            font-family: "{self.font_family}", "Cascadia Mono", monospace;
            font-size: {self.font_size}pt;
        }}

        #root {{
            background-color: {bg};
        }}

        /* ---------- Paneles ---------- */
        QFrame#panel {{
            background-color: {self.rgba(panel, 0.72)};
            border: 1px solid {self.rgba(a, 0.28)};
            border-radius: 4px;
        }}

        QLabel#panelTitle {{
            color: {a};
            font-size: {self.font_size - 1}pt;
            font-weight: bold;
            letter-spacing: 3px;
            padding: 2px 0 6px 0;
            border-bottom: 1px solid {self.rgba(a, 0.25)};
        }}

        QLabel#hint {{
            color: {self.muted};
            font-size: {self.font_size - 2}pt;
            letter-spacing: 1px;
        }}

        QLabel#statusLabel {{
            color: {a};
            font-size: {self.font_size - 1}pt;
            letter-spacing: 2px;
        }}

        QLabel#titleText {{
            color: {a};
            font-size: {self.font_size + 7}pt;
            font-weight: bold;
            letter-spacing: 10px;
        }}

        QLabel#subtitleText {{
            color: {self.muted};
            font-size: {self.font_size - 2}pt;
            letter-spacing: 4px;
        }}

        /* ---------- Chat ---------- */
        QTextBrowser#chat {{
            background-color: {self.rgba(panel, 0.55)};
            border: 1px solid {self.rgba(a, 0.22)};
            border-radius: 3px;
            padding: 10px 14px;
            selection-background-color: {self.rgba(a, 0.35)};
        }}

        /* ---------- Entrada de texto ---------- */
        QLineEdit#input {{
            background-color: {self.rgba(panel, 0.85)};
            border: 1px solid {self.rgba(a, 0.35)};
            border-radius: 3px;
            padding: 10px 14px;
            color: {text};
            selection-background-color: {self.rgba(a, 0.35)};
        }}
        QLineEdit#input:focus {{
            border: 1px solid {a};
            background-color: {self.rgba(panel, 0.95)};
        }}

        /* ---------- Botones ---------- */
        QPushButton {{
            background-color: {self.rgba(a, 0.08)};
            border: 1px solid {self.rgba(a, 0.45)};
            border-radius: 3px;
            padding: 9px 16px;
            color: {a};
            letter-spacing: 2px;
        }}
        QPushButton:hover {{
            background-color: {self.rgba(a, 0.20)};
            border: 1px solid {a};
        }}
        QPushButton:pressed {{
            background-color: {self.rgba(a, 0.34)};
        }}
        QPushButton:disabled {{
            color: {self.muted};
            border: 1px solid {self.rgba(a, 0.15)};
            background-color: transparent;
        }}
        QPushButton:checked {{
            background-color: {self.rgba(a, 0.28)};
            border: 1px solid {a};
            color: #FFFFFF;
        }}

        QPushButton#danger {{
            color: {self.danger};
            border: 1px solid {self.rgba(self.danger, 0.5)};
        }}
        QPushButton#danger:hover {{
            background-color: {self.rgba(self.danger, 0.18)};
            border: 1px solid {self.danger};
        }}

        QPushButton#titleBarButton, QPushButton#closeButton {{
            border: none;
            background: transparent;
            padding: 4px 10px;
            font-size: {self.font_size + 1}pt;
            color: {ad};
        }}
        QPushButton#titleBarButton:hover {{
            color: {a};
            background-color: {self.rgba(a, 0.12)};
        }}
        QPushButton#closeButton {{
            color: {ad};
        }}
        QPushButton#closeButton:hover {{
            color: #FFFFFF;
            background-color: {self.rgba(self.danger, 0.65)};
        }}

        /* ---------- Barras de progreso ---------- */
        QProgressBar {{
            background-color: {self.rgba(a, 0.08)};
            border: 1px solid {self.rgba(a, 0.30)};
            border-radius: 2px;
            height: 10px;
            text-align: center;
            color: transparent;
        }}
        QProgressBar::chunk {{
            background-color: {self.rgba(a, 0.75)};
            border-radius: 1px;
        }}

        /* ---------- Barra de desplazamiento ---------- */
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {self.rgba(a, 0.35)};
            border-radius: 4px;
            min-height: 28px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {self.rgba(a, 0.65)};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}

        QToolTip {{
            background-color: {panel};
            color: {text};
            border: 1px solid {a};
            padding: 4px;
        }}
        """


theme = Theme()
