"""La voz de ElevenLabs, probada sin gastar ni un caracter de verdad.

Lo que de verdad importa aquí no es que hable bonito, sino que **cuando falle
no deje mudo al asistente**: se paga por uso, va por internet y tiene cupo
mensual, así que fallar es parte de su funcionamiento normal.
"""

from __future__ import annotations

import threading

import pytest
import requests

from jarvis.config import config
from jarvis.core import tts_elevenlabs as el
from jarvis.core.tts_elevenlabs import ElevenLabsError, ElevenLabsTTS, GastoVoz

CLAVE = "sk_" + "a" * 40


@pytest.fixture(autouse=True)
def clave_de_mentira(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", CLAVE)


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setitem(config._data.setdefault("voice", {}), "elevenlabs_voice", "voz123")
    return ElevenLabsTTS(voice_id="voz123", model="eleven_flash_v2_5")


# --------------------------------------------------------------------------
# Dobles
# --------------------------------------------------------------------------

class RespuestaFalsa:
    def __init__(self, codigo=200, json_data=None, trozos=(), texto=""):
        self.status_code = codigo
        self._json = json_data or {}
        self._trozos = list(trozos)
        self.text = texto
        self.cerrada = False

    def json(self):
        return self._json

    def iter_content(self, chunk_size=4096):
        yield from self._trozos

    def close(self):
        self.cerrada = True


class AltavozFalso:
    """Se hace pasar por PyAudio y apunta lo que le mandan reproducir."""

    def __init__(self):
        self.escrito = b""
        self.cerrado = False
        self.paInt16 = 8

    def PyAudio(self):                              # noqa: N802 (nombre de PyAudio)
        return self

    def open(self, **kwargs):
        self.parametros = kwargs
        return self

    def write(self, datos):
        self.escrito += datos

    def stop_stream(self):
        pass

    def close(self):
        self.cerrado = True

    def terminate(self):
        pass


@pytest.fixture
def altavoz(monkeypatch):
    falso = AltavozFalso()
    monkeypatch.setitem(__import__("sys").modules, "pyaudio", falso)
    return falso


# --------------------------------------------------------------------------
# Hablar
# --------------------------------------------------------------------------

def test_el_audio_se_reproduce_segun_llega(cliente, altavoz, monkeypatch):
    """En streaming: si esperase al archivo entero, tardaría demasiado."""
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: RespuestaFalsa(trozos=[b"12", b"34", b"56"]))

    cliente.speak("hola")

    assert altavoz.escrito == b"123456"
    assert altavoz.parametros["rate"] == el.SAMPLE_RATE
    assert altavoz.parametros["channels"] == 1


def test_se_pide_pcm_y_no_mp3(cliente, altavoz, monkeypatch):
    """Un MP3 habría que descodificarlo, y eso pide ffmpeg instalado."""
    visto = {}

    def falso_post(url, **kwargs):
        visto["url"] = url
        visto["cuerpo"] = kwargs.get("json")
        return RespuestaFalsa(trozos=[b"x"])

    monkeypatch.setattr(requests, "post", falso_post)
    cliente.speak("hola")

    assert "output_format=pcm_" in visto["url"]
    assert visto["cuerpo"]["model_id"] == "eleven_flash_v2_5"
    assert visto["cuerpo"]["text"] == "hola"


def test_la_clave_va_en_la_cabecera_y_no_en_la_url(cliente, altavoz, monkeypatch):
    visto = {}

    def falso_post(url, **kwargs):
        visto["url"] = url
        visto["cabeceras"] = kwargs.get("headers")
        return RespuestaFalsa(trozos=[b"x"])

    monkeypatch.setattr(requests, "post", falso_post)
    cliente.speak("hola")

    assert visto["cabeceras"]["xi-api-key"] == CLAVE
    assert CLAVE not in visto["url"], "la clave no puede acabar en una URL"


def test_una_frase_vacia_no_gasta_nada(cliente, monkeypatch):
    def no_deberia(*a, **k):
        raise AssertionError("no hay que llamar a la API por una frase vacía")

    monkeypatch.setattr(requests, "post", no_deberia)
    cliente.speak("   ")
    assert cliente.gasto.frases == 0


def test_se_puede_cortar_a_media_frase(cliente, altavoz, monkeypatch):
    """Al pulsar Esc, la voz tiene que callarse ya, no al terminar."""
    def muchos_trozos(*a, **k):
        return RespuestaFalsa(trozos=[b"1", b"2", b"3", b"4", b"5"])

    monkeypatch.setattr(requests, "post", muchos_trozos)

    original = altavoz.write

    def escribir_y_cortar(datos):
        original(datos)
        cliente.stop()

    altavoz.write = escribir_y_cortar
    cliente.speak("una frase larga")

    assert altavoz.escrito == b"1", "no ha parado al primer trozo"
    assert cliente.gasto.frases == 0, "lo que no se ha dicho no se apunta"


# --------------------------------------------------------------------------
# Cuando falla
# --------------------------------------------------------------------------

@pytest.mark.parametrize("codigo, esperado", [
    (401, "no es válida"),
    (404, "ya no existe"),
    (422, "rechazado"),
    (429, "sin cupo"),
])
def test_cada_error_se_explica_en_castellano(cliente, altavoz, monkeypatch, codigo, esperado):
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: RespuestaFalsa(codigo=codigo, texto="{}"))

    with pytest.raises(ElevenLabsError) as fallo:
        cliente.speak("hola")
    assert esperado in str(fallo.value)


