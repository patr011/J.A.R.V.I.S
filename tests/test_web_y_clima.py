"""Música y tiempo: se simulan las respuestas de internet.

Ninguna prueba sale a la red de verdad, para que funcionen sin conexión y
den siempre el mismo resultado.
"""

from __future__ import annotations

import pytest
import requests

from jarvis.commands import weather, web

# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------


class RespuestaFalsa:
    def __init__(self, texto="", json_data=None, status=200):
        self.text = texto
        self._json = json_data
        self.status_code = status

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


HTML_YOUTUBE = (
    '<!DOCTYPE html><html><head><title>despacito - YouTube</title></head><body>'
    '<script>var ytInitialData = {"contents":{"itemSectionRenderer":{"contents":['
    '{"videoRenderer":{"videoId":"kJQP7kiw5Fk","title":{"runs":[{"text":"Despacito"}]}}},'
    '{"videoRenderer":{"videoId":"72UO0v5ESUo"}}]}}};</script></body></html>'
)


@pytest.fixture
def navegador(monkeypatch):
    """Recoge las URL que se habrían abierto en el navegador."""
    abiertas: list[str] = []
    monkeypatch.setattr(web, "_open", lambda url: (abiertas.append(url), (True, ""))[1])
    return abiertas


# --------------------------------------------------------------------------
# Reproducir canciones
# --------------------------------------------------------------------------

def test_pone_el_video_y_no_la_busqueda(monkeypatch, navegador):
    """Lo importante: abrir el vídeo, que suena, y no la lista de resultados."""
    monkeypatch.setattr(requests, "get", lambda url, **k: RespuestaFalsa(HTML_YOUTUBE))
    resultado = web.play_song("despacito")
    assert resultado.ok
    assert navegador[-1] == "https://www.youtube.com/watch?v=kJQP7kiw5Fk"
    assert "Reproduciendo" in resultado.message


def test_filtra_a_videos(monkeypatch, navegador):
    """Sin el filtro, el primer resultado puede ser un canal y no sonaría nada."""
    pedidas: list[str] = []

    def capturar(url, **kwargs):
        pedidas.append(url)
        return RespuestaFalsa(HTML_YOUTUBE)

    monkeypatch.setattr(requests, "get", capturar)
    web.play_song("linkin park numb")
    assert "sp=EgIQAQ%3D%3D" in pedidas[0]


@pytest.mark.parametrize("fallo", [
    requests.ConnectionError("sin red"),
    requests.Timeout("tarda demasiado"),
])
def test_sin_internet_deja_la_busqueda_y_lo_dice(monkeypatch, navegador, fallo):
    def reventar(url, **kwargs):
        raise fallo

    monkeypatch.setattr(requests, "get", reventar)
    resultado = web.play_song("despacito")
    assert resultado.ok                              # no deja al usuario tirado
    assert "results?search_query" in navegador[-1]
    assert "no he podido" in resultado.message.lower()


def test_si_youtube_cambia_el_formato_no_se_rompe(monkeypatch, navegador):
    monkeypatch.setattr(requests, "get", lambda url, **k: RespuestaFalsa("<html>nada</html>"))
    resultado = web.play_song("despacito")
    assert "results?search_query" in navegador[-1]


def test_pedir_cancion_vacia():
    assert not web.play_song("   ").ok


# --------------------------------------------------------------------------
# El tiempo
# --------------------------------------------------------------------------

GEO_MADRID = {"results": [{"name": "Madrid", "latitude": 40.4165, "longitude": -3.70256,
                           "country": "España", "admin1": "Comunidad de Madrid"}]}

TIEMPO_DESPEJADO = {
    "current": {"temperature_2m": 31.2, "relative_humidity_2m": 28,
                "apparent_temperature": 34.6, "weather_code": 0, "wind_speed_10m": 11.5},
    "daily": {"temperature_2m_max": [35.1], "temperature_2m_min": [19.4],
              "precipitation_probability_max": [5]},
}

TIEMPO_LLUVIA = {
    "current": {"temperature_2m": 14.0, "relative_humidity_2m": 80,
                "apparent_temperature": 13.0, "weather_code": 63, "wind_speed_10m": 20.0},
    "daily": {"temperature_2m_max": [16.0], "temperature_2m_min": [11.0],
              "precipitation_probability_max": [85]},
}


@pytest.fixture
def sin_guardar_config(monkeypatch):
    monkeypatch.setattr("jarvis.commands.weather.config.save", lambda: None)


def _servidor_del_tiempo(monkeypatch, prevision, geo=GEO_MADRID):
    def _get(url, **kwargs):
        return RespuestaFalsa(json_data=geo if "geocoding" in url else prevision)
    monkeypatch.setattr(requests, "get", _get)


def test_dice_el_tiempo_actual(monkeypatch, sin_guardar_config):
    _servidor_del_tiempo(monkeypatch, TIEMPO_DESPEJADO)
    resultado = weather.get_weather("Madrid")
    assert resultado.ok
    assert "Madrid" in resultado.message
    assert "31" in resultado.message
    assert "despejado" in resultado.message


def test_avisa_del_paraguas_si_va_a_llover(monkeypatch, sin_guardar_config):
    _servidor_del_tiempo(monkeypatch, TIEMPO_LLUVIA)
    resultado = weather.get_weather("Madrid")
    assert "paraguas" in resultado.message


def test_ciudad_inexistente(monkeypatch, sin_guardar_config):
    _servidor_del_tiempo(monkeypatch, TIEMPO_DESPEJADO, geo={"results": []})
    assert not weather.get_weather("Ciudadinventada").ok


def test_sin_internet_lo_dice_claro(monkeypatch, sin_guardar_config):
    def reventar(url, **kwargs):
        raise requests.ConnectionError("sin red")
    monkeypatch.setattr(requests, "get", reventar)
    resultado = weather.get_weather("Madrid")
    assert not resultado.ok
    assert "conexión" in resultado.message


def test_sin_ciudad_pide_la_ciudad(monkeypatch, sin_guardar_config):
    monkeypatch.setattr("jarvis.commands.weather.config.get",
                        lambda clave, defecto=None: "" if clave == "commands.city" else defecto)
    resultado = weather.get_weather("")
    assert not resultado.ok
    assert "dígame" in resultado.message.lower()


@pytest.mark.parametrize("codigo,texto", [
    (0, "despejado"), (3, "nublado"), (63, "lloviendo"),
    (75, "nevada"), (95, "tormenta"), (999, "variable"),
])
def test_traduce_los_codigos_meteorologicos(codigo, texto):
    assert texto in weather.describe_code(codigo)
