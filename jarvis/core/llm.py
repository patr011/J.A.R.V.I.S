"""Elección del cerebro: la API de Claude o un modelo local con Ollama.

Los dos clientes exponen la misma interfaz (`chat_stream`, `cancel`,
`is_running`, `resolve_model`, `list_models`, `model`), así que el asistente
usa uno u otro sin enterarse. Se elige en los ajustes o en el config.json:

    "llm": { "provider": "claude" }     ← la API de Claude (por defecto)
    "llm": { "provider": "ollama" }     ← modelo local, gratis y sin internet
"""

from __future__ import annotations

from ..config import config
from ..logging_setup import get_logger
from .claude_client import ClaudeClient, ClaudeError
from .ollama_client import OllamaClient, OllamaError

log = get_logger("llm")

PROVIDERS = {
    "claude": "API de Claude (Anthropic)",
    "ollama": "Modelo local con Ollama",
}

# Errores de cualquiera de los dos, para poder capturarlos de una vez.
LLMError = (ClaudeError, OllamaError)


def current_provider() -> str:
    proveedor = str(config.get("llm.provider", "claude")).lower().strip()
    return proveedor if proveedor in PROVIDERS else "claude"


def create_client(provider: str | None = None):
    """Crea el cliente del proveedor elegido.

    Si se pide Claude pero no hay clave ni librería, se avisa en el log y se
    devuelve el cliente igualmente: su `error` explica qué falta, y la ventana
    lo enseña. Es mejor que caer a Ollama en silencio y dejar al usuario
    preguntándose por qué responde otro modelo.
    """
    provider = (provider or current_provider()).lower()

    if provider == "ollama":
        return OllamaClient()

    cliente = ClaudeClient()
    if not cliente.ready:
        log.warning("Claude no está listo: %s", cliente.error)
    return cliente


def describe(client) -> str:
    """Texto corto para el panel: qué cerebro está en uso."""
    if hasattr(client, "describe"):
        return client.describe()
    return f"Ollama · {getattr(client, 'model', '?')}"
