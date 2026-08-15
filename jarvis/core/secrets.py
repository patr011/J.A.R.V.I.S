"""Carga de la clave de API desde el entorno o desde un archivo .env.

La clave NUNCA se escribe en el código ni en config.json. Se busca, en este
orden:

    1. La variable de entorno ANTHROPIC_API_KEY (si ya está puesta, gana).
    2. El archivo  .env  en la carpeta del proyecto.
    3. El archivo  ~/.jarvis/.env  (recomendado: queda fuera del repositorio).

Se escribe un lector de .env propio, de veinte líneas, en lugar de añadir la
librería python-dotenv: una dependencia menos que instalar para algo tan
pequeño, y así se controla que una variable ya definida en el entorno no se
pise nunca.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..config import HOME_DIR
from ..logging_setup import get_logger

log = get_logger("secretos")

API_KEY_VAR = "ANTHROPIC_API_KEY"
ELEVENLABS_KEY_VAR = "ELEVENLABS_API_KEY"

# El .env del proyecto se lee primero; el de ~/.jarvis es el recomendado.
ENV_FILES = (
    Path(__file__).resolve().parent.parent.parent / ".env",
    HOME_DIR / ".env",
)


def parse_env_file(texto: str) -> dict[str, str]:
    """Lee el contenido de un .env y devuelve sus variables.

    Admite comentarios, líneas en blanco, el prefijo «export» y valores
    entre comillas simples o dobles.
    """
    variables: dict[str, str] = {}
    # El Bloc de notas y PowerShell suelen colar una marca invisible (BOM) al
    # principio del archivo. Sin quitarla, la primera variable pasaria a
    # llamarse "﻿ANTHROPIC_API_KEY" y la clave no se encontraria nunca.
    texto = texto.lstrip("﻿")
    for linea in texto.splitlines():
        linea = linea.strip().lstrip("﻿")
        if not linea or linea.startswith("#"):
            continue
        if linea.lower().startswith("export "):
            linea = linea[7:].lstrip()
        if "=" not in linea:
            continue
        nombre, _, valor = linea.partition("=")
        nombre = nombre.strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        if nombre:
            variables[nombre] = valor
    return variables


def load_env_files() -> list[Path]:
    """Carga los .env encontrados. Devuelve los archivos que ha leído."""
    cargados: list[Path] = []
    for ruta in ENV_FILES:
        try:
            if not ruta.is_file():
                continue
            variables = parse_env_file(ruta.read_text(encoding="utf-8"))
            for nombre, valor in variables.items():
                # Lo que ya está en el entorno manda: así se puede lanzar el
                # asistente con otra clave sin editar ningún archivo.
                os.environ.setdefault(nombre, valor)
            cargados.append(ruta)
            log.info("Variables cargadas desde %s", ruta)
        except OSError as exc:
            log.warning("No se pudo leer %s: %s", ruta, exc)
    return cargados


def _leer_clave(variable: str) -> str:
    """Busca una clave en el entorno y, si no está, en los .env."""
    clave = os.environ.get(variable, "").strip()
    if not clave:
        load_env_files()
        clave = os.environ.get(variable, "").strip()
    return clave


def get_api_key() -> str:
    """La clave de Claude, o cadena vacía si no está configurada."""
    return _leer_clave(API_KEY_VAR)


def has_api_key() -> bool:
    return bool(get_api_key())


def get_elevenlabs_key() -> str:
    """La clave de ElevenLabs (voz), o cadena vacía. Es opcional."""
    return _leer_clave(ELEVENLABS_KEY_VAR)


def has_elevenlabs_key() -> bool:
    return bool(get_elevenlabs_key())


def mask_api_key(clave: str = "") -> str:
    """Muestra la clave sin revelarla: sk-ant-…a4f2.

    Se usa en la interfaz y en el diagnóstico para que el usuario pueda
    comprobar *cuál* clave está activa sin que quede escrita en ningún sitio.
    """
    clave = clave or get_api_key()
    if not clave:
        return "sin configurar"
    if len(clave) <= 12:
        return "…" + clave[-4:]
    return f"{clave[:7]}…{clave[-4:]}"


def where_to_put_the_key() -> str:
    """Instrucciones para el usuario cuando falta la clave."""
    return (
        "No encuentro la clave de la API de Claude.\n"
        f"   Cree el archivo  {HOME_DIR / '.env'}  con esta línea dentro:\n"
        "       ANTHROPIC_API_KEY=sk-ant-...\n"
        "   Su clave se obtiene en https://console.anthropic.com/settings/keys\n"
        "   (También sirve la variable de entorno ANTHROPIC_API_KEY.)"
    )
