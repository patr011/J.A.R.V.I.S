"""El panel de ajustes y la resistencia a fallos de Ollama."""

from __future__ import annotations

import pytest
import requests

from jarvis.config import config
from jarvis.core.ollama_client import OllamaClient, OllamaError

pytest.importorskip("PyQt6", reason="PyQt6 no está instalado")

from PyQt6.QtWidgets import QApplication          # noqa: E402

from jarvis.ui.settings_dialog import SettingsDialog  # noqa: E402


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


# --------------------------------------------------------------------------
# Panel de ajustes
# --------------------------------------------------------------------------

def test_el_panel_se_abre_con_todas_las_pestañas(app):
    dialogo = SettingsDialog(modelos=["llama3.1:8b", "llama3.2:3b"],
                             voces=[("id-1", "Helena"), ("id-2", "Pablo")])
    assert not dialogo.grab().isNull()
    dialogo.deleteLater()


def test_muestra_los_valores_actuales(app, monkeypatch):
    monkeypatch.setitem(config.as_dict(), "user_title", "Jefe")
    dialogo = SettingsDialog(modelos=["llama3.1:8b"])
    assert dialogo.trato.text() == "Jefe"
    dialogo.deleteLater()


def test_guardar_aplica_los_cambios(app, monkeypatch):
    guardado = {}
    monkeypatch.setattr(config, "save", lambda: guardado.setdefault("si", True))

    dialogo = SettingsDialog(modelos=["llama3.1:8b", "llama3.2:3b"])
    dialogo.trato.setText("Comandante")
    dialogo.ciudad.setText("Valencia")
    dialogo.modelo.setCurrentText("llama3.2:3b")
    dialogo.velocidad.setValue(200)
    dialogo._guardar()

    assert config.get("user_title") == "Comandante"
    assert config.get("commands.city") == "Valencia"
    assert config.get("ollama.model") == "llama3.2:3b"
    assert config.get("voice.rate") == 200
    assert guardado.get("si")
    dialogo.deleteLater()


def test_las_carpetas_se_guardan_como_lista(app, monkeypatch):
    monkeypatch.setattr(config, "save", lambda: True)
    dialogo = SettingsDialog()
    dialogo.carpetas.setText("D:/Proyectos, E:/Fotos")
    dialogo._guardar()
    assert config.get("commands.search_paths") == ["D:/Proyectos", "E:/Fotos"]
    dialogo.deleteLater()


def test_cambiar_el_color_pide_reinicio(app, monkeypatch):
    monkeypatch.setattr(config, "save", lambda: True)
    config.set("ui.accent", "#00E5FF")
    dialogo = SettingsDialog()
    for i in range(dialogo.color.count()):
        if dialogo.color.itemData(i) != "#00E5FF":
            dialogo.color.setCurrentIndex(i)
            break
    dialogo._guardar()
    assert dialogo.necesita_reinicio
    dialogo.deleteLater()


def test_no_deja_el_trato_vacio(app, monkeypatch):
    monkeypatch.setattr(config, "save", lambda: True)
    dialogo = SettingsDialog()
    dialogo.trato.setText("   ")
    dialogo._guardar()
    assert config.get("user_title") == "Señor"
    dialogo.deleteLater()


# --------------------------------------------------------------------------
# Ollama: aguantar caídas
# --------------------------------------------------------------------------

class RespuestaFalsa:
    def __init__(self, status=200, models=None):
        self.status_code = status
        self._models = models or []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def json(self):
        return {"models": [{"name": m} for m in self._models]}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_lines(self, decode_unicode=False):
        return iter(())


def test_si_ollama_se_cae_intenta_levantarlo(monkeypatch):
    """Ollama se apaga solo tras un rato: el usuario no debería notarlo."""
    cliente = OllamaClient(host="http://localhost:99999", model="prueba")
    intentos = {"n": 0}

    def post_que_falla(*a, **k):
        intentos["n"] += 1
        raise requests.ConnectionError("no hay nadie escuchando")

    monkeypatch.setattr(cliente._session, "post", post_que_falla)
    monkeypatch.setattr(cliente, "start_server", lambda: (False, "no instalado"))

    with pytest.raises(OllamaError) as error:
        cliente.chat_stream([{"role": "user", "content": "hola"}])
    assert "Ollama" in str(error.value)
    assert intentos["n"] == 1, "sin arrancar el servidor no debe reintentar"


def test_reintenta_una_vez_si_consigue_arrancarlo(monkeypatch):
    cliente = OllamaClient(host="http://localhost:99999", model="prueba")
    intentos = {"n": 0}

    def post(*a, **k):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise requests.ConnectionError("caído")
        return RespuestaFalsa()

    monkeypatch.setattr(cliente._session, "post", post)
    monkeypatch.setattr(cliente, "start_server", lambda: (True, "arrancado"))

    cliente.chat_stream([{"role": "user", "content": "hola"}])
    assert intentos["n"] == 2, "debería reintentar una vez tras arrancar Ollama"


def test_no_reintenta_infinitamente(monkeypatch):
    """Un bucle de reintentos colgaría el asistente."""
    cliente = OllamaClient(host="http://localhost:99999", model="prueba")
    intentos = {"n": 0}

    def post(*a, **k):
        intentos["n"] += 1
        raise requests.ConnectionError("sigue caído")

    monkeypatch.setattr(cliente._session, "post", post)
    monkeypatch.setattr(cliente, "start_server", lambda: (True, "arrancado"))

    with pytest.raises(OllamaError):
        cliente.chat_stream([{"role": "user", "content": "hola"}])
    assert intentos["n"] == 2, "solo un reintento, no un bucle"


def test_modelo_ausente_dice_cuales_hay(monkeypatch):
    cliente = OllamaClient(host="http://localhost:99999", model="fantasma")
    monkeypatch.setattr(cliente._session, "post", lambda *a, **k: RespuestaFalsa(status=404))
    monkeypatch.setattr(cliente, "list_models", lambda: ["llama3.1:8b", "llama3.2:3b"])

    with pytest.raises(OllamaError) as error:
        cliente.chat_stream([{"role": "user", "content": "hola"}])
    mensaje = str(error.value)
    assert "ollama pull fantasma" in mensaje
    assert "llama3.1:8b" in mensaje


def test_arrancar_sin_ollama_instalado(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda nombre: None)
    cliente = OllamaClient(host="http://localhost:99999")
    monkeypatch.setattr(cliente, "is_running", lambda: False)
    ok, mensaje = cliente.start_server()
    assert not ok
    assert "ollama.com" in mensaje
