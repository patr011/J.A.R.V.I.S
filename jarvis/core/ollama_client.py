"""Conexion con Ollama (modelo de lenguaje local, sin API de pago).

Ollama expone un servidor HTTP en http://localhost:11434.
Aqui usamos tres endpoints:

    GET  /api/tags      -> modelos que tienes descargados
    POST /api/chat      -> conversacion con historial (soporta streaming)
    POST /api/pull      -> descargar un modelo

Todo esta pensado para llamarse desde un hilo de trabajo, nunca desde el
hilo de la interfaz: las peticiones pueden tardar varios segundos.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Iterator

import requests

from ..config import config
from ..logging_setup import get_logger
# El prompt vive en prompts.py (lo comparten los dos proveedores);
# se reexporta aqui para no romper lo que ya lo importaba de este modulo.
from .prompts import build_system_prompt  # noqa: F401

log = get_logger("ollama")

# --------------------------------------------------------------------------
# Recomendacion de modelo segun el hardware
# --------------------------------------------------------------------------


@dataclass
class ModelSuggestion:
    name: str
    size: str
    reason: str
    command: str


#  RAM minima (GB) -> modelo recomendado
#
#  Ojo con los umbrales: Windows nunca reporta la cifra redonda. Un equipo de
#  16 GB suele declarar unos 15,7 GB porque el hardware se reserva una parte,
#  y uno de 8 GB ronda los 7,8 GB. Por eso los limites son 30 / 15 / 7 y no
#  32 / 16 / 8: con los redondos, cada equipo caeria en el escalon de abajo.
MODEL_TIERS: list[tuple[float, ModelSuggestion]] = [
    (30, ModelSuggestion(
        "llama3.1:8b", "~4.7 GB",
        "Tu equipo es potente: este modelo responde muy bien y sigue instrucciones con precision.",
        "ollama pull llama3.1:8b")),
    (15, ModelSuggestion(
        "llama3.1:8b", "~4.7 GB",
        "Con 16 GB de RAM este modelo va comodo y da respuestas de buena calidad.",
        "ollama pull llama3.1:8b")),
    (7, ModelSuggestion(
        "llama3.2:3b", "~2.0 GB",
        "Equilibrio ideal entre 8 y 16 GB de RAM: rapido y suficientemente inteligente.",
        "ollama pull llama3.2:3b")),
    (0, ModelSuggestion(
        "llama3.2:1b", "~1.3 GB",
        "Equipo modesto: este modelo es pequeño y arranca rapido aunque sea menos preciso.",
        "ollama pull llama3.2:1b")),
]

# Se recomienda Llama 3.1 y no Qwen aunque Qwen puntue mas alto en las
# comparativas: Qwen intercala caracteres chinos al escribir en español,
# y en un asistente que ademas lee en voz alta eso es inaceptable.
GPU_SUGGESTION = ModelSuggestion(
    "llama3.1:8b", "~4.7 GB",
    "Tienes GPU dedicada: el modelo cabe entero en la VRAM y las respuestas salen casi al instante.",
    "ollama pull llama3.1:8b")


def detect_hardware() -> dict[str, object]:
    """Devuelve RAM, nucleos y (si se puede) la GPU detectada."""
    info: dict[str, object] = {"ram_gb": 0.0, "cores": 0, "gpu": "", "vram_gb": 0.0}
    try:
        import psutil
        info["ram_gb"] = round(psutil.virtual_memory().total / (1024 ** 3), 1)
        info["cores"] = psutil.cpu_count(logical=True) or 0
    except Exception:
        pass

    # Deteccion de GPU en Windows via WMI (no requiere instalar nada extra).
    try:
        import subprocess
        import sys
        if sys.platform == "win32":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_VideoController | "
                 "Select-Object -First 1 -Property Name,AdapterRAM | ConvertTo-Json"],
                capture_output=True, text=True, timeout=12,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if out.returncode == 0 and out.stdout.strip():
                data = json.loads(out.stdout)
                if isinstance(data, list):
                    data = data[0]
                info["gpu"] = data.get("Name", "") or ""
                vram = data.get("AdapterRAM") or 0
                # AdapterRAM se desborda en tarjetas > 4 GB; solo es orientativo.
                if isinstance(vram, (int, float)) and vram > 0:
                    info["vram_gb"] = round(float(vram) / (1024 ** 3), 1)
    except Exception:
        pass
    return info


def suggest_model() -> tuple[ModelSuggestion, dict[str, object]]:
    """Elige el modelo mas adecuado para este equipo."""
    hw = detect_hardware()
    ram = float(hw.get("ram_gb") or 0)
    gpu = str(hw.get("gpu") or "").lower()

    dedicated = any(k in gpu for k in ("nvidia", "geforce", "rtx", "gtx", "radeon rx", "arc"))
    if dedicated and ram >= 15:
        return GPU_SUGGESTION, hw

    for min_ram, suggestion in MODEL_TIERS:
        if ram >= min_ram:
            return suggestion, hw
    return MODEL_TIERS[-1][1], hw


# --------------------------------------------------------------------------
# Cliente
# --------------------------------------------------------------------------

class OllamaError(RuntimeError):
    """Fallo hablando con el servidor de Ollama."""


class OllamaClient:
    """Cliente minimo y sincrono para la API de Ollama."""

    def __init__(self, host: str | None = None, model: str | None = None) -> None:
        self.host = (host or config.get("ollama.host", "http://localhost:11434")).rstrip("/")
        self.model = model or config.get("ollama.model", "llama3.2:3b")
        self.timeout = config.get("ollama.timeout", 120)
        self._session = requests.Session()
        self._cancelled = False

    # -- estado ---------------------------------------------------------

    def is_running(self) -> bool:
        """¿Esta el servidor de Ollama encendido?"""
        try:
            r = self._session.get(f"{self.host}/api/tags", timeout=3)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def start_server(self) -> tuple[bool, str]:
        """Intenta arrancar Ollama si esta instalado pero parado.

        Es lo primero que haria el usuario a mano, asi que se hace por el.
        """
        import shutil
        import subprocess
        import sys
        import time

        if self.is_running():
            return True, "Ollama ya estaba en marcha."
        if shutil.which("ollama") is None:
            return False, ("Ollama no está instalado. Descárguelo de "
                           "https://ollama.com/download")
        try:
            kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            if sys.platform == "win32":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(["ollama", "serve"], **kwargs)
        except (OSError, ValueError) as exc:
            return False, f"No he podido arrancar Ollama: {exc}"

        # El servidor tarda un par de segundos en aceptar conexiones.
        for _ in range(12):
            time.sleep(0.5)
            if self.is_running():
                return True, "He arrancado Ollama."
        return False, "He lanzado Ollama pero todavía no responde. Inténtelo en unos segundos."

    def list_models(self) -> list[str]:
        """Modelos descargados en este equipo."""
        try:
            r = self._session.get(f"{self.host}/api/tags", timeout=10)
            r.raise_for_status()
            return [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]
        except (requests.RequestException, ValueError) as exc:
            raise OllamaError(f"No se pudo obtener la lista de modelos: {exc}") from exc

    def has_model(self, name: str | None = None) -> bool:
        name = name or self.model
        try:
            models = self.list_models()
        except OllamaError:
            return False
        # "llama3.2:3b" debe coincidir tambien con "llama3.2:3b" listado tal cual,
        # y "llama3.2" con "llama3.2:latest".
        base = name.split(":")[0]
        return any(m == name or m.split(":")[0] == base for m in models)

    def resolve_model(self) -> str | None:
        """Devuelve un modelo utilizable: el configurado, o el primero disponible."""
        try:
            models = self.list_models()
        except OllamaError:
            return None
        if not models:
            return None
        base = self.model.split(":")[0]
        for m in models:
            if m == self.model or m.split(":")[0] == base:
                return m
        return models[0]

    # -- generacion -----------------------------------------------------

    def cancel(self) -> None:
        """Pide detener la respuesta que se esta generando."""
        self._cancelled = True

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        on_token: Callable[[str], None] | None = None,
        retrying: bool = False,
    ) -> str:
        """Envia la conversacion y devuelve la respuesta completa.

        Si se pasa `on_token`, se llama con cada fragmento segun llega, para
        poder pintar la respuesta en pantalla mientras se genera.
        """
        self._cancelled = False
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": config.get("ollama.keep_alive", "10m"),
            "options": {
                "temperature": config.get("ollama.temperature", 0.7),
                "num_ctx": config.get("ollama.num_ctx", 4096),
            },
        }

        chunks: list[str] = []
        try:
            with self._session.post(
                f"{self.host}/api/chat",
                json=payload,
                stream=True,
                timeout=(10, self.timeout),
            ) as response:
                if response.status_code == 404:
                    # Decir cuales SI hay ahorra al usuario ir a mirarlo.
                    try:
                        disponibles = self.list_models()
                    except OllamaError:
                        disponibles = []
                    alternativa = (f"\nModelos que sí tiene: {', '.join(disponibles)}."
                                   if disponibles else "")
                    raise OllamaError(
                        f"El modelo «{self.model}» no está descargado. "
                        f"Abre una terminal y ejecuta:  ollama pull {self.model}"
                        + alternativa
                    )
                response.raise_for_status()

                for line in response.iter_lines(decode_unicode=True):
                    if self._cancelled:
                        break
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "error" in data:
                        raise OllamaError(str(data["error"]))
                    piece = (data.get("message") or {}).get("content", "")
                    if piece:
                        chunks.append(piece)
                        if on_token:
                            on_token(piece)
                    if data.get("done"):
                        break
        except requests.ConnectionError as exc:
            # Ollama se apaga solo tras un rato sin uso, y tambien puede
            # haberse reiniciado. Antes de dar error, se intenta levantarlo
            # y repetir la peticion una vez: para el usuario es transparente.
            if not retrying:
                arrancado, _ = self.start_server()
                if arrancado:
                    return self.chat_stream(messages, on_token=on_token, retrying=True)
            raise OllamaError(
                "No puedo conectar con Ollama. Comprueba que esté instalado y "
                "en marcha (abre una terminal y escribe:  ollama serve )."
            ) from exc
        except requests.Timeout as exc:
            raise OllamaError(
                "Ollama ha tardado demasiado en responder. Prueba con un modelo "
                "mas pequeño, por ejemplo llama3.2:1b."
            ) from exc
        except requests.RequestException as exc:
            raise OllamaError(f"Error hablando con Ollama: {exc}") from exc

        return "".join(chunks).strip()

    def chat(self, messages: list[dict[str, str]]) -> str:
        return self.chat_stream(messages, on_token=None)

    # -- descarga de modelos --------------------------------------------

    def pull_model(self, name: str, on_progress: Callable[[str], None] | None = None) -> Iterator[str]:
        """Descarga un modelo. Va devolviendo el estado de la descarga."""
        try:
            with self._session.post(
                f"{self.host}/api/pull",
                json={"model": name, "stream": True},
                stream=True,
                timeout=(10, 3600),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    status = data.get("status", "")
                    if data.get("total") and data.get("completed"):
                        pct = 100 * data["completed"] / data["total"]
                        status = f"{status} — {pct:.0f}%"
                    if on_progress:
                        on_progress(status)
                    yield status
        except requests.RequestException as exc:
            raise OllamaError(f"No se pudo descargar «{name}»: {exc}") from exc


