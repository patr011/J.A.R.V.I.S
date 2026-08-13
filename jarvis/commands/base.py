"""Tipos comunes a todos los comandos."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CommandResult:
    """Lo que devuelve un comando al asistente.

    - `handled=False` significa "esto no era un comando para mi": el
      asistente se lo pasara entonces al modelo de lenguaje.
    - Si `confirm_action` no es None, el comando NO se ha ejecutado todavia:
      se esta pidiendo confirmacion al usuario. El asistente guardara la
      accion y la ejecutara si el usuario responde que si.
    """

    message: str = ""
    ok: bool = True
    handled: bool = True
    confirm_action: Callable[[], "CommandResult"] | None = None
    confirm_prompt: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_confirmation(self) -> bool:
        return self.confirm_action is not None

    # Atajos para escribir menos en los comandos.
    @staticmethod
    def unhandled() -> "CommandResult":
        return CommandResult(handled=False)

    @staticmethod
    def fail(message: str) -> "CommandResult":
        return CommandResult(message=message, ok=False)

    @staticmethod
    def done(message: str, **data: Any) -> "CommandResult":
        return CommandResult(message=message, ok=True, data=data)


def normalize(text: str) -> str:
    """Minusculas y sin acentos, para comparar lo que dice el usuario.

    'Ábreme el Explorador' -> 'abreme el explorador'
    """
    text = text.strip().lower()
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    # La ñ si se conserva: 'año' -> 'año'
    return unicodedata.normalize("NFC", stripped)


# Palabras que se quitan del nombre de una app/archivo pedido por el usuario.
FILLER_WORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "mi", "mis", "por", "favor", "porfavor",
    "programa", "aplicacion", "app", "the", "please", "me",
}


def strip_filler(text: str) -> str:
    """Quita muletillas del objetivo de un comando."""
    words = [w for w in normalize(text).split() if w not in FILLER_WORDS]
    return " ".join(words).strip(" .,;:!?")
