"""Panel de ajustes.

Todo lo que antes había que cambiar editando ~/.jarvis/config.json con el
Bloc de notas se puede tocar desde aquí: el modelo, la voz, la ciudad del
tiempo, el color del panel y las opciones de seguridad.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ..config import CONFIG_FILE, config
from .theme import theme
from .widgets.hud import WrapLabel

# (nombre visible, para qué sirve) por modelo.
MODELOS_CLAUDE = {
    "claude-sonnet-5": ("Claude Sonnet 5", "recomendado"),
    "claude-haiku-4-5": ("Claude Haiku 4.5", "el más barato"),
    "claude-opus-5": ("Claude Opus 5", "el más capaz"),
}

COLORES = {
    "Cian (Iron Man)": "#00E5FF",
    "Ámbar (Mark I)": "#FF8A00",
    "Verde (Matrix)": "#39FF14",
    "Rojo (alerta)": "#FF3B3B",
    "Violeta": "#B36BFF",
    "Blanco frío": "#DCEBF5",
}


class SettingsDialog(QDialog):
    """Ventana de ajustes. Devuelve True si algo requiere reiniciar."""

    def __init__(self, parent=None, modelos: list[str] | None = None,
                 voces: list[tuple[str, str]] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("J.A.R.V.I.S. — Ajustes")
        self.setMinimumWidth(660)
        self.setStyleSheet(theme.stylesheet())
        self.necesita_reinicio = False

        self._modelos = modelos or []
        self._voces = voces or []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        titulo = QLabel("AJUSTES")
        titulo.setObjectName("panelTitle")
        layout.addWidget(titulo)

        pestañas = QTabWidget()
        pestañas.addTab(self._pestaña_general(), "General")
        pestañas.addTab(self._pestaña_ia(), "Núcleo IA")
        pestañas.addTab(self._pestaña_voz(), "Voz")
        pestañas.addTab(self._pestaña_aspecto(), "Aspecto")
        layout.addWidget(pestañas)

        ruta = WrapLabel(f"El archivo de configuración está en:\n{CONFIG_FILE}")
        ruta.setObjectName("hint")
        layout.addWidget(ruta)

        botones = QHBoxLayout()
        botones.addStretch(1)
        cancelar = QPushButton("CANCELAR")
        cancelar.clicked.connect(self.reject)
        guardar = QPushButton("GUARDAR")
        guardar.clicked.connect(self._guardar)
        botones.addWidget(cancelar)
        botones.addWidget(guardar)
        layout.addLayout(botones)

    # ------------------------------------------------------------------
    # Pestañas
    # ------------------------------------------------------------------

    @staticmethod
    def _pagina() -> tuple[QWidget, QFormLayout]:
        pagina = QWidget()
        formulario = QFormLayout(pagina)
        formulario.setContentsMargins(6, 12, 6, 6)
        formulario.setSpacing(10)
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        # Sin esto, los campos no se estiran y los textos largos se recortan.
        formulario.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        formulario.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        return pagina, formulario

    def _pestaña_general(self) -> QWidget:
        pagina, form = self._pagina()

        self.trato = QLineEdit(str(config.get("user_title", "Señor")))
        self.trato.setObjectName("input")
        form.addRow("Cómo te llama:", self.trato)

        self.ciudad = QLineEdit(str(config.get("commands.city", "")))
        self.ciudad.setObjectName("input")
        self.ciudad.setPlaceholderText("Madrid, Valencia, Buenos Aires…")
        form.addRow("Ciudad para el tiempo:", self.ciudad)

        self.carpetas = QLineEdit(", ".join(config.get("commands.search_paths") or []))
        self.carpetas.setObjectName("input")
        self.carpetas.setPlaceholderText("D:/Proyectos, E:/Documentos")
        form.addRow("Carpetas extra de búsqueda:", self.carpetas)

        self.confirmar = QCheckBox("Pedir confirmación antes de apagar o reiniciar")
        self.confirmar.setChecked(bool(config.get("commands.confirm_dangerous", True)))
        form.addRow(self.confirmar)

        aviso = WrapLabel(
            "Desactivar la confirmación es peligroso: un «apaga el equipo» mal "
            "entendido por el micrófono apagaría el ordenador sin preguntar.")
        aviso.setObjectName("hint")
        form.addRow(aviso)

        self.margen = QSpinBox()
        self.margen.setRange(0, 120)
        self.margen.setSuffix(" segundos")
        self.margen.setValue(int(config.get("commands.shutdown_delay", 15)))
        form.addRow("Margen antes de apagar:", self.margen)

        return pagina

    def _pestaña_ia(self) -> QWidget:
        pagina, form = self._pagina()

        # --- qué cerebro responde ---
        self.proveedor = QComboBox()
        self.proveedor.addItem("API de Claude (Anthropic)", "claude")
        self.proveedor.addItem("Modelo local con Ollama", "ollama")
        indice = self.proveedor.findData(
            str(config.get("llm.provider", "claude")).lower())
        self.proveedor.setCurrentIndex(max(0, indice))
        self.proveedor.currentIndexChanged.connect(self._cambiar_proveedor)
        form.addRow("Cerebro:", self.proveedor)

        self.nota_proveedor = WrapLabel()
        self.nota_proveedor.setObjectName("hint")
        form.addRow(self.nota_proveedor)

        # --- Claude ---
        self.modelo_claude = QComboBox()
        for clave, datos in MODELOS_CLAUDE.items():
            self.modelo_claude.addItem(f"{datos[0]} — {datos[1]}", clave)
        indice = self.modelo_claude.findData(
            str(config.get("claude.model", "claude-sonnet-5")))
        self.modelo_claude.setCurrentIndex(max(0, indice))
        self.fila_modelo_claude = ("Modelo de Claude:", self.modelo_claude)
        form.addRow(*self.fila_modelo_claude)

        self.clave_label = WrapLabel()
        self.clave_label.setObjectName("hint")
        form.addRow(self.clave_label)

        self.longitud = QSpinBox()
        self.longitud.setRange(256, 8192)
        self.longitud.setSingleStep(256)
        self.longitud.setSuffix(" tokens")
        self.longitud.setValue(int(config.get("claude.max_tokens", 1024)))
        self.longitud.setToolTip(
            "Tope de la respuesta. 1024 tokens ≈ 700 palabras.\n"
            "Cuanto más alto, más puede extenderse (y más cuesta).")
        form.addRow("Longitud máxima:", self.longitud)

        self.esfuerzo = QComboBox()
        for etiqueta, valor in [("Bajo — respuestas rápidas (recomendado)", "low"),
                                ("Medio — equilibrado", "medium"),
                                ("Alto — piensa más, tarda más", "high")]:
            self.esfuerzo.addItem(etiqueta, valor)
        indice = self.esfuerzo.findData(str(config.get("claude.effort", "low")))
        self.esfuerzo.setCurrentIndex(max(0, indice))
        form.addRow("Esfuerzo:", self.esfuerzo)

        self.pensar = QCheckBox("Razonar antes de responder")
        self.pensar.setToolTip(
            "Claude piensa unos segundos antes de contestar.\n"
            "Acierta más en preguntas difíciles, pero tarda más y cuesta más.")
        self.pensar.setChecked(bool(config.get("claude.thinking", False)))
        form.addRow(self.pensar)

        self.ver_gasto = QCheckBox("Mostrar el gasto estimado en el panel")
        self.ver_gasto.setChecked(bool(config.get("claude.show_cost", True)))
        form.addRow(self.ver_gasto)

        # --- Ollama ---
        self.modelo = QComboBox()
        self.modelo.setEditable(True)
        actual = str(config.get("ollama.model", "llama3.1:8b"))
        opciones = list(dict.fromkeys(self._modelos + [actual]))
        self.modelo.addItems(opciones)
        self.modelo.setCurrentText(actual)
        form.addRow("Modelo local:", self.modelo)

        self.temperatura = QSlider(Qt.Orientation.Horizontal)
        self.temperatura.setRange(0, 100)
        self.temperatura.setValue(int(float(config.get("ollama.temperature", 0.7)) * 100))
        self.etiqueta_temp = QLabel()
        self.temperatura.valueChanged.connect(self._actualizar_temp)
        self._actualizar_temp(self.temperatura.value())
        fila = QHBoxLayout()
        fila.addWidget(self.temperatura, 1)
        fila.addWidget(self.etiqueta_temp)
        self.caja_temperatura = QWidget()
        self.caja_temperatura.setLayout(fila)
        form.addRow("Creatividad:", self.caja_temperatura)

        self.contexto = QSpinBox()
        self.contexto.setRange(1024, 32768)
        self.contexto.setSingleStep(1024)
        self.contexto.setValue(int(config.get("ollama.num_ctx", 8192)))
        form.addRow("Memoria del modelo:", self.contexto)

        # --- común ---
        self.turnos = QSpinBox()
        self.turnos.setRange(6, 200)
        self.turnos.setValue(int(config.get("memory.max_turns", 40)))
        form.addRow("Turnos recordados:", self.turnos)

        self._formulario_ia = form
        self._cambiar_proveedor()
        return pagina

    def _cambiar_proveedor(self) -> None:
        """Enseña solo los ajustes del cerebro elegido.

        Los dos juegos de opciones no se parecen —Claude no admite
        «creatividad», Ollama no tiene clave ni coste—, así que mezclarlos en
        pantalla solo confundiría.
        """
        from ..core.secrets import has_api_key, mask_api_key

        es_claude = self.proveedor.currentData() == "claude"

        for widget in (self.modelo_claude, self.clave_label, self.longitud,
                       self.esfuerzo, self.pensar, self.ver_gasto):
            self._mostrar_fila(widget, es_claude)
        for widget in (self.modelo, self.caja_temperatura, self.contexto):
            self._mostrar_fila(widget, not es_claude)

        if es_claude:
            self.nota_proveedor.setText(
                "Las respuestas las genera Claude en los servidores de Anthropic. "
                "Necesita conexión a internet y consume crédito de su cuenta.")
            if has_api_key():
                self.clave_label.setText(f"Clave detectada: {mask_api_key()}")
            else:
                self.clave_label.setText(
                    "⚠ No hay clave configurada. Cree el archivo "
                    f"{CONFIG_FILE.parent / '.env'} con la línea:\n"
                    "    ANTHROPIC_API_KEY=sk-ant-...")
        else:
            self.nota_proveedor.setText(
                "Las respuestas las genera un modelo en su propio equipo. "
                "Gratis y sin internet, pero de menor calidad y más lento.")

    def _mostrar_fila(self, widget, visible: bool) -> None:
        """Oculta un campo y su etiqueta a la vez."""
        widget.setVisible(visible)
        etiqueta = self._formulario_ia.labelForField(widget)
        if etiqueta is not None:
            etiqueta.setVisible(visible)

    def _actualizar_temp(self, valor: int) -> None:
        if valor <= 30:
            texto = "preciso"
        elif valor <= 75:
            texto = "equilibrado"
        else:
            texto = "creativo"
        self.etiqueta_temp.setText(f"{valor / 100:.2f}  ({texto})")

    def _pestaña_voz(self) -> QWidget:
        pagina, form = self._pagina()

        self.voz_activa = QCheckBox("El asistente responde hablando")
        self.voz_activa.setChecked(bool(config.get("voice.tts_enabled", True)))
        form.addRow(self.voz_activa)

        self.voz = QComboBox()
        self.voz.addItem("Automática (la del idioma del sistema)", "")
        for voz_id, nombre in self._voces:
            self.voz.addItem(nombre, voz_id)
        actual = str(config.get("voice.voice_id", ""))
        indice = self.voz.findData(actual)
        self.voz.setCurrentIndex(max(0, indice))
        form.addRow("Voz:", self.voz)

        self.velocidad = QSpinBox()
        self.velocidad.setRange(80, 320)
        self.velocidad.setSuffix(" palabras/min")
        self.velocidad.setValue(int(config.get("voice.rate", 180)))
        form.addRow("Velocidad al hablar:", self.velocidad)

        self.palabra_clave = QLineEdit(str(config.get("voice.wake_word", "jarvis")))
        self.palabra_clave.setObjectName("input")
        form.addRow("Palabra clave:", self.palabra_clave)

        self.idioma_voz = QComboBox()
        for etiqueta, codigo in [("Español (España)", "es-ES"),
                                 ("Español (México)", "es-MX"),
                                 ("Español (Argentina)", "es-AR"),
                                 ("Español (Colombia)", "es-CO"),
                                 ("Inglés (EE. UU.)", "en-US")]:
            self.idioma_voz.addItem(etiqueta, codigo)
        indice = self.idioma_voz.findData(str(config.get("voice.stt_language", "es-ES")))
        self.idioma_voz.setCurrentIndex(max(0, indice))
        form.addRow("Idioma del micrófono:", self.idioma_voz)

        return pagina

    def _pestaña_aspecto(self) -> QWidget:
        pagina, form = self._pagina()

        self.color = QComboBox()
        for nombre, valor in COLORES.items():
            self.color.addItem(nombre, valor)
        actual = str(config.get("ui.accent", "#00E5FF")).upper()
        for i in range(self.color.count()):
            if str(self.color.itemData(i)).upper() == actual:
                self.color.setCurrentIndex(i)
                break
        form.addRow("Color principal:", self.color)

        self.muestra = QFrame()
        self.muestra.setFixedHeight(26)
        self._pintar_muestra(self.color.currentData())
        self.color.currentIndexChanged.connect(
            lambda: self._pintar_muestra(self.color.currentData()))
        form.addRow(self.muestra)

        self.tamaño = QSpinBox()
        self.tamaño.setRange(8, 18)
        self.tamaño.setSuffix(" pt")
        self.tamaño.setValue(int(config.get("ui.font_size", 11)))
        form.addRow("Tamaño de letra:", self.tamaño)

        self.animaciones = QCheckBox("Animaciones (reactor, rejilla, onda)")
        self.animaciones.setChecked(bool(config.get("ui.animations", True)))
        form.addRow(self.animaciones)

        self.maximizada = QCheckBox("Abrir maximizado")
        self.maximizada.setChecked(bool(config.get("ui.start_maximized", False)))
        form.addRow(self.maximizada)

        nota = WrapLabel("Los cambios de aspecto se aplican al reiniciar el asistente.")
        nota.setObjectName("hint")
        form.addRow(nota)

        return pagina

    def _pintar_muestra(self, color: str) -> None:
        self.muestra.setStyleSheet(
            f"background-color: {color}; border-radius: 3px;")

    # ------------------------------------------------------------------
    # Guardar
    # ------------------------------------------------------------------

    def _guardar(self) -> None:
        aspecto_antes = (config.get("ui.accent"), config.get("ui.font_size"),
                         config.get("ui.animations"))

        config.set("user_title", self.trato.text().strip() or "Señor")
        config.set("commands.city", self.ciudad.text().strip())
        carpetas = [c.strip() for c in self.carpetas.text().split(",") if c.strip()]
        config.set("commands.search_paths", carpetas)
        config.set("commands.confirm_dangerous", self.confirmar.isChecked())
        config.set("commands.shutdown_delay", self.margen.value())

        config.set("llm.provider", self.proveedor.currentData())

        config.set("claude.model", self.modelo_claude.currentData())
        config.set("claude.max_tokens", self.longitud.value())
        config.set("claude.effort", self.esfuerzo.currentData())
        config.set("claude.thinking", self.pensar.isChecked())
        config.set("claude.show_cost", self.ver_gasto.isChecked())

        config.set("ollama.model", self.modelo.currentText().strip())
        config.set("ollama.temperature", self.temperatura.value() / 100)
        config.set("ollama.num_ctx", self.contexto.value())
        config.set("memory.max_turns", self.turnos.value())

        config.set("voice.tts_enabled", self.voz_activa.isChecked())
        config.set("voice.voice_id", self.voz.currentData() or "")
        config.set("voice.rate", self.velocidad.value())
        config.set("voice.wake_word", self.palabra_clave.text().strip() or "jarvis")
        config.set("voice.stt_language", self.idioma_voz.currentData())

        config.set("ui.accent", self.color.currentData())
        config.set("ui.font_size", self.tamaño.value())
        config.set("ui.animations", self.animaciones.isChecked())
        config.set("ui.start_maximized", self.maximizada.isChecked())

        config.save()

        aspecto_despues = (config.get("ui.accent"), config.get("ui.font_size"),
                           config.get("ui.animations"))
        self.necesita_reinicio = aspecto_antes != aspecto_despues
        self.accept()
