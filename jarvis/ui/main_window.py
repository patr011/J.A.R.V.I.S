"""Ventana principal: el panel holografico de J.A.R.V.I.S.

Distribucion:

    ┌──────────────────────────────────────────────────────────┐
    │  J.A.R.V.I.S.                                    ─   ✕   │
    ├──────────────┬───────────────────────────────────────────┤
    │  reactor     │  conversación (lo que dices / responde)   │
    │  onda        │                                           │
    │  sistema     ├───────────────────────────────────────────┤
    │  núcleo IA   │  [ escribe aquí ]  [MIC] [VOZ] [ENVIAR]   │
    └──────────────┴───────────────────────────────────────────┘
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizeGrip, QSizePolicy, QVBoxLayout, QWidget,
)

from ..commands import system as syscmd
from ..config import config
from ..core.assistant import Assistant
from ..core.memory import Memory
from ..core.ollama_client import OllamaClient
from ..core.speech import SpeechToText, TextToSpeech
from .theme import theme
from .widgets.arc_reactor import ArcReactor
from .widgets.chat_view import ChatView
from .widgets.hud import HudBackground, StatBar
from .widgets.waveform import Waveform
from .workers import AssistantWorker, ListenWorker, StartupCheckWorker, WakeWordWorker

STATE_TEXT = {
    "idle": "EN ESPERA",
    "listening": "ESCUCHANDO...",
    "thinking": "PROCESANDO...",
    "speaking": "RESPONDIENDO...",
    "error": "ERROR",
}


def _panel(title: str) -> tuple[QFrame, QVBoxLayout]:
    """Crea un panel con borde y titulo, y devuelve su layout interno."""
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 10, 14, 12)
    layout.setSpacing(8)
    if title:
        label = QLabel(title)
        label.setObjectName("panelTitle")
        layout.addWidget(label)
    return frame, layout


class JarvisWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()

        # --- nucleo ---
        self.memory = Memory()
        self.llm = OllamaClient()
        self.assistant = Assistant(memory=self.memory, llm=self.llm)
        self.tts = TextToSpeech()
        self.stt = SpeechToText()

        self._worker: AssistantWorker | None = None
        self._listener: ListenWorker | None = None
        self._waker: WakeWordWorker | None = None
        self._drag_pos: QPoint | None = None
        self._mic_ready = False
        self._last_voice_error = ""
        self._closing = False

        self._build_ui()
        self._wire_shortcuts()
        self._start_timers()
        self._boot()

    # ==================================================================
    # Construccion de la interfaz
    # ==================================================================

    def _build_ui(self) -> None:
        self.setWindowTitle("J.A.R.V.I.S.")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.resize(1180, 740)
        self.setMinimumSize(900, 600)
        self.setObjectName("root")
        self.setStyleSheet(theme.stylesheet())

        # Fondo HUD (se redimensiona en resizeEvent)
        self.hud = HudBackground(self)
        self.hud.lower()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(10)

        root.addLayout(self._build_title_bar())

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_left_column(), 0)
        body.addLayout(self._build_right_column(), 1)
        root.addLayout(body, 1)

        root.addLayout(self._build_footer())

    # -- barra de titulo -------------------------------------------------

    def _build_title_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(10)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("J . A . R . V . I . S .")
        title.setObjectName("titleText")
        subtitle = QLabel("JUST A RATHER VERY INTELLIGENT SYSTEM")
        subtitle.setObjectName("subtitleText")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        bar.addLayout(titles)

        bar.addStretch(1)

        self.clock_label = QLabel("--:--:--")
        self.clock_label.setObjectName("statusLabel")
        bar.addWidget(self.clock_label)

        minimize = QPushButton("—")
        minimize.setObjectName("titleBarButton")
        minimize.setToolTip("Minimizar")
        minimize.clicked.connect(self.showMinimized)

        maximize = QPushButton("□")
        maximize.setObjectName("titleBarButton")
        maximize.setToolTip("Maximizar / restaurar")
        maximize.clicked.connect(self._toggle_maximized)

        close = QPushButton("✕")
        close.setObjectName("closeButton")
        close.setToolTip("Cerrar")
        close.clicked.connect(self.close)

        for button in (minimize, maximize, close):
            button.setFixedWidth(42)
            bar.addWidget(button)
        return bar

    # -- columna izquierda -----------------------------------------------

    def _build_left_column(self) -> QWidget:
        column = QWidget()
        column.setFixedWidth(320)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Reactor + estado
        reactor_frame, reactor_layout = _panel("")
        self.reactor = ArcReactor()
        reactor_layout.addWidget(self.reactor, alignment=Qt.AlignmentFlag.AlignCenter)

        self.state_label = QLabel(STATE_TEXT["idle"])
        self.state_label.setObjectName("statusLabel")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reactor_layout.addWidget(self.state_label)

        self.waveform = Waveform()
        reactor_layout.addWidget(self.waveform)
        layout.addWidget(reactor_frame)

        # Estado del sistema
        sys_frame, sys_layout = _panel("SISTEMA")
        self.bar_cpu = StatBar("CPU")
        self.bar_ram = StatBar("MEMORIA")
        self.bar_vol = StatBar("VOLUMEN")
        self.bar_bright = StatBar("BRILLO")
        self.bar_battery = StatBar("BATERÍA")
        for bar in (self.bar_cpu, self.bar_ram, self.bar_vol, self.bar_bright, self.bar_battery):
            sys_layout.addWidget(bar)
        layout.addWidget(sys_frame)

        # Nucleo de IA
        ai_frame, ai_layout = _panel("NÚCLEO IA")
        self.model_label = QLabel("Ollama: comprobando...")
        self.model_label.setObjectName("hint")
        self.model_label.setWordWrap(True)
        self.memory_label = QLabel("Memoria: 0 turnos")
        self.memory_label.setObjectName("hint")
        self.voice_label = QLabel("Voz: —")
        self.voice_label.setObjectName("hint")
        self.reminder_label = QLabel("Sin avisos programados")
        self.reminder_label.setObjectName("hint")
        for label in (self.model_label, self.memory_label, self.voice_label,
                      self.reminder_label):
            label.setWordWrap(True)
            ai_layout.addWidget(label)
        layout.addWidget(ai_frame)

        layout.addStretch(1)
        return column

    # -- columna derecha --------------------------------------------------

    def _build_right_column(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        self.chat = ChatView()
        self.chat.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.chat, 1)

        row = QHBoxLayout()
        row.setSpacing(8)

        self.input = QLineEdit()
        self.input.setObjectName("input")
        self.input.setPlaceholderText("Escriba una orden o una pregunta…   (F2 para hablar)")
        self.input.returnPressed.connect(self.send_message)
        self.input.setFont(QFont(theme.font_family, theme.font_size))
        row.addWidget(self.input, 1)

        self.mic_button = QPushButton("🎙 HABLAR")
        self.mic_button.setToolTip("Dictar una orden por micrófono (F2)")
        self.mic_button.clicked.connect(self.start_listening)
        row.addWidget(self.mic_button)

        self.wake_button = QPushButton("👂 MANOS LIBRES")
        self.wake_button.setCheckable(True)
        self.wake_button.setToolTip(
            "Escucha continua: diga «Oye JARVIS» seguido de la orden (F4)")
        self.wake_button.clicked.connect(self._toggle_wake_word)
        row.addWidget(self.wake_button)

        self.voice_button = QPushButton("🔊 VOZ")
        self.voice_button.setCheckable(True)
        self.voice_button.setChecked(self.tts.enabled)
        self.voice_button.setToolTip("Activar o desactivar la voz del asistente")
        self.voice_button.clicked.connect(self._toggle_voice)
        row.addWidget(self.voice_button)

        self.send_button = QPushButton("ENVIAR")
        self.send_button.clicked.connect(self.send_message)
        row.addWidget(self.send_button)

        layout.addLayout(row)
        return layout

    # -- pie ---------------------------------------------------------------

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        self.hint_label = QLabel(
            "F2 hablar · F4 manos libres · Esc detener · Ctrl+L limpiar · «ayuda»"
        )
        self.hint_label.setObjectName("hint")
        footer.addWidget(self.hint_label)
        footer.addStretch(1)

        grip = QSizeGrip(self)
        grip.setFixedSize(16, 16)
        footer.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        return footer

    # ==================================================================
    # Atajos de teclado y temporizadores
    # ==================================================================

    def _wire_shortcuts(self) -> None:
        QShortcut(QKeySequence("F2"), self, self.start_listening)
        QShortcut(QKeySequence("F4"), self, self.wake_button.click)
        QShortcut(QKeySequence("Ctrl+L"), self, self._clear_chat)
        QShortcut(QKeySequence("Esc"), self, self._stop_everything)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)

    def _start_timers(self) -> None:
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(2000)

        # La voz corre en otro hilo: se consulta su estado periodicamente.
        self._voice_timer = QTimer(self)
        self._voice_timer.timeout.connect(self._poll_voice_state)
        self._voice_timer.start(200)

        # Temporizadores y alarmas. Se comprueban desde aqui, en el hilo de la
        # ventana, para poder escribir en el chat sin riesgos.
        self._reminder_timer = QTimer(self)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start(1000)

        self._update_clock()
        self._update_stats()

    # ==================================================================
    # Arranque
    # ==================================================================

    def _boot(self) -> None:
        self.chat.add_separator("SISTEMA INICIADO")
        greeting = self.assistant.greeting()
        self.chat.add_message("assistant", greeting)
        self.tts.say(greeting)

        if not self.tts.available:
            self.chat.add_message("system", f"Voz desactivada: {self.tts.error}")

        self._check = StartupCheckWorker(self.llm, self.stt, parent=self)
        self._check.report.connect(self._on_startup_report)
        self._check.start()

        self.input.setFocus()

    @pyqtSlot(dict)
    def _on_startup_report(self, info: dict) -> None:
        if self._closing:
            return                                   # la ventana ya se va
        suggestion = info.get("suggestion") or {}
        hardware = info.get("hardware") or {}

        # --- Ollama ---
        if not info.get("ollama_running"):
            self.model_label.setText("Ollama: sin conexión")
            self.chat.add_message(
                "error",
                "No detecto Ollama en marcha.\n"
                "   1. Instálalo desde https://ollama.com/download\n"
                "   2. Abre una terminal y ejecuta:  ollama serve\n"
                f"   3. Descarga un modelo:  {suggestion.get('command', 'ollama pull llama3.2:3b')}\n"
                "Mientras tanto puede usar todos los comandos del sistema con normalidad."
            )
        elif not info.get("model_ready"):
            self.model_label.setText("Ollama: sin modelos")
            self.chat.add_message(
                "error",
                "Ollama está funcionando, pero no hay ningún modelo descargado.\n"
                f"   Ejecute en una terminal:  {suggestion.get('command', 'ollama pull llama3.2:3b')}"
            )
        else:
            model = str(info.get("model"))
            self.llm.model = model
            config.set("ollama.model", model)
            config.save()
            self.model_label.setText(f"Ollama: en línea\nModelo: {model}")
            self.chat.add_message("system", f"Núcleo de IA conectado. Modelo activo: {model}.")

        # --- Recomendacion de hardware (solo la primera vez) ---
        if suggestion and not config.get("ollama.suggestion_shown", False):
            ram = hardware.get("ram_gb", 0)
            gpu = hardware.get("gpu", "") or "no detectada"
            self.chat.add_message(
                "system",
                f"Análisis del equipo — RAM: {ram} GB · GPU: {gpu}\n"
                f"   Modelo recomendado: {suggestion['name']} ({suggestion['size']})\n"
                f"   {suggestion['reason']}\n"
                f"   Para instalarlo:  {suggestion['command']}"
            )
            config.set("ollama.suggestion_shown", True)
            config.save()

        # --- Microfono ---
        self._mic_ready = bool(info.get("mic_ok"))
        if self._mic_ready:
            self.voice_label.setText("Voz: micrófono listo")
        else:
            mensaje = info.get("mic_message") or "micrófono no disponible"
            self.voice_label.setText(f"Voz: {mensaje}")
            self.mic_button.setEnabled(False)
            self.mic_button.setToolTip(str(mensaje))

    # ==================================================================
    # Conversacion
    # ==================================================================

    @pyqtSlot()
    def send_message(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        if self._worker is not None and self._worker.isRunning():
            self.chat.add_message("system", "Un momento, todavía estoy con la orden anterior.")
            return

        self.input.clear()
        self.chat.add_message("user", text)
        self.tts.stop()
        self._set_state("thinking")
        self._set_busy(True)

        self._worker = AssistantWorker(self.assistant, text, parent=self)
        self._worker.stream_started.connect(self.chat.start_stream)
        self._worker.token.connect(self.chat.append_stream)
        self._worker.finished_ok.connect(self._on_response)
        self._worker.failed.connect(self._on_worker_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    @pyqtSlot()
    def _on_worker_finished(self) -> None:
        """Libera el hilo terminado para que no se acumulen en la sesión."""
        self._set_busy(False)
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()

    @pyqtSlot(str, str, bool)
    def _on_response(self, text: str, source: str, ok: bool) -> None:
        if source == "stream":
            self.chat.end_stream()
        else:
            self.chat.add_message("assistant" if ok else "error", text)

        if self.assistant.awaiting_confirmation:
            self.hint_label.setText(
                f"⚠ Esperando confirmación para {self.assistant.pending_prompt}: "
                "responda «sí» o «no»."
            )
        else:
            self.hint_label.setText(
                "F2 hablar · F4 manos libres · Esc detener · Ctrl+L limpiar · «ayuda»"
            )

        self.tts.say(text)
        self._set_state("speaking" if self.tts.enabled and text else "idle")
        self._update_memory_label()

    @pyqtSlot(str)
    def _on_worker_error(self, message: str) -> None:
        self.chat.end_stream()
        self.chat.add_message("error", message)
        self._set_state("error")
        QTimer.singleShot(2500, lambda: self._set_state("idle"))

    def _set_busy(self, busy: bool) -> None:
        self.send_button.setEnabled(not busy)
        self.send_button.setText("…" if busy else "ENVIAR")
        self.input.setEnabled(not busy)
        if not busy:
            self.input.setFocus()

    # ==================================================================
    # Voz
    # ==================================================================

    @pyqtSlot()
    def start_listening(self) -> None:
        if not self.stt.available:
            self.chat.add_message("system", self.stt.error)
            return
        if not self._mic_ready:
            self.chat.add_message("system", "No hay ningún micrófono disponible.")
            return
        if self._listener is not None and self._listener.isRunning():
            return

        self.tts.stop()
        self._set_state("listening")
        self.mic_button.setEnabled(False)
        self.mic_button.setText("🎙 …")

        self._listener = ListenWorker(self.stt, parent=self)
        self._listener.recognized.connect(self._on_recognized)
        self._listener.failed.connect(self._on_listen_failed)
        self._listener.finished.connect(self._on_listener_finished)
        self._listener.start()

    @pyqtSlot()
    def _on_listener_finished(self) -> None:
        self._reset_mic_button()
        listener, self._listener = self._listener, None
        if listener is not None:
            listener.deleteLater()

    @pyqtSlot(str)
    def _on_recognized(self, text: str) -> None:
        self.input.setText(text)
        self.send_message()

    @pyqtSlot(str)
    def _on_listen_failed(self, message: str) -> None:
        self.chat.add_message("system", message)
        self._set_state("idle")

    def _reset_mic_button(self) -> None:
        self.mic_button.setEnabled(self._mic_ready)
        self.mic_button.setText("🎙 HABLAR")

    # -- escucha continua -------------------------------------------------

    def _toggle_wake_word(self) -> None:
        if self.wake_button.isChecked():
            self._start_wake_word()
        else:
            self._stop_wake_word()

    def _start_wake_word(self) -> None:
        if not self._mic_ready:
            self.chat.add_message(
                "system",
                self.stt.error or "No hay micrófono disponible para la escucha continua.\n"
                "   Alternativa: pulse Windows+H y dicte directamente en la caja de texto.")
            self.wake_button.setChecked(False)
            return
        if self._waker is not None and self._waker.isRunning():
            return

        # No escucha mientras habla ni mientras piensa: se oiría a sí mismo.
        self._waker = WakeWordWorker(
            self.stt,
            is_busy=lambda: self.tts.is_busy or (self._worker is not None
                                                 and self._worker.isRunning()),
            parent=self)
        self._waker.heard.connect(self._on_wake_command)
        self._waker.woken.connect(self._on_woken)
        self._waker.status.connect(lambda m: self.chat.add_message("system", m))
        self._waker.stopped.connect(self._on_waker_stopped)
        self._waker.start()
        self.wake_button.setText("👂 ESCUCHANDO")

    def _stop_wake_word(self) -> None:
        self.wake_button.setChecked(False)
        self.wake_button.setText("👂 MANOS LIBRES")
        if self._waker is not None and self._waker.isRunning():
            self._waker.stop()

    @pyqtSlot()
    def _on_waker_stopped(self) -> None:
        self.wake_button.setChecked(False)
        self.wake_button.setText("👂 MANOS LIBRES")
        waker, self._waker = self._waker, None
        if waker is not None:
            waker.deleteLater()
        if self.reactor.state() == "listening":
            self._set_state("idle")

    @pyqtSlot()
    def _on_woken(self) -> None:
        """Ha oído su nombre pero sin orden: se queda esperando."""
        self._set_state("listening")
        self.hint_label.setText("Le escucho… diga la orden.")

    @pyqtSlot(str)
    def _on_wake_command(self, text: str) -> None:
        if not text.strip():
            return
        self.input.setText(text)
        self.send_message()

    def _toggle_voice(self) -> None:
        enabled = self.tts.set_enabled(self.voice_button.isChecked())
        self.voice_button.setChecked(enabled)
        if not self.tts.available:
            self.chat.add_message("system", self.tts.error)
            return
        self.chat.add_message("system", "Voz activada." if enabled else "Voz desactivada.")

    def _poll_voice_state(self) -> None:
        """Sincroniza el reactor y la onda con lo que hace la voz."""
        # El motor de voz vive en otro hilo: si falla al arrancar o al hablar,
        # no puede avisar por si mismo. Aqui se recoge el error y se enseña
        # una sola vez, para que no se quede mudo sin explicacion.
        if self.tts.error and self.tts.error != self._last_voice_error:
            self._last_voice_error = self.tts.error
            self.chat.add_message("system", f"Voz: {self.tts.error}")
            self.voice_label.setText(f"Voz: {self.tts.error}")
            self.voice_button.setChecked(self.tts.enabled)

        # `is_busy` incluye las frases aun en cola: si se usara `is_speaking`
        # el reactor parpadearia entre "hablando" y "en espera" en el hueco
        # que hay antes de que el motor de voz arranque.
        speaking = self.tts.is_busy
        current = self.reactor.state()

        if speaking and current != "speaking":
            self._set_state("speaking")
        elif not speaking and current == "speaking":
            self._set_state("idle")

        if current == "listening":
            self.waveform.set_active(True, "#7CFFCB")
            self.reactor.set_level(0.7)
        elif speaking:
            self.waveform.set_active(True, theme.accent)
            self.reactor.set_level(0.85)
        elif current == "thinking":
            self.waveform.set_active(True, theme.warn)
            self.reactor.set_level(0.4)
        else:
            self.waveform.set_active(False)
            self.reactor.set_level(0.0)

    # ==================================================================
    # Estado e indicadores
    # ==================================================================

    def _set_state(self, state: str) -> None:
        self.reactor.set_state(state)
        self.state_label.setText(STATE_TEXT.get(state, state.upper()))

    def _update_clock(self) -> None:
        from datetime import datetime
        self.clock_label.setText(datetime.now().strftime("%d/%m/%Y   %H:%M:%S"))

    def _update_stats(self) -> None:
        stats = syscmd.system_stats()
        self.bar_cpu.set_value(float(stats["cpu"]))
        self.bar_ram.set_value(float(stats["ram"]))

        vol = syscmd.volume.get_level()
        self.bar_vol.set_value(vol if vol is not None else 0,
                               text="" if vol is not None else "n/d")
        # Si sale «n/d», que al menos se pueda ver por qué al pasar el ratón.
        self.bar_vol.setToolTip(
            f"No puedo leer el nivel de volumen.\n{syscmd.volume.error}\n\n"
            "Subirlo y bajarlo sí funciona."
            if vol is None else f"Volumen: {vol}%  ({syscmd.volume.backend})")

        bright = syscmd.brightness.get_level()
        self.bar_bright.set_value(bright if bright is not None else 0,
                                  text="" if bright is not None else "n/d")

        battery = stats["battery"]
        if isinstance(battery, int) and battery >= 0:
            sufijo = " ⚡" if stats["plugged"] else ""
            self.bar_battery.set_value(battery, text=f"{battery}%{sufijo}")
        else:
            self.bar_battery.set_value(0, text="n/d")

        self._update_memory_label()

    def _check_reminders(self) -> None:
        """Avisa cuando vence un temporizador o una alarma."""
        if self._closing:
            return
        for aviso in self.assistant.reminders.check_due():
            texto = self.assistant.reminders.announcement(aviso)
            self.chat.add_message("assistant", "⏰  " + texto)
            self.tts.say(texto)
            self.memory.add_assistant(texto)
            # Un parpadeo del reactor para que se note aunque estés en otra ventana.
            self._set_state("speaking")
            QApplication.alert(self, 3000)
        self._update_reminder_label()

    def _update_reminder_label(self) -> None:
        pendientes = self.assistant.reminders.pending()
        if not pendientes:
            self.reminder_label.setText("Sin avisos programados")
            self.reminder_label.setToolTip("")
            return
        siguiente = pendientes[0]
        self.reminder_label.setText(
            f"{len(pendientes)} aviso(s) · el próximo en {siguiente.describe_remaining()}")
        self.reminder_label.setToolTip("\n".join(r.describe() for r in pendientes))

    def _update_memory_label(self) -> None:
        stats = self.memory.stats()
        self.memory_label.setText(
            f"Memoria: {stats['turnos']} turnos · {stats['hechos']} notas\n"
            f"Sesión: {stats['sesion']}"
        )

    # ==================================================================
    # Acciones varias
    # ==================================================================

    def _clear_chat(self) -> None:
        self.chat.clear_chat()
        self.memory.clear()
        self.chat.add_separator("CONVERSACIÓN REINICIADA")
        self._update_memory_label()

    def _stop_everything(self) -> None:
        self.tts.stop()
        self.assistant.cancel_generation()
        if self.chat.streaming:
            self.chat.end_stream()
        self._set_state("idle")

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ==================================================================
    # Eventos de ventana (arrastrar, redimensionar, cerrar)
    # ==================================================================

    def resizeEvent(self, event) -> None:           # noqa: N802
        self.hud.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)

    def mousePressEvent(self, event) -> None:       # noqa: N802
        # Solo se arrastra desde la franja superior (la barra de titulo).
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 70:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:        # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if not self.isMaximized():
                self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:     # noqa: N802
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.position().y() < 70:
            self._toggle_maximized()

    def closeEvent(self, event) -> None:            # noqa: N802
        self.tts.stop()
        self.assistant.cancel_generation()
        if self._waker is not None:
            self._waker.stop()

        # Hay que esperar a TODOS los hilos, incluido el de comprobación
        # inicial: si Qt destruye la ventana con un hilo suyo todavía en
        # marcha, el programa se cierra de golpe. Pasaba al cerrar durante
        # los primeros segundos, mientras se consultaba Ollama.
        self._closing = True
        for worker in (self._worker, self._listener, self._waker,
                       getattr(self, "_check", None)):
            if worker is None:
                continue
            try:
                if worker.isRunning():
                    worker.requestInterruption()
                    worker.wait(6000)
            except RuntimeError:
                pass                                 # ya lo había borrado Qt

        self.tts.shutdown()
        event.accept()
