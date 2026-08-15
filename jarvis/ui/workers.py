"""Hilos de trabajo.

Regla de oro en una interfaz grafica: nada que tarde puede ejecutarse en el
hilo de la ventana, o el programa se queda congelado. Aqui van todas las
tareas lentas: hablar con Ollama, escuchar el microfono y las comprobaciones
del arranque.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from ..core.assistant import Assistant
from ..core.llm import current_provider, describe
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


class WakeWordWorker(QThread):
    """Escucha continua: espera a oír «Oye JARVIS» y recoge la orden.

    Dos cuidados importantes:

    - No escucha mientras el asistente habla, o se oiría a sí mismo y
      entraría en bucle.
    - Los silencios y los ruidos que no entiende se ignoran en silencio; si
      no, llenaría la conversación de «no he entendido nada».
    """

    heard = pyqtSignal(str)          # orden ya sin la palabra clave
    woken = pyqtSignal()             # ha oído su nombre, espera la orden
    status = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(self, stt: SpeechToText, is_busy: Callable[[], bool] | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.stt = stt
        self.is_busy = is_busy or (lambda: False)
        self._running = True

    def stop(self) -> None:
        self._running = False
        self.requestInterruption()

    def run(self) -> None:                     # noqa: D102
        from ..config import config
        from ..core.speech import strip_wake_word

        clave = config.get("voice.wake_word", "jarvis")
        self.status.emit(f"Escuchando. Diga «Oye {clave.capitalize()}» seguido de la orden.")

        fallos_seguidos = 0
        while self._running and not self.isInterruptionRequested():
            # Mientras el asistente habla, ni escuchar: se oiría a sí mismo.
            if self.is_busy():
                self.msleep(300)
                continue

            try:
                ok, texto = self.stt.listen_once(timeout=4.0)
            except Exception as exc:
                self.status.emit(f"Micrófono no disponible: {exc}")
                break

            if not self._running:
                break

            if not ok:
                # Silencio o ruido: normal, se sigue escuchando sin quejarse.
                if "PyAudio" in texto or "micrófono" in texto.lower():
                    fallos_seguidos += 1
                    if fallos_seguidos >= 3:
                        self.status.emit(texto)
                        break
                continue

            fallos_seguidos = 0
            despierta, orden = strip_wake_word(texto, clave)
            if not despierta:
                continue

            if orden:
                self.heard.emit(orden)
            else:
                # Ha dicho solo el nombre: se queda a la escucha de la orden.
                self.woken.emit()
                if self.is_busy():
                    continue
                ok, seguimiento = self.stt.listen_once(timeout=6.0)
                if ok and seguimiento.strip():
                    self.heard.emit(seguimiento)

        self.stopped.emit()


class StartupCheckWorker(QThread):
    """Comprueba Ollama, el modelo y el microfono sin bloquear el arranque."""

    report = pyqtSignal(dict)

    def __init__(self, llm: OllamaClient, stt: SpeechToText | None, parent=None) -> None:
        super().__init__(parent)
        self.llm = llm
        self.stt = stt

    def run(self) -> None:                     # noqa: D102
        info: dict[str, object] = {
            "provider": current_provider(),
            "descripcion": describe(self.llm),
            "error": getattr(self.llm, "error", ""),
            "ollama_running": False,
            "models": [],
            "model_ready": False,
            "model": self.llm.model,
            "suggestion": None,
            "hardware": {},
            "mic_checked": self.stt is not None,
            "mic_ok": False,
            "mic_message": "",
            "volume_ok": True,
            "volume_error": "",
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
            else:
                info["error"] = getattr(self.llm, "error", "") or info["error"]
        except Exception as exc:
            info["error"] = str(exc)

        # La recomendacion de modelo segun el hardware solo aplica a Ollama:
        # con Claude el modelo corre en los servidores de Anthropic y da igual
        # la RAM que tenga el equipo.
        try:
            if info["provider"] != "ollama":
                raise StopIteration
            suggestion, hardware = suggest_model()
            info["suggestion"] = {
                "name": suggestion.name,
                "size": suggestion.size,
                "reason": suggestion.reason,
                "command": suggestion.command,
            }
            info["hardware"] = hardware
        except StopIteration:
            pass
        except Exception:
            pass

        if self.stt is not None:
            try:
                ok, message = self.stt.check_microphone()
                info["mic_ok"] = ok
                info["mic_message"] = message
            except Exception as exc:
                info["mic_message"] = str(exc)

        # El volumen se comprueba aqui, en un hilo aparte, y no en la ventana:
        # abrir el mezclador de Windows la primera vez tarda un poco. Ademas,
        # cada hilo tiene su propio enlace, asi que este intento no le sirve a
        # la ventana; lo que se busca es saber SI se puede, para poder
        # explicarlo en vez de dejar un «n/d» sin motivo.
        from ..commands.system import volume
        try:
            info["volume_ok"] = volume.get_level() is not None
            info["volume_error"] = volume.error
        except Exception as exc:                        # pragma: no cover
            info["volume_ok"] = False
            info["volume_error"] = str(exc)

        self.report.emit(info)
