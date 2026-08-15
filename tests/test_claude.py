"""El cliente de la API de Claude.

Ninguna prueba llama a la API de verdad: se simula el SDK. Así funcionan sin
clave, sin internet y sin gastar ni un céntimo.
"""

from __future__ import annotations

import pytest

anthropic = pytest.importorskip("anthropic", reason="La librería anthropic no está instalada")

from jarvis.core import claude_client, secrets            # noqa: E402
from jarvis.core.claude_client import ClaudeClient, ClaudeError, Usage, model_info  # noqa: E402


# --------------------------------------------------------------------------
# Dobles del SDK
# --------------------------------------------------------------------------

class UsoFalso:
    def __init__(self, entrada=100, salida=50):
        self.input_tokens = entrada
        self.output_tokens = salida


class MensajeFalso:
    def __init__(self, stop_reason="end_turn", uso=None, modelo="claude-sonnet-5",
                 stop_details=None):
        self.stop_reason = stop_reason
        self.usage = uso or UsoFalso()
        self.model = modelo
        self.stop_details = stop_details


class StreamFalso:
    """Imita el gestor de contexto que devuelve messages.stream()."""

    def __init__(self, trozos, final=None):
        self._trozos = trozos
        self._final = final or MensajeFalso()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def text_stream(self):
        return iter(self._trozos)

    def get_final_message(self):
        return self._final


class MensajesFalsos:
    def __init__(self, stream):
        self._stream = stream
        self.ultima_peticion = None

    def stream(self, **kwargs):
        self.ultima_peticion = kwargs
        if isinstance(self._stream, Exception):
            raise self._stream
        return self._stream


class SDKFalso:
    def __init__(self, stream=None):
        self.messages = MensajesFalsos(stream or StreamFalso(["hola"]))
        self.models = ModelosFalsos()


class ModelosFalsos:
    def __init__(self, error=None):
        self.error = error

    def retrieve(self, model_id):
        if self.error:
            raise self.error
        return type("M", (), {"id": model_id})()

    def list(self):
        return [type("M", (), {"id": m})() for m in
                ("claude-sonnet-5", "claude-haiku-4-5", "claude-opus-5")]


