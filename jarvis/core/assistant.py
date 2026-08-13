"""El cerebro del asistente: une memoria, comandos y modelo de lenguaje.

Flujo de cada mensaje:

    texto del usuario
        -> ¿hay una confirmacion pendiente? ("si" / "no")
        -> ¿es un comando conocido? (abrir app, volumen, apagar...)
        -> si no lo es, se lo pregunta a Ollama con el historial

Esta clase NO sabe nada de la interfaz: devuelve objetos `Response`. Asi se
puede usar tambien desde la consola (ver `main.py --consola`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from ..commands.base import CommandResult
from ..commands.registry import CommandRouter, is_affirmative, is_negative
from ..commands.reminders import ReminderManager
from ..config import config
from ..logging_setup import get_logger
from .memory import Memory
from .ollama_client import OllamaClient, OllamaError, build_system_prompt

log = get_logger("asistente")


@dataclass
class Response:
    """Respuesta del asistente lista para mostrar y para leer en voz alta."""

    text: str
    source: str = "system"          # "command" | "llm" | "system"
    ok: bool = True
    speak: bool = True
    data: dict[str, Any] = field(default_factory=dict)


class Assistant:
    def __init__(self, memory: Memory | None = None, llm: OllamaClient | None = None,
                 reminders: ReminderManager | None = None) -> None:
        self.memory = memory or Memory()
        self.llm = llm or OllamaClient()
        self.reminders = reminders or ReminderManager()
        self.router = CommandRouter(memory=self.memory, reminder_manager=self.reminders)
        self._pending: CommandResult | None = None
        self.busy = False

    # ------------------------------------------------------------------
    # Saludo inicial
    # ------------------------------------------------------------------

    def greeting(self) -> str:
        hour = datetime.now().hour
        if hour < 6:
            momento = "Buenas noches"
        elif hour < 13:
            momento = "Buenos días"
        elif hour < 21:
            momento = "Buenas tardes"
        else:
            momento = "Buenas noches"
        titulo = config.get("user_title", "Señor")
        return (f"{momento}, {titulo}. Todos los sistemas en línea. "
                "Escriba «ayuda» para ver lo que puedo hacer.")

    # ------------------------------------------------------------------
    # Procesado de un mensaje
    # ------------------------------------------------------------------

    def process(self, text: str, on_token: Callable[[str], None] | None = None) -> Response:
        text = (text or "").strip()
        if not text:
            return Response("", speak=False)

        self.busy = True
        try:
            self.memory.add_user(text)

            pending = self._resolve_pending(text)
            if pending is not None:
                self.memory.add_assistant(pending.text)
                return pending

            result = self.router.handle(text)
            log.info("Orden: %r -> %s", text,
                     "comando" if result.handled else "modelo de lenguaje")
            if result.handled:
                response = self._from_command(result)
                self.memory.add_assistant(response.text)
                return response

            return self._ask_llm(on_token)
        finally:
            self.busy = False

    # -- confirmaciones ---------------------------------------------------

    @property
    def awaiting_confirmation(self) -> bool:
        return self._pending is not None

    @property
    def pending_prompt(self) -> str:
        return self._pending.confirm_prompt if self._pending else ""

    def _resolve_pending(self, text: str) -> Response | None:
        if self._pending is None:
            return None
        pending, self._pending = self._pending, None

        if is_affirmative(text):
            action = pending.confirm_action
            assert action is not None
            result = action()
            return Response(result.message, source="command", ok=result.ok,
                            data=result.data)

        if is_negative(text):
            return Response(f"De acuerdo, he cancelado la orden de {pending.confirm_prompt}.",
                            source="command")

        # Cualquier otra cosa: se cancela por seguridad y se sigue con el mensaje.
        self._pending = None
        aviso = (f"He cancelado la orden de {pending.confirm_prompt} porque no la ha "
                 "confirmado con un sí o un no.")
        # El mensaje del usuario se procesa igualmente como una peticion nueva.
        siguiente = self.router.handle(text)
        if siguiente.handled:
            base = self._from_command(siguiente)
            return Response(f"{aviso}\n{base.text}", source=base.source, ok=base.ok,
                            data=base.data)
        return Response(aviso, source="command")

    def _from_command(self, result: CommandResult) -> Response:
        if result.needs_confirmation:
            self._pending = result
            return Response(result.message, source="command", ok=True, data=result.data)
        return Response(result.message, source="command", ok=result.ok, data=result.data)

    # -- modelo de lenguaje ----------------------------------------------

    def _ask_llm(self, on_token: Callable[[str], None] | None) -> Response:
        messages = [{"role": "system", "content": build_system_prompt(self.memory.facts_text())}]
        messages += self.memory.history(limit=config.get("memory.max_turns", 40))

        try:
            answer = self.llm.chat_stream(messages, on_token=on_token)
        except OllamaError as exc:
            log.warning("Ollama no ha respondido: %s", exc)
            # Los errores de conexion no se guardan en la memoria: solo
            # ensuciarian el contexto que se le manda al modelo despues.
            return Response(str(exc), source="llm", ok=False)

        if not answer:
            answer = "No he obtenido respuesta del modelo. ¿Puede repetir la pregunta?"
        self.memory.add_assistant(answer)
        return Response(answer, source="llm")

    def cancel_generation(self) -> None:
        self.llm.cancel()

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def llm_status(self) -> tuple[bool, str]:
        """(esta_listo, mensaje) para mostrar en la interfaz."""
        if not self.llm.is_running():
            return False, ("Ollama no responde. Abra una terminal y ejecute:  ollama serve")
        model = self.llm.resolve_model()
        if model is None:
            return False, ("Ollama está en marcha pero no hay ningún modelo descargado. "
                           f"Ejecute:  ollama pull {self.llm.model}")
        if model != self.llm.model:
            self.llm.model = model
            config.set("ollama.model", model)
            config.save()
            return True, f"Modelo en uso: {model}"
        return True, f"Modelo en uso: {model}"
