"""Hilos de trabajo.

Regla de oro en una interfaz grafica: nada que tarde puede ejecutarse en el
hilo de la ventana, o el programa se queda congelado. Aqui van todas las
tareas lentas: hablar con Ollama, escuchar el microfono y las comprobaciones
del arranque.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from ..core.assistant import Assistant
from ..core.ollama_client import OllamaClient, suggest_model
from ..core.speech import SpeechToText


class AssistantWorker(QThread):
    """Procesa un mensaje del usuario (comando o pregunta al modelo)."""

    token = pyqtSignal(str)                    # fragmento de respuesta del modelo
    stream_started = pyqtSignal()              # el modelo ha empezado a escribir
    finished_ok = pyqtSignal(str, str, bool)   # texto, origen, ok
    failed = pyqtSignal(str)

    def __init__(self, assistant: Assistant, text: str, parent=None) -> None:
        super().__init__(parent)
        self.assistant = assistant
        self.text = text
        self._started_stream = False

    def _on_token(self, token: str) -> None:
        if not self._started_stream:
            self._started_stream = True
            self.stream_started.emit()
        self.token.emit(token)

    def run(self) -> None:                     # noqa: D102
        try:
            response = self.assistant.process(self.text, on_token=self._on_token)
            source = "stream" if self._started_stream else response.source
            self.finished_ok.emit(response.text, source, response.ok)
        except Exception as exc:               # red de seguridad: nunca romper la UI
            self.failed.emit(f"Error interno del asistente: {exc}")


class ListenWorker(QThread):
    """Escucha el microfono una vez y devuelve el texto reconocido."""

    listening = pyqtSignal()
    recognized = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, stt: SpeechToText, timeout: float = 7.0, parent=None) -> None:
        super().__init__(parent)
        self.stt = stt
        self.timeout = timeout

    def run(self) -> None:                     # noqa: D102
        self.listening.emit()
        try:
            ok, text = self.stt.listen_once(timeout=self.timeout)
        except Exception as exc:
            self.failed.emit(f"Error con el micrófono: {exc}")
            return
        if ok:
            self.recognized.emit(text)
        else:
            self.failed.emit(text)


class StartupCheckWorker(QThread):
    """Comprueba Ollama, el modelo y el microfono sin bloquear el arranque."""

    report = pyqtSignal(dict)

    def __init__(self, llm: OllamaClient, stt: SpeechToText | None, parent=None) -> None:
        super().__init__(parent)
        self.llm = llm
        self.stt = stt

    def run(self) -> None:                     # noqa: D102
        info: dict[str, object] = {
            "ollama_running": False,
            "models": [],
            "model_ready": False,
            "model": self.llm.model,
            "suggestion": None,
            "hardware": {},
            "mic_ok": False,
            "mic_message": "",
        }
        try:
            info["ollama_running"] = self.llm.is_running()
            if info["ollama_running"]:
                models = self.llm.list_models()
                info["models"] = models
                resolved = self.llm.resolve_model()
                if resolved:
                    info["model"] = resolved
                    info["model_ready"] = True
        except Exception:
            pass

        try:
            suggestion, hardware = suggest_model()
            info["suggestion"] = {
                "name": suggestion.name,
                "size": suggestion.size,
                "reason": suggestion.reason,
                "command": suggestion.command,
            }
            info["hardware"] = hardware
        except Exception:
            pass

        if self.stt is not None:
            try:
                ok, message = self.stt.check_microphone()
                info["mic_ok"] = ok
                info["mic_message"] = message
            except Exception as exc:
                info["mic_message"] = str(exc)

        self.report.emit(info)
