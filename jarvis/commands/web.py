"""Abrir paginas web y hacer busquedas en el navegador."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import webbrowser
from urllib.parse import quote, quote_plus

import requests

from ..config import config
from .base import CommandResult, normalize, strip_filler

# Dominios frecuentes para reconocer "abre marca punto com".
_DOMAIN_RE = re.compile(
    r"^(https?://)?([\w-]+\.)+(com|es|org|net|io|dev|tv|me|gg|co|ai|app|info|edu|gov|mx|ar|cl)(/\S*)?$"
)

SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={}",
    "youtube": "https://www.youtube.com/results?search_query={}",
    "wikipedia": "https://es.wikipedia.org/w/index.php?search={}",
    "bing": "https://www.bing.com/search?q={}",
}


def _open(url: str) -> tuple[bool, str]:
    try:
        opened = webbrowser.open(url, new=2)
        return bool(opened), "" if opened else "el navegador no respondió"
    except Exception as exc:
        return False, str(exc)


def known_sites() -> dict[str, str]:
    return {normalize(k): v for k, v in (config.get("websites") or {}).items()}


def match_site(query: str) -> str | None:
    """Devuelve la URL si lo pedido es un sitio conocido o un dominio."""
    key = strip_filler(query)
    if not key:
        return None

    sites = known_sites()
    if key in sites:
        return sites[key]

    # "abre la pagina de youtube" -> el nombre puede venir con relleno
    for name, url in sites.items():
        if key == name or key.startswith(name + " ") or key.endswith(" " + name):
            return url

    # ¿Parece un dominio o una URL?
    candidate = query.strip().strip('"').replace(" punto ", ".").replace(" ", "")
    if _DOMAIN_RE.match(candidate):
        return candidate if candidate.startswith("http") else f"https://{candidate}"
    return None


def open_site(query: str) -> CommandResult:
    """Abre una web conocida, una URL o, si no, busca en Google."""
    url = match_site(query)
    if url:
        ok, err = _open(url)
        nombre = strip_filler(query) or url
        return (CommandResult.done(f"Abriendo {nombre}.", url=url)
                if ok else CommandResult.fail(f"No he podido abrir el navegador: {err}"))

    term = strip_filler(query)
    if not term:
        return CommandResult.fail("¿Qué página quiere que abra?")
    return search(term)


def search(term: str, engine: str = "google") -> CommandResult:
    """Busca un texto en el buscador indicado."""
    term = term.strip()
    if not term:
        return CommandResult.fail("¿Qué quiere que busque?")
    template = SEARCH_ENGINES.get(normalize(engine), SEARCH_ENGINES["google"])
    from urllib.parse import quote_plus
    url = template.format(quote_plus(term))
    ok, err = _open(url)
    if not ok:
        return CommandResult.fail(f"No he podido abrir el navegador: {err}")
    donde = "YouTube" if engine == "youtube" else ("Wikipedia" if engine == "wikipedia" else "Google")
    return CommandResult.done(f"Buscando «{term}» en {donde}.", url=url)


def play_on_youtube(term: str) -> CommandResult:
    """Busca en YouTube y deja los resultados en pantalla (sin reproducir)."""
    term = term.strip()
    if not term:
        return CommandResult.fail("¿Qué quiere que reproduzca?")
    return search(term, engine="youtube")


# --------------------------------------------------------------------------
# Reproducir una cancion concreta
# --------------------------------------------------------------------------

# En el HTML de los resultados de YouTube cada video aparece como
# "videoId":"dQw4w9WgXcQ" — once caracteres. Sacando el primero se llega
# directo al video, que es lo unico que reproduce de verdad: la pagina de
# resultados se queda quieta esperando a que hagas clic.
_VIDEO_ID_RE = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')

_BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


def first_youtube_video(term: str, timeout: int = 8) -> str | None:
    """Devuelve el id del primer video de la busqueda, o None si no se puede."""
    # El parametro sp=EgIQAQ%3D%3D filtra a videos: sin el, el primer
    # resultado puede ser un canal o una lista y el enlace no reproduciria nada.
    url = f"https://www.youtube.com/results?search_query={quote_plus(term)}&sp=EgIQAQ%3D%3D"
    try:
        response = requests.get(url, headers=_BROWSER_HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return None
    match = _VIDEO_ID_RE.search(response.text)
    return match.group(1) if match else None


def play_song(term: str) -> CommandResult:
    """Reproduce lo que le pidas: abre el primer video de YouTube."""
    term = term.strip()
    if not term:
        return CommandResult.fail("¿Qué canción quiere que ponga?")

    video_id = first_youtube_video(term)
    if video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"
        ok, err = _open(url)
        if ok:
            return CommandResult.done(f"Reproduciendo «{term}».", url=url)
        return CommandResult.fail(f"No he podido abrir el navegador: {err}")

    # Sin conexion o YouTube ha cambiado el formato: al menos deja la busqueda
    # hecha, pero se avisa de que hay que darle al play a mano.
    result = search(term, engine="youtube")
    if result.ok:
        return CommandResult.done(
            f"No he podido sacar el vídeo directo, así que le he dejado la búsqueda "
            f"de «{term}» abierta en YouTube. Pulse el primer resultado.")
    return result


def open_in_spotify(term: str) -> CommandResult:
    """Abre Spotify con la busqueda hecha."""
    term = term.strip()
    if not term:
        return CommandResult.fail("¿Qué quiere buscar en Spotify?")
    uri = f"spotify:search:{quote(term)}"
    try:
        if sys.platform == "win32":
            os.startfile(uri)                        # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", uri])
        return CommandResult.done(
            f"Buscando «{term}» en Spotify. Pulse la canción y empieza a sonar.", uri=uri)
    except OSError:
        return CommandResult.fail(
            "No he podido abrir Spotify. ¿Está instalado? Puedo ponérselo en YouTube.")