@pytest.fixture
def con_clave(monkeypatch):
    """Simula que hay una clave configurada, sin usar una de verdad."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-clave-de-prueba-0000")


@pytest.fixture
def cliente(con_clave, monkeypatch):
    """Cliente con el SDK sustituido por un doble."""
    sdk = SDKFalso(StreamFalso(["Hola", ", ", "señor."]))
    monkeypatch.setattr(claude_client.anthropic, "Anthropic", lambda **kw: sdk)
    c = ClaudeClient(model="claude-sonnet-5")
    c._sdk_falso = sdk
    return c


# --------------------------------------------------------------------------
# La clave nunca se escribe en el código
# --------------------------------------------------------------------------

def test_la_clave_se_lee_del_entorno(con_clave):
    assert secrets.get_api_key() == "sk-ant-clave-de-prueba-0000"
    assert secrets.has_api_key()


def test_sin_clave_lo_dice_y_explica_donde_ponerla(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(secrets, "ENV_FILES", (tmp_path / "no-existe.env",))
    assert not secrets.has_api_key()

    cliente = ClaudeClient()
    assert not cliente.ready
    assert "ANTHROPIC_API_KEY" in cliente.error
    assert ".env" in cliente.error


def test_la_clave_se_lee_de_un_archivo_env(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fichero = tmp_path / ".env"
    fichero.write_text('# comentario\nexport ANTHROPIC_API_KEY="sk-ant-desde-fichero"\n',
                       encoding="utf-8")
    monkeypatch.setattr(secrets, "ENV_FILES", (fichero,))
    assert secrets.get_api_key() == "sk-ant-desde-fichero"


def test_el_entorno_gana_al_archivo(monkeypatch, tmp_path):
    """Poder lanzarlo con otra clave sin editar ficheros."""
    fichero = tmp_path / ".env"
    fichero.write_text("ANTHROPIC_API_KEY=sk-ant-del-fichero\n", encoding="utf-8")
    monkeypatch.setattr(secrets, "ENV_FILES", (fichero,))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-del-entorno")
    assert secrets.get_api_key() == "sk-ant-del-entorno"


def test_la_clave_nunca_se_muestra_entera(con_clave):
    enmascarada = secrets.mask_api_key()
    assert "sk-ant-clave-de-prueba-0000" not in enmascarada
    assert enmascarada.endswith("0000")
    assert "…" in enmascarada


def test_la_clave_no_aparece_en_el_codigo_fuente():
    """Ninguna clave literal debe haberse colado en el repositorio."""
    import re
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    patron = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")
    for ruta in list(raiz.rglob("*.py")) + list(raiz.rglob("*.md")) + list(raiz.rglob("*.json")):
        if ".venv" in ruta.parts or "tests" in ruta.parts:
            continue
        texto = ruta.read_text(encoding="utf-8", errors="ignore")
        assert not patron.search(texto), f"¡Posible clave escrita en {ruta}!"


# --------------------------------------------------------------------------
# Conversación
# --------------------------------------------------------------------------

def test_responde_en_streaming(cliente):
    recibidos = []
    salida = cliente.chat_stream(
        [{"role": "system", "content": "eres jarvis"},
         {"role": "user", "content": "hola"}],
        on_token=recibidos.append)
    assert recibidos == ["Hola", ", ", "señor."]
    assert salida == "Hola, señor."


def test_el_prompt_de_sistema_va_en_su_parametro(cliente):
    """En esta API el sistema no es un mensaje más: va aparte."""
    cliente.chat_stream([{"role": "system", "content": "eres jarvis"},
                         {"role": "user", "content": "hola"}])
    peticion = cliente._sdk_falso.messages.ultima_peticion
    assert peticion["system"] == "eres jarvis"
    assert peticion["messages"] == [{"role": "user", "content": "hola"}]


def test_no_envia_temperature_ni_top_p(cliente):
    """Los modelos actuales devuelven error 400 si se les manda."""
    cliente.chat_stream([{"role": "user", "content": "hola"}])
    peticion = cliente._sdk_falso.messages.ultima_peticion
    for prohibido in ("temperature", "top_p", "top_k"):
        assert prohibido not in peticion, f"«{prohibido}» haría fallar la petición"


def test_la_conversacion_siempre_empieza_por_el_usuario(cliente):
    """La memoria puede recortarse y empezar por una respuesta; hay que sanearla."""
    cliente.chat_stream([
        {"role": "assistant", "content": "…lo que decía antes"},
        {"role": "user", "content": "sigue"},
    ])
    turnos = cliente._sdk_falso.messages.ultima_peticion["messages"]
    assert turnos[0]["role"] == "user"


def test_descarta_los_mensajes_vacios(cliente):
    cliente.chat_stream([
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "   "},
        {"role": "user", "content": "sigues ahí"},
    ])
    turnos = cliente._sdk_falso.messages.ultima_peticion["messages"]
    assert all(t["content"].strip() for t in turnos)


def test_se_puede_cancelar_a_media_respuesta(con_clave, monkeypatch):
    sdk = SDKFalso(StreamFalso(["uno ", "dos ", "tres ", "cuatro"]))
    monkeypatch.setattr(claude_client.anthropic, "Anthropic", lambda **kw: sdk)
    cliente = ClaudeClient()

    recibidos = []

    def parar(token):
        recibidos.append(token)
        if len(recibidos) == 2:
            cliente.cancel()

    cliente.chat_stream([{"role": "user", "content": "cuenta"}], on_token=parar)
    assert len(recibidos) == 2, "debería haberse detenido al cancelar"


def test_una_negativa_no_se_lee_como_respuesta_vacia(con_clave, monkeypatch):
    """Una petición declinada llega como un 200 normal, no como excepción."""
    final = MensajeFalso(stop_reason="refusal",
                         stop_details=type("D", (), {"category": "cyber"})())
    sdk = SDKFalso(StreamFalso([], final=final))
    monkeypatch.setattr(claude_client.anthropic, "Anthropic", lambda **kw: sdk)

    with pytest.raises(ClaudeError) as error:
        ClaudeClient().chat_stream([{"role": "user", "content": "…"}])
    assert "declinado" in str(error.value)
    assert "cyber" in str(error.value)


def test_respuesta_cortada_por_longitud(con_clave, monkeypatch):
    final = MensajeFalso(stop_reason="max_tokens")
    sdk = SDKFalso(StreamFalso([], final=final))
    monkeypatch.setattr(claude_client.anthropic, "Anthropic", lambda **kw: sdk)

    with pytest.raises(ClaudeError) as error:
        ClaudeClient().chat_stream([{"role": "user", "content": "…"}])
    assert "Longitud máxima" in str(error.value)


# --------------------------------------------------------------------------
# Errores: cada uno con su solución
# --------------------------------------------------------------------------

def _respuesta_http(status):
    import httpx
    return httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com"))


ERRORES = [
    (lambda: anthropic.AuthenticationError("no", response=_respuesta_http(401), body=None),
     "clave"),
    (lambda: anthropic.RateLimitError("no", response=_respuesta_http(429), body=None),
     "límite"),
    (lambda: anthropic.NotFoundError("no", response=_respuesta_http(404), body=None),
     "no existe"),
    (lambda: anthropic.PermissionDeniedError("no", response=_respuesta_http(403), body=None),
     "permiso"),
    (lambda: anthropic.APIConnectionError(request=None), "conexión"),
]


@pytest.mark.parametrize("crear_error,esperado", ERRORES)
def test_cada_error_explica_que_hacer(con_clave, monkeypatch, crear_error, esperado):
    sdk = SDKFalso(crear_error())
    monkeypatch.setattr(claude_client.anthropic, "Anthropic", lambda **kw: sdk)

    with pytest.raises(ClaudeError) as error:
        ClaudeClient().chat_stream([{"role": "user", "content": "hola"}])
    assert esperado in str(error.value).lower()


def test_sin_credito_dice_donde_recargar(con_clave, monkeypatch):
    error = anthropic.BadRequestError(
        "Your credit balance is too low", response=_respuesta_http(400), body=None)
    sdk = SDKFalso(error)
    monkeypatch.setattr(claude_client.anthropic, "Anthropic", lambda **kw: sdk)

    with pytest.raises(ClaudeError) as fallo:
        ClaudeClient().chat_stream([{"role": "user", "content": "hola"}])
    assert "crédito" in str(fallo.value)
    assert "billing" in str(fallo.value)


# --------------------------------------------------------------------------
# Gasto
# --------------------------------------------------------------------------

def test_cuenta_los_tokens_y_estima_el_gasto(cliente):
    cliente.chat_stream([{"role": "user", "content": "hola"}])
    assert cliente.usage.requests == 1
    assert cliente.usage.input_tokens == 100
    assert cliente.usage.output_tokens == 50
    assert cliente.usage.cost_usd > 0


def test_el_calculo_del_gasto_es_correcto():
    uso = Usage()
    # Sonnet 5: $3 por millón de entrada, $15 por millón de salida.
    uso.add("claude-sonnet-5", 1_000_000, 1_000_000)
    assert uso.cost_usd == pytest.approx(18.0)


def test_haiku_es_mas_barato_que_sonnet():
    assert model_info("claude-haiku-4-5").entrada < model_info("claude-sonnet-5").entrada


def test_el_identificador_largo_de_haiku_tambien_vale():
    assert model_info("claude-haiku-4-5-20251001").nombre == "Claude Haiku 4.5"


def test_el_resumen_de_gasto_se_lee_bien(cliente):
    assert "Sin consultas" in cliente.usage.resumen()
    cliente.chat_stream([{"role": "user", "content": "hola"}])
    resumen = cliente.usage.resumen()
    assert "1 consulta" in resumen and "$" in resumen
