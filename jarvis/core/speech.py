"""Voz: texto a voz (pyttsx3) y voz a texto (SpeechRecognition).

Las dos librerias son OPCIONALES. Si no estan instaladas el asistente sigue
funcionando por texto y simplemente avisa de que la voz no esta disponible.

Detalle importante: pyttsx3 no es seguro entre hilos. Por eso el motor se
crea dentro de un hilo dedicado y se le mandan frases por una cola; nunca se
toca desde la interfaz.
"""

from __future__ import annotations

import queue
import re
import threading
from typing import Callable

from ..config import config
from ..logging_setup import get_logger

log = get_logger("voz")

# --------------------------------------------------------------------------
# Deteccion de dependencias opcionales
# --------------------------------------------------------------------------

try:
    import pyttsx3
    TTS_AVAILABLE = True
except Exception:                                   # pragma: no cover
    pyttsx3 = None                                  # type: ignore[assignment]
    TTS_AVAILABLE = False

try:
    import speech_recognition as sr
    STT_AVAILABLE = True
except Exception:                                   # pragma: no cover
    sr = None                                       # type: ignore[assignment]
    STT_AVAILABLE = False


# --------------------------------------------------------------------------
# Texto a voz
# --------------------------------------------------------------------------

_SPEAK_CLEANUP = [
    (re.compile(r"```.*?```", re.S), " (bloque de código) "),
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"\*\*([^*]*)\*\*"), r"\1"),
    (re.compile(r"[*_#>|]"), " "),
    (re.compile(r"https?://\S+"), " enlace "),
    (re.compile(r"\s{2,}"), " "),
]


def clean_for_speech(text: str, max_chars: int = 600) -> str:
    """Quita Markdown, URLs y recorta para que la voz no se eternice."""
    out = text
    for pattern, repl in _SPEAK_CLEANUP:
        out = pattern.sub(repl, out)
    out = out.strip()
    if len(out) > max_chars:
        cut = out[:max_chars]
        last = max(cut.rfind("."), cut.rfind("?"), cut.rfind("!"))
        out = cut[: last + 1] if last > max_chars * 0.5 else cut + "..."
    return out


