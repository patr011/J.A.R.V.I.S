"""Voz de ElevenLabs: voces sintéticas de calidad, por internet.

La alternativa a la voz de Windows. Suena muchísimo mejor, pero tiene tres
diferencias que condicionan todo el diseño de este archivo:

    1. Cuesta dinero (por caracteres hablados) y tiene cupo mensual.
    2. Necesita internet, y por tanto puede fallar a mitad de una frase.
    3. Tarda unas décimas en empezar, porque hay que ir a buscar el audio.

Por eso se pide el audio en streaming y se va reproduciendo según llega, en
vez de esperar al archivo entero: así el retardo es de menos de un segundo.
Y por eso, si algo falla, quien llama puede volver a la voz de Windows sin
que el asistente se quede mudo.

El audio se pide en PCM crudo y se reproduce con PyAudio -que ya hace falta
para el micrófono-, en lugar de MP3. Un MP3 habría que descodificarlo, y eso
significa ffmpeg instalado en el equipo: justo el tipo de dependencia que
este proyecto evita.

La clave va en ELEVENLABS_API_KEY, igual que la de Claude: nunca en el
código ni en la configuración.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field

import requests

from ..config import config
from ..logging_setup import get_logger
from .secrets import get_elevenlabs_key

log = get_logger("voz-elevenlabs")

API_BASE = "https://api.elevenlabs.io/v1"

# PCM de 24 kHz: buena calidad para voz y lo reproduce PyAudio tal cual.
SAMPLE_RATE = 24000
OUTPUT_FORMAT = f"pcm_{SAMPLE_RATE}"

# Modelos. El de por defecto es el rápido: en un asistente importa más
# contestar pronto que la última décima de calidad.
MODELOS = {
    "eleven_flash_v2_5": "Flash v2.5 — el más rápido (recomendado)",
    "eleven_turbo_v2_5": "Turbo v2.5 — rápido y algo mejor",
    "eleven_multilingual_v2": "Multilingual v2 — el que mejor suena, más lento",
}
MODELO_POR_DEFECTO = "eleven_flash_v2_5"

CONSOLA = "https://elevenlabs.io/app/settings/api-keys"


class ElevenLabsError(Exception):
    """Fallo hablando con ElevenLabs, ya traducido a algo entendible."""


@dataclass
class Voz:
    """Una voz de la cuenta del usuario."""

    voice_id: str
    nombre: str
    descripcion: str = ""

    def etiqueta(self) -> str:
        return f"{self.nombre} — {self.descripcion}" if self.descripcion else self.nombre


@dataclass
class GastoVoz:
    """Cuántos caracteres se llevan hablados. ElevenLabs cobra por caracter."""

    caracteres: int = 0
    frases: int = 0
    cupo_usado: int = 0
    cupo_total: int = 0
    por_voz: dict[str, int] = field(default_factory=dict)

    def add(self, voice_id: str, texto: str) -> None:
        self.caracteres += len(texto)
        self.frases += 1
        self.por_voz[voice_id] = self.por_voz.get(voice_id, 0) + len(texto)

    def resumen(self) -> str:
        if not self.frases:
            return "Sin usar todavía"
        if self.cupo_total:
            queda = max(0, self.cupo_total - self.cupo_usado)
            return f"{self.caracteres} caracteres · quedan {queda:,}".replace(",", ".")
        return f"{self.caracteres} caracteres · {self.frases} frases"


def _traducir(exc: Exception, codigo: int = 0, cuerpo: str = "") -> ElevenLabsError:
    """Convierte el fallo en algo que diga qué hacer.

    Los mensajes crudos de la API vienen en inglés y en JSON anidado; aquí se
    traduce solo lo que el usuario puede arreglar por su cuenta.
    """
    detalle = ""
    if cuerpo:
        try:
            datos = json.loads(cuerpo)
            bruto = datos.get("detail", datos)
            if isinstance(bruto, dict):
                detalle = str(bruto.get("message") or bruto.get("status") or "")
            else:
                detalle = str(bruto)
        except (ValueError, AttributeError):
            detalle = cuerpo[:200]

    if codigo == 401:
        return ElevenLabsError(
            "La clave de ElevenLabs no es válida o ha caducado.\n"
            f"   Revísala en {CONSOLA}")
    if codigo == 403:
        return ElevenLabsError(
            "Tu cuenta de ElevenLabs no tiene permiso para esto.\n"
            f"   {detalle}" if detalle else
            "Tu cuenta de ElevenLabs no tiene permiso para esto.")
    if codigo == 404:
        return ElevenLabsError(
            "Esa voz ya no existe en tu cuenta.\n"
            "   Elige otra en Ajustes → Voz.")
    if codigo == 422:
        return ElevenLabsError(
            f"ElevenLabs ha rechazado la petición: {detalle or 'datos incorrectos'}\n"
            "   Suele ser el modelo elegido: prueba con otro en Ajustes → Voz.")
    if codigo == 429:
        return ElevenLabsError(
            "Te has quedado sin cupo de ElevenLabs este mes, o vas demasiado rápido.\n"
            "   Puedes volver a la voz de Windows en Ajustes → Voz.")
    if isinstance(exc, requests.Timeout):
        return ElevenLabsError("ElevenLabs ha tardado demasiado en responder.")
    if isinstance(exc, requests.ConnectionError):
        return ElevenLabsError(
            "No hay conexión con ElevenLabs. Comprueba tu internet.\n"
            "   Sin conexión, la voz de Windows sigue funcionando.")
    if codigo:
        return ElevenLabsError(f"ElevenLabs ha respondido {codigo}. {detalle}".strip())
    return ElevenLabsError(f"Fallo con ElevenLabs: {exc}")


class ElevenLabsTTS:
    """Cliente de voz. Pensado para usarse desde un único hilo de audio."""

    def __init__(self, voice_id: str = "", model: str = "") -> None:
        self.voice_id = voice_id or str(config.get("voice.elevenlabs_voice", ""))
        self.model = model or str(config.get("voice.elevenlabs_model", MODELO_POR_DEFECTO))
        self.gasto = GastoVoz()
        self.error = ""
        self._cancelar = threading.Event()
        self._audio = None          # PyAudio
        self._stream = None

    # -- estado ---------------------------------------------------------

    @property
    def hay_clave(self) -> bool:
        return bool(get_elevenlabs_key())

    def esta_listo(self) -> tuple[bool, str]:
        """¿Se puede hablar con esta configuración? Devuelve (sí/no, motivo)."""
        if not self.hay_clave:
            return False, ("No hay clave de ElevenLabs.\n"
                           f"   Sácala en {CONSOLA} y guárdala con poner_clave.bat")
        if not self.voice_id:
            return False, ("No has elegido ninguna voz de ElevenLabs.\n"
                           "   Elige una en Ajustes → Voz.")
        try:
            import pyaudio                              # noqa: F401
        except ImportError:
            return False, ("Falta PyAudio, que es quien reproduce el audio.\n"
                           "   Instálalo con:  pip install pyaudio")
        return True, "Voz de ElevenLabs lista."

    # -- consultas a la API ---------------------------------------------

    def _cabeceras(self) -> dict[str, str]:
        clave = get_elevenlabs_key()
        if not clave:
            raise ElevenLabsError("No hay clave de ElevenLabs configurada.")
        return {"xi-api-key": clave, "Content-Type": "application/json"}

    def list_voices(self) -> list[Voz]:
        """Las voces de la cuenta. Lista vacía si algo falla."""
        try:
            r = requests.get(f"{API_BASE}/voices", headers=self._cabeceras(), timeout=15)
            if r.status_code != 200:
                raise _traducir(Exception(), r.status_code, r.text)
            datos = r.json()
        except ElevenLabsError as exc:
            self.error = str(exc)
            return []
        except (requests.RequestException, ValueError) as exc:
            self.error = str(_traducir(exc))
            return []

        voces: list[Voz] = []
        for bruto in datos.get("voices", []):
            identificador = bruto.get("voice_id") or bruto.get("voiceId") or ""
            if not identificador:
                continue
            etiquetas = bruto.get("labels") or {}
            descripcion = ", ".join(
                str(v) for k, v in etiquetas.items()
                if k in ("accent", "gender", "age", "language") and v)
            voces.append(Voz(identificador, bruto.get("name") or identificador, descripcion))
        self.error = ""
        return voces

    def actualizar_cupo(self) -> None:
        """Lee cuánto cupo queda. Si falla, se calla: es solo informativo."""
        try:
            r = requests.get(f"{API_BASE}/user/subscription",
                             headers=self._cabeceras(), timeout=10)
            if r.status_code != 200:
                return
            datos = r.json()
            self.gasto.cupo_usado = int(datos.get("character_count", 0))
            self.gasto.cupo_total = int(datos.get("character_limit", 0))
        except (requests.RequestException, ValueError, TypeError, ElevenLabsError):
            pass

    # -- hablar ---------------------------------------------------------

    def stop(self) -> None:
        """Corta la frase que se esté diciendo."""
        self._cancelar.set()

    def speak(self, texto: str) -> None:
        """Dice el texto. Bloquea hasta terminar; llámalo desde un hilo.

        Lanza ElevenLabsError si no se ha podido decir, para que quien llame
        pueda recurrir a la voz de Windows.
        """
        texto = (texto or "").strip()
        if not texto:
            return
        self._cancelar.clear()

        cuerpo = {
            "text": texto,
            "model_id": self.model,
            "voice_settings": {
                "stability": float(config.get("voice.elevenlabs_stability", 0.5)),
                "similarity_boost": float(config.get("voice.elevenlabs_similarity", 0.75)),
                "speed": float(config.get("voice.elevenlabs_speed", 1.0)),
            },
        }
        url = (f"{API_BASE}/text-to-speech/{self.voice_id}/stream"
               f"?output_format={OUTPUT_FORMAT}")

        try:
            respuesta = requests.post(url, headers=self._cabeceras(), json=cuerpo,
                                      stream=True, timeout=(10, 60))
        except requests.RequestException as exc:
            raise _traducir(exc) from exc

        if respuesta.status_code != 200:
            # El cuerpo del error es corto; con stream=True hay que leerlo.
            try:
                detalle = respuesta.text
            except Exception:
                detalle = ""
            respuesta.close()
            raise _traducir(Exception(), respuesta.status_code, detalle)

        try:
            self._reproducir(respuesta)
        finally:
            respuesta.close()

        if not self._cancelar.is_set():
            self.gasto.add(self.voice_id, texto)

    def _reproducir(self, respuesta) -> None:
        """Va sacando por los altavoces el audio según llega."""
        import pyaudio

        self._audio = pyaudio.PyAudio()
        try:
            self._stream = self._audio.open(
                format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE, output=True)
        except Exception as exc:
            self._audio.terminate()
            self._audio = None
            raise ElevenLabsError(
                f"No se puede abrir la salida de audio: {exc}\n"
                "   Comprueba que hay altavoces o auriculares conectados.") from exc

        try:
            for trozo in respuesta.iter_content(chunk_size=4096):
                if self._cancelar.is_set():
                    break
                if trozo:
                    self._stream.write(trozo)
        except Exception as exc:
            raise _traducir(exc) from exc
        finally:
            self._cerrar_audio()

    def _cerrar_audio(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._audio is not None:
            try:
                self._audio.terminate()
            except Exception:
                pass
            self._audio = None
