"""Abrir paginas web y hacer busquedas en el navegador."""

from __future__ import annotations

import re
import webbrowser

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
    """Busca en YouTube (con el primer resultado listo para reproducir)."""
    term = term.strip()
    if not term:
        return CommandResult.fail("¿Qué quiere que reproduzca?")
    return search(term, engine="youtube")
