"""Area de conversacion: muestra lo que dices y lo que responde el asistente.

Soporta escritura en streaming: cuando Ollama va generando la respuesta,
las palabras aparecen en pantalla segun llegan, como en las peliculas.
"""

from __future__ import annotations

import html
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextBlockFormat, QTextCursor
from PyQt6.QtWidgets import QTextBrowser, QWidget

from ..theme import theme

ROLE_STYLES = {
    "user":      {"label": "USTED",  "color": theme.user_color},
    "assistant": {"label": "JARVIS", "color": theme.accent},
    "system":    {"label": "SISTEMA", "color": theme.muted},
    "error":     {"label": "ERROR",  "color": theme.danger},
    "command":   {"label": "JARVIS", "color": theme.accent},
}


class ChatView(QTextBrowser):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chat")
        self.setOpenExternalLinks(True)
        self.setReadOnly(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._streaming = False
        self._stream_color = theme.accent

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @staticmethod
    def _escape(text: str) -> str:
        """Texto plano -> HTML, respetando saltos de linea y sangrias."""
        escaped = html.escape(text)
        escaped = escaped.replace("\n", "<br>")
        escaped = escaped.replace("   ", "&nbsp;&nbsp;&nbsp;")
        return escaped

    def _at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 40

    def _scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _header_html(self, role: str) -> str:
        style = ROLE_STYLES.get(role, ROLE_STYLES["system"])
        hora = datetime.now().strftime("%H:%M:%S")
        return (
            f'<span style="color:{style["color"]}; font-weight:bold; letter-spacing:2px;">'
            f'{style["label"]}</span>'
            f'<span style="color:{theme.muted};"> · {hora}</span>'
        )

    def _new_block(self, top_margin: float = 0.0, left_margin: float = 0.0) -> QTextCursor:
        """Empieza un parrafo nuevo al final del documento.

        Hace falta llamar a insertBlock() explicitamente: si se insertara solo
        HTML, Qt lo pegaria al final del parrafo anterior y los mensajes
        saldrian todos seguidos en la misma linea.
        """
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        block_format = QTextBlockFormat()
        block_format.setTopMargin(top_margin)
        block_format.setLeftMargin(left_margin)
        if self.document().isEmpty():
            cursor.setBlockFormat(block_format)
        else:
            cursor.insertBlock(block_format)
        return cursor

    # ------------------------------------------------------------------
    # Mensajes completos
    # ------------------------------------------------------------------

    def add_message(self, role: str, text: str) -> None:
        if not text:
            return
        style = ROLE_STYLES.get(role, ROLE_STYLES["system"])
        stick = self._at_bottom()

        cursor = self._new_block(top_margin=14.0)
        cursor.insertHtml(self._header_html(role))

        cursor = self._new_block(top_margin=2.0, left_margin=12.0)
        cursor.insertHtml(
            f'<span style="color:{style["color"]};">{self._escape(text)}</span>'
        )
        self.setTextCursor(cursor)
        if stick:
            self._scroll_to_bottom()

    def add_separator(self, label: str = "") -> None:
        cursor = self._new_block(top_margin=16.0)
        cursor.insertHtml(
            f'<span style="color:{theme.muted}; letter-spacing:3px;">'
            f'{"─" * 6} {html.escape(label)} {"─" * 30}</span>'
        )
        self._scroll_to_bottom()

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def start_stream(self, role: str = "assistant") -> None:
        style = ROLE_STYLES.get(role, ROLE_STYLES["assistant"])
        self._stream_color = style["color"]
        self._streaming = True

        cursor = self._new_block(top_margin=14.0)
        cursor.insertHtml(self._header_html(role))
        # Bloque vacio donde se ira escribiendo la respuesta token a token.
        cursor = self._new_block(top_margin=2.0, left_margin=12.0)
        self.setTextCursor(cursor)
        self._scroll_to_bottom()

    def append_stream(self, token: str) -> None:
        if not self._streaming or not token:
            return
        stick = self._at_bottom()
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(
            f'<span style="color:{self._stream_color};">{self._escape(token)}</span>'
        )
        if stick:
            self._scroll_to_bottom()

    def end_stream(self) -> None:
        self._streaming = False
        self._scroll_to_bottom()

    @property
    def streaming(self) -> bool:
        return self._streaming

    # ------------------------------------------------------------------

    def clear_chat(self) -> None:
        self.clear()
        self._streaming = False
