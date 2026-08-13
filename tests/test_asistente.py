"""El asistente completo: confirmaciones, memoria y trato con el modelo."""

from __future__ import annotations

import json

import pytest
import requests

from jarvis.core.assistant import Assistant
from jarvis.core.memory import Memory
from jarvis.core.ollama_client import OllamaClient, OllamaError

from .dobles import sistema_simulado


@pytest.fixture
def memoria(tmp_path, monkeypatch):
    """Memoria que escribe en una carpeta temporal, no en la del usuario."""
    monkeypatch.setattr("jarvis.core.memory.MEMORY_FILE", tmp_path / "memoria.json")
    return Memory()


# --------------------------------------------------------------------------
# Confirmaciones: lo más delicado del asistente
# --------------------------------------------------------------------------

def test_apagar_solo_se_ejecuta_tras_decir_si(memoria):
    with sistema_simulado() as registro:
        asistente = Assistant(memory=memoria)
        asistente.process("apaga el equipo")
        assert asistente.awaiting_confirmation
        assert "apagar-confirmado" not in [c[0] for c in registro.llamadas]

        asistente.process("sí")
        assert "apagar-confirmado" in [c[0] for c in registro.llamadas]
        assert not asistente.awaiting_confirmation


def test_decir_no_cancela_el_apagado(memoria):
    with sistema_simulado() as registro:
        asistente = Assistant(memory=memoria)
        asistente.process("apaga el equipo")
        respuesta = asistente.process("no")
        assert "cancelado" in respuesta.text.lower()
        assert "apagar-confirmado" not in [c[0] for c in registro.llamadas]


def test_responder_otra_cosa_cancela_por_seguridad(memoria):
    """Si no dice ni sí ni no, no se apaga: se cancela y se atiende lo nuevo."""
    with sistema_simulado() as registro:
        asistente = Assistant(memory=memoria)
        asistente.process("apaga el equipo")
        respuesta = asistente.process("qué hora es")
        assert "apagar-confirmado" not in [c[0] for c in registro.llamadas]
        assert not asistente.awaiting_confirmation
        assert "hora" in respuesta.text.lower() or "las" in respuesta.text.lower()


@pytest.mark.parametrize("afirmacion", ["sí", "si", "claro", "adelante", "hazlo", "confirmo", "vale"])
def test_formas_de_decir_que_si(memoria, afirmacion):
    with sistema_simulado() as registro:
        asistente = Assistant(memory=memoria)
        asistente.process("apaga el equipo")
        asistente.process(afirmacion)
        assert "apagar-confirmado" in [c[0] for c in registro.llamadas], \
            f"«{afirmacion}» debería confirmar"


@pytest.mark.parametrize("negacion", ["no", "cancela", "mejor no", "olvidalo", "para"])
def test_formas_de_decir_que_no(memoria, negacion):
    with sistema_simulado() as registro:
        asistente = Assistant(memory=memoria)
        asistente.process("apaga el equipo")
        asistente.process(negacion)
        assert "apagar-confirmado" not in [c[0] for c in registro.llamadas], \
            f"«{negacion}» NO debería confirmar"


# --------------------------------------------------------------------------
# Memoria
# --------------------------------------------------------------------------

def test_recuerda_lo_que_se_le_dice_en_la_sesion(memoria):
    with sistema_simulado():
        asistente = Assistant(memory=memoria)
        asistente.process("recuerda que mi perro se llama Rocky")
        respuesta = asistente.process("¿qué te dije?")
        assert "Rocky" in respuesta.text


def test_el_historial_llega_al_modelo(memoria):
    with sistema_simulado():
        asistente = Assistant(memory=memoria)
        asistente.memory.add_user("me llamo Ana")
        asistente.memory.add_assistant("Encantado, Ana.")
        historial = asistente.memory.history()
        assert [m["role"] for m in historial] == ["user", "assistant"]
        assert "Ana" in historial[0]["content"]


def test_olvidar_borra_las_notas(memoria):
    memoria.remember("me gusta el café")
    assert memoria.facts
    memoria.forget("todo")
    assert not memoria.facts


def test_la_memoria_no_crece_sin_limite(memoria):
    memoria.max_turns = 10
    for i in range(50):
        memoria.add_user(f"mensaje {i}")
    assert len(memoria.turns) <= 10
    # Y conserva los más recientes, que son los que importan.
    assert "mensaje 49" in memoria.turns[-1].content


# --------------------------------------------------------------------------
# Modelo de lenguaje
# --------------------------------------------------------------------------

class RespuestaFalsa:
    """Imita el streaming de Ollama."""

    def __init__(self, trozos, status=200):
        self._trozos = trozos
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_lines(self, decode_unicode=False):
        for trozo in self._trozos:
            yield json.dumps({"message": {"content": trozo}, "done": False})
        yield json.dumps({"message": {"content": ""}, "done": True})


def test_el_streaming_reconstruye_la_respuesta(monkeypatch):
    cliente = OllamaClient(host="http://localhost:99999", model="prueba")
    trozos = ["La ", "capital ", "es ", "París."]
    monkeypatch.setattr(cliente._session, "post", lambda *a, **k: RespuestaFalsa(trozos))

    recibidos = []
    salida = cliente.chat_stream([{"role": "user", "content": "hola"}], on_token=recibidos.append)
    assert recibidos == trozos
    assert salida == "La capital es París."


def test_modelo_sin_descargar_da_instrucciones(monkeypatch):
    cliente = OllamaClient(host="http://localhost:99999", model="inexistente")
    monkeypatch.setattr(cliente._session, "post", lambda *a, **k: RespuestaFalsa([], status=404))
    with pytest.raises(OllamaError) as error:
        cliente.chat_stream([{"role": "user", "content": "hola"}])
    assert "ollama pull" in str(error.value)


def test_sin_ollama_el_asistente_no_se_rompe(memoria):
    """Si Ollama no está, se avisa; los comandos deben seguir funcionando."""
    with sistema_simulado() as registro:
        asistente = Assistant(memory=memoria, llm=OllamaClient(host="http://localhost:1"))
        respuesta = asistente.process("¿cuál es la capital de Francia?")
        assert not respuesta.ok
        assert "Ollama" in respuesta.text

        asistente.process("sube el volumen")
        assert "volumen-cambiar" in [c[0] for c in registro.llamadas]


def test_el_error_de_conexion_no_ensucia_la_memoria(memoria):
    """Un fallo de red no debe quedarse en el contexto del modelo."""
    with sistema_simulado():
        asistente = Assistant(memory=memoria, llm=OllamaClient(host="http://localhost:1"))
        asistente.process("¿cuál es la capital de Francia?")
        respuestas = [t for t in memoria.turns if t.role == "assistant"]
        assert not any("Ollama" in t.content for t in respuestas)