def test_sin_internet_lo_dice_y_recuerda_el_plan_b(cliente, monkeypatch):
    def sin_red(*a, **k):
        raise requests.ConnectionError("sin ruta al host")

    monkeypatch.setattr(requests, "post", sin_red)
    with pytest.raises(ElevenLabsError) as fallo:
        cliente.speak("hola")
    assert "conexión" in str(fallo.value)
    assert "Windows" in str(fallo.value)


def test_el_mensaje_de_la_api_se_aprovecha_si_lo_trae(cliente, monkeypatch):
    cuerpo = '{"detail": {"message": "model_not_found", "status": "invalid"}}'
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: RespuestaFalsa(codigo=422, texto=cuerpo))

    with pytest.raises(ElevenLabsError) as fallo:
        cliente.speak("hola")
    assert "model_not_found" in str(fallo.value)


def test_sin_clave_ni_se_intenta(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr("jarvis.core.secrets.load_env_files", lambda: [])
    cliente = ElevenLabsTTS(voice_id="voz123")

    listo, motivo = cliente.esta_listo()
    assert not listo
    assert "clave" in motivo.lower()


def test_sin_voz_elegida_avisa(monkeypatch):
    cliente = ElevenLabsTTS(voice_id="")
    listo, motivo = cliente.esta_listo()
    assert not listo
    assert "voz" in motivo.lower()


# --------------------------------------------------------------------------
# Voces y gasto
# --------------------------------------------------------------------------

def test_se_leen_las_voces_de_la_cuenta(cliente, monkeypatch):
    datos = {"voices": [
        {"voice_id": "abc", "name": "Rachel", "labels": {"gender": "female",
                                                         "accent": "american"}},
        {"voice_id": "def", "name": "Antoni", "labels": {}},
        {"name": "sin id, se ignora"},
    ]}
    monkeypatch.setattr(requests, "get", lambda *a, **k: RespuestaFalsa(json_data=datos))

    voces = cliente.list_voices()
    assert [v.voice_id for v in voces] == ["abc", "def"]
    assert "Rachel" in voces[0].etiqueta()
    assert "female" in voces[0].etiqueta()


def test_si_falla_la_lista_de_voces_no_revienta(cliente, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: RespuestaFalsa(codigo=401, texto="{}"))
    assert cliente.list_voices() == []
    assert "no es válida" in cliente.error


def test_se_cuentan_los_caracteres_hablados(cliente, altavoz, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: RespuestaFalsa(trozos=[b"x"]))
    cliente.speak("hola")
    cliente.speak("buenas tardes")

    assert cliente.gasto.frases == 2
    assert cliente.gasto.caracteres == len("hola") + len("buenas tardes")
    assert "17 caracteres" in cliente.gasto.resumen()


def test_el_resumen_enseña_lo_que_queda_de_cupo():
    gasto = GastoVoz()
    gasto.add("v1", "hola")
    gasto.cupo_usado, gasto.cupo_total = 4000, 10000
    assert "quedan 6.000" in gasto.resumen()


def test_sin_usar_no_asusta_con_numeros():
    assert "Sin usar" in GastoVoz().resumen()


# --------------------------------------------------------------------------
# Integración con el motor de voz
# --------------------------------------------------------------------------

def test_si_elevenlabs_no_esta_listo_se_habla_por_windows(monkeypatch):
    """Configurar mal la voz no puede dejar al asistente sin hablar."""
    from jarvis.core.speech import TextToSpeech

    monkeypatch.setitem(config._data.setdefault("voice", {}), "engine", "elevenlabs")
    monkeypatch.setitem(config._data["voice"], "elevenlabs_voice", "")   # sin voz

    tts = TextToSpeech()
    try:
        assert tts.engine_name == "windows"
        assert "voz" in tts.eleven_error.lower()
        assert "Windows" in tts.describe_engine()
    finally:
        tts.shutdown()


def test_un_fallo_hablando_pasa_el_relevo_a_windows(monkeypatch):
    """Que se caiga internet a media conversación no puede dejarlo mudo."""
    from jarvis.core import speech as modulo_voz

    tts = modulo_voz.TextToSpeech.__new__(modulo_voz.TextToSpeech)
    tts.engine_name = "elevenlabs"
    tts.eleven_error = ""
    tts.error = ""
    tts._engine = None

    class ElevenRoto:
        def speak(self, texto):
            raise ElevenLabsError("sin cupo")

    tts._eleven = ElevenRoto()

    assert tts._decir_con_elevenlabs("hola") is False
    assert tts.engine_name == "windows", "tenía que pasarse a la voz de Windows"
    assert "sin cupo" in tts.error


def test_el_hilo_de_audio_es_uno_solo(cliente, altavoz, monkeypatch):
    """Dos frases a la vez sonarían superpuestas y el audio se pisaría."""
    monkeypatch.setattr(requests, "post", lambda *a, **k: RespuestaFalsa(trozos=[b"x" * 10]))
    hilos = set()

    original = altavoz.write

    def apuntar(datos):
        hilos.add(threading.get_ident())
        original(datos)

    altavoz.write = apuntar
    cliente.speak("una")
    cliente.speak("dos")

    assert len(hilos) == 1
