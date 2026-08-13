"""Memoria de la conversacion.

Dos niveles:

1. Memoria de sesion (`turns`): todo lo que se dijo desde que abriste el
   programa. Es lo que se manda a Ollama para que el modelo tenga contexto
   y pueda "recordar" lo que le dijiste hace unos minutos.

2. Hechos permanentes (`facts`): cosas que le pides recordar explicitamente
   ("recuerda que mi cumpleaños es el 3 de mayo"). Se guardan en disco en
   ~/.jarvis/memory.json y sobreviven al cierre del programa.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import HOME_DIR, config

MEMORY_FILE = HOME_DIR / "memory.json"


@dataclass
class Turn:
    """Un mensaje de la conversacion."""

    role: str                     # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def as_message(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}

    def clock(self) -> str:
        return self.timestamp.strftime("%H:%M:%S")


class Memory:
    """Historial de la sesion + hechos persistentes. Seguro entre hilos."""

    def __init__(self, max_turns: int | None = None) -> None:
        self._lock = threading.RLock()
        self.max_turns: int = max_turns or config.get("memory.max_turns", 40)
        self.turns: list[Turn] = []
        self.facts: list[str] = []
        self.started_at = datetime.now()
        self._load_facts()

    # ------------------------------------------------------------------
    # Conversacion de la sesion
    # ------------------------------------------------------------------

    def add(self, role: str, content: str) -> Turn:
        turn = Turn(role=role, content=content)
        with self._lock:
            self.turns.append(turn)
            # Recorta el historial pero conserva siempre los mas recientes.
            if len(self.turns) > self.max_turns:
                self.turns = self.turns[-self.max_turns:]
        return turn

    def add_user(self, content: str) -> Turn:
        return self.add("user", content)

    def add_assistant(self, content: str) -> Turn:
        return self.add("assistant", content)

    def history(self, limit: int | None = None) -> list[dict[str, str]]:
        """Historial en el formato que espera la API de chat de Ollama."""
        with self._lock:
            turns = self.turns[-limit:] if limit else list(self.turns)
        return [t.as_message() for t in turns]

    def last_user_message(self) -> str | None:
        with self._lock:
            for turn in reversed(self.turns):
                if turn.role == "user":
                    return turn.content
        return None

    def recent_text(self, count: int = 6) -> str:
        """Resumen legible de los ultimos turnos (para responder '¿que te dije?')."""
        with self._lock:
            turns = [t for t in self.turns if t.role in ("user", "assistant")][-count:]
        if not turns:
            return ""
        etiquetas = {"user": "Tu", "assistant": "Yo"}
        return "\n".join(f"[{t.clock()}] {etiquetas[t.role]}: {t.content}" for t in turns)

    def clear(self) -> None:
        """Borra la conversacion de la sesion (no los hechos permanentes)."""
        with self._lock:
            self.turns.clear()
            self.started_at = datetime.now()

    def stats(self) -> dict[str, int | str]:
        with self._lock:
            users = sum(1 for t in self.turns if t.role == "user")
            elapsed = datetime.now() - self.started_at
            minutes = int(elapsed.total_seconds() // 60)
            return {
                "turnos": len(self.turns),
                "preguntas": users,
                "hechos": len(self.facts),
                "sesion": f"{minutes} min",
            }

    # ------------------------------------------------------------------
    # Hechos permanentes
    # ------------------------------------------------------------------

    def remember(self, fact: str) -> str:
        fact = fact.strip(" .,")
        if not fact:
            return "No he entendido qué debo recordar."
        with self._lock:
            if fact.lower() in (f.lower() for f in self.facts):
                return f"Ya lo tenía anotado: {fact}."
            self.facts.append(fact)
        self._save_facts()
        return f"Anotado: {fact}."

    def forget(self, needle: str = "") -> str:
        needle = needle.strip().lower()
        with self._lock:
            if not needle or needle in ("todo", "todas", "all"):
                count = len(self.facts)
                self.facts.clear()
                self._save_facts()
                return f"He borrado {count} nota(s) de mi memoria permanente."
            keep = [f for f in self.facts if needle not in f.lower()]
            removed = len(self.facts) - len(keep)
            self.facts = keep
        self._save_facts()
        if removed:
            return f"He olvidado {removed} nota(s) sobre «{needle}»."
        return f"No tenía nada anotado sobre «{needle}»."

    def facts_text(self) -> str:
        with self._lock:
            if not self.facts:
                return ""
            return "\n".join(f"- {f}" for f in self.facts)

    # ------------------------------------------------------------------
    # Disco
    # ------------------------------------------------------------------

    def _load_facts(self) -> None:
        if not config.get("memory.persist_facts", True):
            return
        try:
            if MEMORY_FILE.exists():
                with open(MEMORY_FILE, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                loaded = data.get("facts", [])
                if isinstance(loaded, list):
                    self.facts = [str(f) for f in loaded]
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[memoria] No se pudo cargar {MEMORY_FILE}: {exc}")

    def _save_facts(self) -> None:
        if not config.get("memory.persist_facts", True):
            return
        try:
            HOME_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"facts": self.facts, "updated": datetime.now().isoformat()}
            tmp = Path(str(MEMORY_FILE) + ".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, MEMORY_FILE)
        except OSError as exc:
            print(f"[memoria] No se pudo guardar {MEMORY_FILE}: {exc}")