class TextToSpeech:
    """Cola de frases habladas atendida por un unico hilo."""

    def __init__(self) -> None:
        self.available = TTS_AVAILABLE
        self.enabled = bool(config.get("voice.tts_enabled", True)) and self.available
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._engine = None
        self._thread: threading.Thread | None = None
        self._speaking = threading.Event()
        self._stop_flag = threading.Event()
        self._failures = 0
        self.error: str = "" if self.available else (
            "pyttsx3 no está instalado (pip install pyttsx3)."
        )
        self.on_state_change: Callable[[bool], None] | None = None

        if self.available:
            self._thread = threading.Thread(target=self._worker, name="jarvis-tts", daemon=True)
            self._thread.start()

    # -- API publica ----------------------------------------------------

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    @property
    def is_busy(self) -> bool:
        """Hablando ahora mismo o con frases todavia en la cola."""
        return self._speaking.is_set() or not self._queue.empty()

    def say(self, text: str) -> None:
        """Encola una frase. No bloquea."""
        if not self.enabled or not text.strip():
            return
        cleaned = clean_for_speech(text)
        if cleaned:
            self._queue.put(cleaned)

    def stop(self) -> None:
        """Corta lo que se esta diciendo y vacia la cola."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass

    def set_enabled(self, value: bool) -> bool:
        self.enabled = bool(value) and self.available
        if not self.enabled:
            self.stop()
        config.set("voice.tts_enabled", self.enabled)
        config.save()
        return self.enabled

    def list_voices(self) -> list[tuple[str, str]]:
        if not self.available:
            return []
        try:
            engine = pyttsx3.init()
            voices = [(v.id, v.name) for v in engine.getProperty("voices")]
            del engine
            return voices
        except Exception:
            return []

    def shutdown(self) -> None:
        self._stop_flag.set()
        self.stop()
        self._queue.put(None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    # -- hilo interno ---------------------------------------------------

    def _init_engine(self) -> bool:
        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", config.get("voice.rate", 180))
            self._engine.setProperty("volume", config.get("voice.volume", 1.0))
            self._select_voice()
            return True
        except Exception as exc:                     # pragma: no cover
            self.error = f"No se pudo iniciar la voz: {exc}"
            log.error("No se pudo iniciar el motor de voz", exc_info=True)
            self.available = False
            self.enabled = False
            return False

    def _select_voice(self) -> None:
        """Elige la voz configurada o, si no hay, una en el idioma del usuario."""
        assert self._engine is not None
        wanted_id = config.get("voice.voice_id", "")
        try:
            voices = self._engine.getProperty("voices")
        except Exception:
            return

        if wanted_id:
            for v in voices:
                if v.id == wanted_id:
                    self._engine.setProperty("voice", v.id)
                    return

        lang = config.get("language", "es")
        keys = ("spanish", "español", "espanol", "helena", "sabina", "laura", "es-")
        if lang != "es":
            keys = ("english", "zira", "david", "hazel", "en-")
        for v in voices:
            haystack = f"{getattr(v, 'name', '')} {getattr(v, 'id', '')}".lower()
            if any(k in haystack for k in keys):
                self._engine.setProperty("voice", v.id)
                return

    def _worker(self) -> None:
        # La voz de Windows (SAPI5) se maneja por COM, y COM hay que
        # inicializarlo EN CADA HILO que lo use. Sin esto, crear el motor
        # dentro de este hilo falla y el asistente se queda mudo sin decir
        # por que. Es la causa mas habitual de "no se oye nada".
        com_ready = False
        try:
            import comtypes
            comtypes.CoInitialize()
            com_ready = True
        except Exception:
            pass

        try:
            if not self._init_engine():
                return
            self._speak_loop()
        finally:
            if com_ready:
                try:
                    import comtypes
                    comtypes.CoUninitialize()
                except Exception:
                    pass

    def _speak_loop(self) -> None:
        while not self._stop_flag.is_set():
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            try:
                self._speaking.set()
                if self.on_state_change:
                    self.on_state_change(True)
                self._engine.say(item)
                self._engine.runAndWait()
            except RuntimeError:
                # "run loop already started": reinicia el motor y sigue.
                try:
                    self._engine.endLoop()
                except Exception:
                    pass
                self._init_engine()
            except Exception as exc:                 # pragma: no cover
                # Con pythonw.exe no hay consola donde ver esto, asi que el
                # error se guarda para que la ventana pueda mostrarlo.
                self.error = f"Error al hablar: {type(exc).__name__}: {exc}"
                self._failures += 1
                log.error(self.error, exc_info=True)
                if self._failures >= 3:
                    self.error = (f"La voz ha fallado {self._failures} veces y se desactiva. "
                                  f"Último error: {exc}")
                    self.enabled = False
                    break
            finally:
                self._speaking.clear()
                if self.on_state_change:
                    self.on_state_change(False)
                self._queue.task_done()


# --------------------------------------------------------------------------
# Palabra clave ("Oye JARVIS")
# --------------------------------------------------------------------------

# El reconocedor rara vez escribe "jarvis" tal cual: suele entender algo
# parecido. Aceptar variantes evita tener que vocalizar como un locutor.
WAKE_VARIANTS = (
    "jarvis", "yarvis", "harvis", "jarbis", "yarbis", "jervis", "yervis",
    "charvis", "sharvis", "jarvi", "yarvi", "arvis", "travis", "jarvis.",
)

# Muletillas que pueden ir delante: "oye jarvis", "hey jarvis", "ok jarvis".
WAKE_PREFIXES = ("oye", "hey", "ey", "eh", "ok", "okey", "okay", "vale", "escucha")


def strip_wake_word(text: str, wake_word: str = "jarvis") -> tuple[bool, str]:
    """¿Empieza la frase por la palabra clave? Devuelve (sí/no, la orden).

    «Oye Jarvis, pon música»  ->  (True, "pon música")
    «Jarvis»                  ->  (True, "")          solo la llamada
    «pon música»              ->  (False, "pon música")
    """
    import unicodedata

    original = (text or "").strip()
    if not original:
        return False, ""

    # Normaliza para comparar, pero conserva el texto original para devolverlo.
    plano = unicodedata.normalize("NFD", original.lower())
    plano = "".join(c for c in plano if unicodedata.category(c) != "Mn")

    variantes = set(WAKE_VARIANTS)
    clave = (wake_word or "jarvis").strip().lower()
    if clave:
        variantes.add(clave)

    palabras = re.findall(r"[\w']+", plano)
    if not palabras:
        return False, ""

    indice = 0
    if palabras[0] in WAKE_PREFIXES and len(palabras) > 1:
        indice = 1

    if palabras[indice] not in variantes:
        return False, original

    # La orden es todo lo que va después de la palabra clave.
    restantes = palabras[indice + 1:]
    if not restantes:
        return True, ""

    # Recorta el texto original por el mismo punto, para no perder tildes.
    tokens_originales = re.findall(r"[\w']+|[^\w\s]", original)
    consumidas = 0
    corte = 0
    for posicion, token in enumerate(tokens_originales):
        if re.match(r"[\w']+", token):
            consumidas += 1
            if consumidas == indice + 1:
                corte = posicion + 1
                break
    orden = " ".join(tokens_originales[corte:])
    orden = re.sub(r"\s+([,.;:!?»)])", r"\1", orden)     # sin espacio antes del cierre
    orden = re.sub(r"([¿¡(«])\s+", r"\1", orden)         # ni después de la apertura
    return True, orden.strip(" ,.")


# --------------------------------------------------------------------------
# Voz a texto
# --------------------------------------------------------------------------

class SpeechToText:
    """Reconocimiento de voz con el microfono del equipo.

    Usa el reconocedor gratuito de Google que trae SpeechRecognition (necesita
    internet). Si no hay conexion se intenta Sphinx, si esta instalado.
    """

    def __init__(self) -> None:
        self.available = STT_AVAILABLE
        self.error = "" if STT_AVAILABLE else (
            "SpeechRecognition no está instalado (pip install SpeechRecognition pyaudio)."
        )
        self._recognizer = None
        self._mic = None
        self._calibrated = False
        self._lock = threading.Lock()

        if self.available:
            try:
                self._recognizer = sr.Recognizer()
                self._recognizer.energy_threshold = config.get("voice.energy_threshold", 300)
                self._recognizer.dynamic_energy_threshold = True
                self._recognizer.pause_threshold = config.get("voice.pause_threshold", 0.8)
            except Exception as exc:
                self.available = False
                self.error = f"No se pudo iniciar el reconocedor: {exc}"

    # -- microfono ------------------------------------------------------

    def list_microphones(self) -> list[str]:
        if not self.available:
            return []
        try:
            return list(sr.Microphone.list_microphone_names())
        except Exception as exc:
            self.error = f"No se detecta ningún micrófono: {exc}"
            return []

    def check_microphone(self) -> tuple[bool, str]:
        """Comprueba que haya un microfono utilizable."""
        if not self.available:
            return False, self.error
        try:
            with sr.Microphone():
                pass
            return True, "Micrófono disponible."
        except AttributeError:
            return False, ("PyAudio no está instalado. Ejecuta:  pip install pyaudio")
        except OSError as exc:
            return False, f"No se pudo abrir el micrófono: {exc}"
        except Exception as exc:
            return False, f"Micrófono no disponible: {exc}"

    # -- escucha --------------------------------------------------------

    def listen_once(self, timeout: float = 6.0) -> tuple[bool, str]:
        """Escucha una frase y la devuelve como texto.

        Bloquea; llamalo siempre desde un hilo de trabajo.
        Devuelve (exito, texto_o_mensaje_de_error).
        """
        if not self.available or self._recognizer is None:
            return False, self.error

        phrase_limit = config.get("voice.phrase_time_limit", 12)
        with self._lock:
            try:
                with sr.Microphone() as source:
                    if not self._calibrated:
                        self._recognizer.adjust_for_ambient_noise(source, duration=0.6)
                        self._calibrated = True
                    audio = self._recognizer.listen(
                        source, timeout=timeout, phrase_time_limit=phrase_limit
                    )
            except sr.WaitTimeoutError:
                return False, "No he oído nada."
            except AttributeError:
                return False, "PyAudio no está instalado. Ejecuta:  pip install pyaudio"
            except OSError as exc:
                return False, f"Problema con el micrófono: {exc}"

        language = config.get("voice.stt_language", "es-ES")
        try:
            text = self._recognizer.recognize_google(audio, language=language)
            return True, text
        except sr.UnknownValueError:
            return False, "No he entendido lo que ha dicho."
        except sr.RequestError:
            # Sin internet: intento con el reconocedor offline, si existe.
            try:
                text = self._recognizer.recognize_sphinx(audio)
                return True, text
            except Exception:
                return False, ("No hay conexión con el servicio de reconocimiento de voz. "
                               "Puede escribir el comando.")
        except Exception as exc:
            return False, f"Error al reconocer la voz: {exc}"
