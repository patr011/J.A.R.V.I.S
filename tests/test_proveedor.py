"""Elegir cerebro: Claude o el modelo local, sin que cambie nada más."""

from __future__ import annotations

import pytest

from jarvis.config import config
from jarvis.core import llm
from jarvis.core.assistant import Assistant
from jarvis.core.memory import Memory
from jarvis.core.ollama_client import OllamaClient
from jarvis.core.prompts import build_system_prompt

from .dobles import sistema_simulado


@pytest.fixture
def con_clave(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-clave-de-prueba-0000")


# --------------------------------------------------------------------------
# El selector
# --------------------------------------------------------------------------

def test_por_defecto_usa_claude():
    config.set("llm.provider", "claude")
    assert llm.current_provider() == "claude"


def test_se_puede_elegir_ollama():
    config.set("llm.provider", "ollama")
    assert isinstance(llm.create_client(), OllamaClient)


def test_un_proveedor_desconocido_no_rompe_nada():
    config.set("llm.provider", "chatgpt-inventado")
    assert llm.current_provider() == "claude"


def test_sin_clave_no_cae_a_ollama_en_silencio(monkeypatch, tmp_path):
    """Cambiar de cerebro sin avisar dejaría al usuario preguntándose qué pasa."""
    from jarvis.core import secrets
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(secrets, "ENV_FILES", (tmp_path / "no-existe.env",))
    config.set("llm.provider", "claude")

    cliente = llm.create_client()
    assert not isinstance(cliente, OllamaClient)
    assert not cliente.ready
    assert cliente.error, "debe explicar qué falta"


# --------------------------------------------------------------------------
# Los dos clientes son intercambiables
# --------------------------------------------------------------------------

INTERFAZ = ["chat_stream", "cancel", "is_running", "resolve_model", "list_models"]


@pytest.mark.parametrize("proveedor", ["claude", "ollama"])
@pytest.mark.parametrize("metodo", INTERFAZ)
def test_los_dos_clientes_tienen_la_misma_interfaz(con_clave, proveedor, metodo):
    config.set("llm.provider", proveedor)
    cliente = llm.create_client()
    assert callable(getattr(cliente, metodo, None)), (
        f"a {proveedor} le falta {metodo}(); el asistente lo llama igual para ambos")
    assert hasattr(cliente, "model")


# --------------------------------------------------------------------------
# El prompt de sistema
# --------------------------------------------------------------------------

def test_el_prompt_de_claude_no_arrastra_las_reglas_del_modelo_local():
    """Prohibir caracteres chinos era un parche para qwen; con Claude sobra."""
    prompt = build_system_prompt(provider="claude")
    assert "chino" not in prompt.lower()
    assert "Ollama" not in prompt


def test_el_prompt_del_modelo_local_si_las_conserva():
    prompt = build_system_prompt(provider="ollama")
    assert "chino" in prompt.lower()


@pytest.mark.parametrize("proveedor", ["claude", "ollama"])
def test_los_dos_prompts_dicen_lo_que_el_modelo_no_puede_deducir(proveedor):
    """Que se lee en voz alta y que las órdenes las ejecuta el programa."""
    prompt = build_system_prompt(provider=proveedor).lower()
    assert "voz alta" in prompt
    assert "programa" in prompt


def test_los_hechos_recordados_llegan_al_prompt():
    prompt = build_system_prompt("- me gusta el café", provider="claude")
    assert "me gusta el café" in prompt


# --------------------------------------------------------------------------
# El asistente con Claude
# --------------------------------------------------------------------------

class ClienteFalso:
    """Un cerebro de mentira con la interfaz común."""

    def __init__(self, respuesta="La capital es París."):
        self.model = "claude-sonnet-5"
        self.respuesta = respuesta
        self.recibido = None
        self.error = ""
        self.ready = True

    def chat_stream(self, messages, on_token=None):
        self.recibido = messages
        if on_token:
            for palabra in self.respuesta.split(" "):
                on_token(palabra + " ")
        return self.respuesta

    def cancel(self): pass
    def is_running(self): return True
    def resolve_model(self): return self.model
    def list_models(self): return [self.model]
    def describe(self): return "Claude · Claude Sonnet 5"


def test_el_asistente_funciona_igual_con_claude():
    with sistema_simulado():
        cliente = ClienteFalso()
        asistente = Assistant(memory=Memory(), llm=cliente)
        respuesta = asistente.process("¿cuál es la capital de Francia?")
        assert respuesta.ok
        assert "París" in respuesta.text


def test_los_comandos_no_pasan_por_claude():
    """Abrir programas no debe costar dinero ni esperar a la red."""
    with sistema_simulado() as registro:
        cliente = ClienteFalso()
        Assistant(memory=Memory(), llm=cliente).process("abre Chrome")
        assert registro.primera == "app"
        assert cliente.recibido is None, "no debería haber llamado a la API"


def test_la_memoria_llega_al_modelo():
    with sistema_simulado():
        cliente = ClienteFalso()
        asistente = Assistant(memory=Memory(), llm=cliente)
        asistente.process("me llamo Patricio")
        asistente.process("¿cómo me llamo?")
        roles = [m["role"] for m in cliente.recibido]
        assert roles[0] == "system"
        assert "Patricio" in str(cliente.recibido)


def test_el_estado_del_nucleo_describe_el_cerebro_en_uso():
    with sistema_simulado():
        asistente = Assistant(memory=Memory(), llm=ClienteFalso())
        listo, mensaje = asistente.llm_status()
        assert listo and "Claude" in mensaje
