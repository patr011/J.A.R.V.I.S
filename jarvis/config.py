"""Configuracion global de J.A.R.V.I.S.

La configuracion se guarda en  C:\\Users\\<tu_usuario>\\.jarvis\\config.json
La primera vez que ejecutes el programa el archivo se crea solo con los
valores por defecto que estan aqui abajo. Puedes editarlo con el Bloc de
notas para cambiar el modelo de Ollama, la voz, los atajos, etc.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Rutas
# --------------------------------------------------------------------------

HOME_DIR = Path.home() / ".jarvis"
CONFIG_FILE = HOME_DIR / "config.json"
LOG_FILE = HOME_DIR / "jarvis.log"

# --------------------------------------------------------------------------
# Valores por defecto
# --------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    # ---- Identidad ----
    "assistant_name": "JARVIS",
    "user_title": "Señor",          # como te llama el asistente
    "language": "es",                # "es" o "en"

    # ---- Ollama ----
    "ollama": {
        "host": "http://localhost:11434",
        "model": "llama3.2:3b",      # se ajusta solo en el primer arranque
        "temperature": 0.7,
        "num_ctx": 4096,
        "timeout": 120,
        "keep_alive": "10m",
        "auto_pick_model": True,     # elegir modelo segun el hardware
    },

    # ---- Voz ----
    "voice": {
        "tts_enabled": True,
        "rate": 180,                 # palabras por minuto
        "volume": 1.0,               # 0.0 - 1.0
        "voice_id": "",              # vacio = voz del sistema en tu idioma
        "stt_enabled": True,
        "stt_language": "es-ES",
        "energy_threshold": 300,
        "pause_threshold": 0.8,
        "phrase_time_limit": 12,
        "wake_word": "jarvis",       # solo se usa en modo escucha continua
        "require_wake_word": False,
    },

    # ---- Memoria ----
    "memory": {
        "max_turns": 40,             # turnos de conversacion en memoria
        "persist_facts": True,       # guardar "recuerda que..." en disco
    },

    # ---- Interfaz ----
    "ui": {
        "accent": "#00E5FF",
        "accent_dim": "#0097B2",
        "warn": "#FFB000",
        "danger": "#FF3B3B",
        "background": "#05080D",
        "panel": "#0A121A",
        "text": "#CFEFF7",
        "font_family": "Consolas",
        "font_size": 11,
        "animations": True,
        "start_maximized": False,
    },

    # ---- Comandos ----
    "commands": {
        "confirm_dangerous": True,   # pedir confirmacion para apagar/reiniciar
        "shutdown_delay": 15,        # segundos antes de apagar (da tiempo a cancelar)
        "search_paths": [],          # vacio = Escritorio, Documentos, Descargas...
        "max_search_results": 8,
        "search_timeout": 12,        # segundos maximos buscando archivos
    },

    # ---- Alias de aplicaciones ----
    # "lo que dices"  ->  "como se llama el programa / ejecutable"
    "app_aliases": {
        "chrome": "Google Chrome",
        "google chrome": "Google Chrome",
        "navegador": "Google Chrome",
        "edge": "Microsoft Edge",
        "firefox": "Firefox",
        "word": "Word",
        "excel": "Excel",
        "powerpoint": "PowerPoint",
        "outlook": "Outlook",
        "spotify": "Spotify",
        "discord": "Discord",
        "steam": "Steam",
        "whatsapp": "WhatsApp",
        "telegram": "Telegram",
        "vscode": "Visual Studio Code",
        "visual studio code": "Visual Studio Code",
        "codigo": "Visual Studio Code",
        "calculadora": "calc",
        "calculator": "calc",
        "bloc de notas": "notepad",
        "notepad": "notepad",
        "paint": "mspaint",
        "explorador": "explorer",
        "explorador de archivos": "explorer",
        "cmd": "cmd",
        "terminal": "wt",
        "powershell": "powershell",
        "configuracion": "ms-settings:",
        "ajustes": "ms-settings:",
        "camara": "microsoft.windows.camera:",
        "reproductor": "mswindowsmusic:",
    },

    # ---- Sitios web ----
    "websites": {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "gmail": "https://mail.google.com",
        "correo": "https://mail.google.com",
        "github": "https://github.com",
        "chatgpt": "https://chat.openai.com",
        "claude": "https://claude.ai",
        "wikipedia": "https://es.wikipedia.org",
        "twitch": "https://www.twitch.tv",
        "netflix": "https://www.netflix.com",
        "spotify web": "https://open.spotify.com",
        "twitter": "https://twitter.com",
        "x": "https://twitter.com",
        "instagram": "https://www.instagram.com",
        "facebook": "https://www.facebook.com",
        "reddit": "https://www.reddit.com",
        "drive": "https://drive.google.com",
        "maps": "https://maps.google.com",
        "traductor": "https://translate.google.com",
        "noticias": "https://news.google.com",
        "clima": "https://www.google.com/search?q=clima",
    },
}


# --------------------------------------------------------------------------
# Carga / guardado
# --------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """Mezcla `override` sobre `base` sin perder claves nuevas de DEFAULTS."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """Acceso a la configuracion con rutas tipo 'ollama.model'."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data = data if data is not None else dict(DEFAULTS)

    # -- lectura / escritura ------------------------------------------------

    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, path: str, value: Any) -> None:
        parts = path.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def as_dict(self) -> dict[str, Any]:
        return self._data

    # -- persistencia -------------------------------------------------------

    @classmethod
    def load(cls) -> "Config":
        HOME_DIR.mkdir(parents=True, exist_ok=True)
        data = dict(DEFAULTS)
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                    data = _deep_merge(DEFAULTS, json.load(fh))
            except (json.JSONDecodeError, OSError) as exc:
                print(f"[config] No se pudo leer {CONFIG_FILE}: {exc}")
                print("[config] Se usaran los valores por defecto.")
        cfg = cls(data)
        cfg.save()  # asegura que el archivo exista y tenga las claves nuevas
        return cfg

    def save(self) -> bool:
        try:
            HOME_DIR.mkdir(parents=True, exist_ok=True)
            tmp = CONFIG_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, CONFIG_FILE)
            return True
        except OSError as exc:
            print(f"[config] No se pudo guardar la configuracion: {exc}")
            return False


# Instancia compartida por toda la aplicacion.
config = Config.load()
