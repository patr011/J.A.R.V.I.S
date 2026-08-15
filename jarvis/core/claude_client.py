"""Conexión con la API de Claude (Anthropic).

Expone exactamente la misma interfaz que `OllamaClient` —`chat_stream`,
`cancel`, `is_running`, `resolve_model`, `list_models`, `model`— para que el
asistente pueda usar uno u otro sin enterarse de la diferencia.

Detalles de esta API que condicionan el código:

- **La clave nunca se pasa aquí.** El SDK la lee de ANTHROPIC_API_KEY; ver
  `secrets.py`.
- **Nada de `temperature` ni `top_p`.** Los modelos actuales los rechazan con
  un error 400. La creatividad se dirige con el prompt y con `effort`.
- **`max_tokens` es un tope duro** que cuenta el pensamiento *y* la respuesta.
  Como el asistente lee las respuestas en voz alta, interesa que sean cortas.
- **Se usa streaming siempre**, para que el texto aparezca palabra a palabra
  como ya hacía con Ollama.
- **El prompt de sistema no se cachea**: la caché exige un prefijo de al menos
  1024 tokens en Sonnet 5 y el nuestro no llega, así que marcarlo solo pagaría
  el recargo de escritura sin llegar a leerse nunca.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..config import config
from ..logging_setup import get_logger
from .secrets import get_api_key, has_api_key, where_to_put_the_key

log = get_logger("claude")

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:                                  # pragma: no cover
    anthropic = None                                 # type: ignore[assignment]
    ANTHROPIC_AVAILABLE = False


class ClaudeError(RuntimeError):
    """Fallo hablando con la API de Claude, ya traducido al castellano."""


# --------------------------------------------------------------------------
# Modelos y precios
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelInfo:
    id: str
    nombre: str
    entrada: float          # dólares por millón de tokens de entrada
    salida: float           # dólares por millón de tokens de salida
    nota: str


# Precios de lista por millón de tokens. Sirven para la estimación de gasto
# que se muestra en el panel; la factura real la manda Anthropic.
MODELS: dict[str, ModelInfo] = {
    "claude-sonnet-5": ModelInfo(
        "claude-sonnet-5", "Claude Sonnet 5", 3.00, 15.00,
        "El equilibrio recomendado: casi calidad de Opus a precio de Sonnet."),
    "claude-haiku-4-5": ModelInfo(
        "claude-haiku-4-5", "Claude Haiku 4.5", 1.00, 5.00,
        "El más barato y rápido. De sobra para un asistente de escritorio."),
    "claude-opus-5": ModelInfo(
        "claude-opus-5", "Claude Opus 5", 5.00, 25.00,
        "El más capaz. Sobrado para conversación, útil si le pide código."),
}

# El usuario puede escribir el identificador largo; se acepta igual.
ALIASES = {"claude-haiku-4-5-20251001": "claude-haiku-4-5"}

DEFAULT_MODEL = "claude-sonnet-5"


def model_info(model_id: str) -> ModelInfo:
    """Datos del modelo, con un valor razonable si es uno desconocido."""
    clave = ALIASES.get(model_id, model_id)
    if clave in MODELS:
        return MODELS[clave]
    return ModelInfo(model_id, model_id, 3.00, 15.00, "Modelo no catalogado.")


@dataclass
class Usage:
    """Cuánto se lleva gastado en esta sesión."""

    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    cost_usd: float = 0.0
    por_modelo: dict[str, int] = field(default_factory=dict)

    def add(self, model_id: str, entrada: int, salida: int) -> None:
        info = model_info(model_id)
        self.input_tokens += entrada
        self.output_tokens += salida
        self.requests += 1
        self.cost_usd += (entrada / 1_000_000) * info.entrada
        self.cost_usd += (salida / 1_000_000) * info.salida
        self.por_modelo[model_id] = self.por_modelo.get(model_id, 0) + 1

    def resumen(self) -> str:
        """Una linea corta: cabe en el panel lateral sin partirse en dos.

        El detalle (tokens de entrada y de salida) va en el tooltip; aqui
        solo lo que de verdad importa de un vistazo: cuanto va costando.
        """
        if not self.requests:
            return "Sin consultas todavía"
        plural = "consulta" if self.requests == 1 else "consultas"
        return f"${self.cost_usd:.4f} · {self.requests} {plural}"


# --------------------------------------------------------------------------
# Cliente
# --------------------------------------------------------------------------

class ClaudeClient:
    """Cliente de la API de Claude con la interfaz que espera el asistente."""

    def __init__(self, model: str | None = None) -> None:
        self.model = ALIASES.get(
            model or config.get("claude.model", DEFAULT_MODEL),
            model or config.get("claude.model", DEFAULT_MODEL))
        self.usage = Usage()
        self.error = ""
        self._client = None
        self._cancelled = False

        if not ANTHROPIC_AVAILABLE:
            self.error = ("Falta la librería de Anthropic. Instálela con:  "
                          "pip install anthropic")
            return
        if not has_api_key():
            self.error = where_to_put_the_key()
            return

        try:
            # Sin api_key=: el SDK lo lee de ANTHROPIC_API_KEY. Pasarlo aquí
            # invitaría a escribirlo en el código, que es justo lo que no se
            # quiere.
            self._client = anthropic.Anthropic(
                timeout=float(config.get("claude.timeout", 60)),
                max_retries=2,          # el SDK reintenta 429 y 5xx por su cuenta
            )
        except Exception as exc:                     # pragma: no cover
            self.error = f"No se pudo crear el cliente de Claude: {exc}"
            log.error("Fallo creando el cliente", exc_info=True)

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self._client is not None

    def is_running(self) -> bool:
        """¿Se puede hablar con la API? Comprueba clave, red y modelo."""
        if self._client is None:
            return False
        try:
            self._client.models.retrieve(self.model)
            return True
        except Exception as exc:
            self.error = self._traducir(exc)
            return False

    def list_models(self) -> list[str]:
        """Modelos disponibles para esta clave."""
        if self._client is None:
            return list(MODELS)
        try:
            return [m.id for m in self._client.models.list()]
        except Exception as exc:
            log.warning("No se pudo listar modelos: %s", exc)
            return list(MODELS)

    def resolve_model(self) -> str | None:
        return self.model if self._client is not None else None

    def describe(self) -> str:
        info = model_info(self.model)
        return f"Claude · {info.nombre}"

    # ------------------------------------------------------------------
    # Conversación
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        self._cancelled = True

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        """Envía la conversación y devuelve la respuesta completa.

        `messages` llega en el mismo formato que usaba Ollama, con el prompt
        de sistema como primer elemento; aquí se separa, porque en esta API
        el sistema va en su propio parámetro.
        """
        if self._client is None:
            raise ClaudeError(self.error or "El cliente de Claude no está listo.")

        self._cancelled = False
        system, turnos = self._split_system(messages)
        if not turnos:
            raise ClaudeError("No hay ningún mensaje que enviar.")

        peticion: dict = {
            "model": self.model,
            "max_tokens": int(config.get("claude.max_tokens", 1024)),
            "system": system,
            "messages": turnos,
            # Sin temperature ni top_p: los modelos actuales los rechazan.
            "output_config": {"effort": config.get("claude.effort", "low")},
        }
        # Para un asistente que responde de viva voz interesa la latencia más
        # que el razonamiento profundo, así que el pensamiento viene apagado.
        # Se puede encender desde los ajustes para preguntas difíciles.
        if not config.get("claude.thinking", False):
            peticion["thinking"] = {"type": "disabled"}
        else:
            peticion["thinking"] = {"type": "adaptive"}

        trozos: list[str] = []
        try:
            with self._client.messages.stream(**peticion) as stream:
                for texto in stream.text_stream:
                    if self._cancelled:
                        break
                    trozos.append(texto)
                    if on_token:
                        on_token(texto)
                final = stream.get_final_message()
        except Exception as exc:
            raise ClaudeError(self._traducir(exc)) from exc

        self._registrar_uso(final)

        # Las salvaguardas pueden declinar una petición: llega un 200 normal
        # con stop_reason "refusal", no una excepción. Hay que mirarlo antes
        # de leer el contenido, que puede venir vacío.
        if getattr(final, "stop_reason", None) == "refusal":
            motivo = getattr(getattr(final, "stop_details", None), "category", None)
            detalle = f" (categoría: {motivo})" if motivo else ""
            raise ClaudeError(
                f"Claude ha declinado responder a esa petición{detalle}. "
                "Pruebe a reformularla.")

        respuesta = "".join(trozos).strip()
        if not respuesta and getattr(final, "stop_reason", None) == "max_tokens":
            raise ClaudeError(
                "La respuesta se ha cortado por el límite de longitud. "
                "Suba «Longitud máxima» en los ajustes.")
        return respuesta

    def chat(self, messages: list[dict[str, str]]) -> str:
        return self.chat_stream(messages, on_token=None)

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    @staticmethod
    def _split_system(messages: list[dict[str, str]]) -> tuple[str, list[dict]]:
        """Separa el prompt de sistema y deja los turnos en orden válido.

        La API exige que el primer turno sea del usuario y que ningún mensaje
        venga vacío. La memoria del asistente puede recortarse por la mitad y
        empezar por una respuesta, así que hay que sanearla antes de enviarla.
        """
        system_parts: list[str] = []
        turnos: list[dict] = []
        for mensaje in messages:
            rol = mensaje.get("role")
            contenido = (mensaje.get("content") or "").strip()
            if not contenido:
                continue
            if rol == "system":
                system_parts.append(contenido)
            elif rol in ("user", "assistant"):
                turnos.append({"role": rol, "content": contenido})

        while turnos and turnos[0]["role"] != "user":
            turnos.pop(0)
        return "\n\n".join(system_parts), turnos

    def _registrar_uso(self, final) -> None:
        try:
            uso = getattr(final, "usage", None)
            if uso is None:
                return
            self.usage.add(
                getattr(final, "model", self.model) or self.model,
                int(getattr(uso, "input_tokens", 0) or 0),
                int(getattr(uso, "output_tokens", 0) or 0),
            )
            log.info("Consulta a %s: %s tokens dentro, %s fuera (total $%.4f)",
                     self.model, uso.input_tokens, uso.output_tokens,
                     self.usage.cost_usd)
        except Exception:                            # pragma: no cover
            log.debug("No se pudo registrar el uso", exc_info=True)

    def _traducir(self, exc: Exception) -> str:
        """Convierte los errores del SDK en algo que el usuario entienda.

        Se distingue cada tipo en lugar de capturar uno genérico: lo que hay
        que hacer con un 401 (revisar la clave) no se parece en nada a lo que
        hay que hacer con un 429 (esperar).
        """
        if not ANTHROPIC_AVAILABLE:
            return "La librería de Anthropic no está instalada."

        if isinstance(exc, anthropic.AuthenticationError):
            return ("La clave de la API no es válida o ha caducado. "
                    "Revísela en https://console.anthropic.com/settings/keys")
        if isinstance(exc, anthropic.PermissionDeniedError):
            return ("Su clave no tiene permiso para usar este modelo. "
                    "Puede que necesite añadir crédito a la cuenta.")
        if isinstance(exc, anthropic.NotFoundError):
            disponibles = ", ".join(sorted(MODELS))
            return (f"El modelo «{self.model}» no existe o no está disponible "
                    f"para su cuenta.\nModelos habituales: {disponibles}")
        if isinstance(exc, anthropic.RateLimitError):
            return ("Ha superado el límite de peticiones por minuto. "
                    "Espere unos segundos y vuelva a intentarlo.")
        if isinstance(exc, anthropic.BadRequestError):
            mensaje = getattr(exc, "message", str(exc))
            if "credit" in mensaje.lower() or "balance" in mensaje.lower():
                return ("La cuenta se ha quedado sin crédito. Añada saldo en "
                        "https://console.anthropic.com/settings/billing")
            return f"La petición no era válida: {mensaje}"
        if isinstance(exc, anthropic.APIConnectionError):
            return ("No hay conexión con la API de Claude. Compruebe su "
                    "conexión a internet.")
        if isinstance(exc, anthropic.APIStatusError):
            codigo = getattr(exc, "status_code", "?")
            if isinstance(codigo, int) and codigo >= 500:
                return (f"La API de Claude está teniendo problemas (error {codigo}). "
                        "Inténtelo dentro de un momento.")
            return f"Error de la API de Claude ({codigo}): {getattr(exc, 'message', exc)}"
        return f"Error inesperado hablando con Claude: {exc}"
