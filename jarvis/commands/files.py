"""Buscar y abrir archivos y carpetas por su nombre.

Busca en las carpetas personales (Escritorio, Documentos, Descargas,
Imagenes, Musica, Videos) y en cualquier otra ruta que añadas en
~/.jarvis/config.json  ->  "commands": { "search_paths": ["D:/Proyectos"] }
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from ..config import config
from .base import CommandResult, normalize, strip_filler

IS_WINDOWS = sys.platform == "win32"

# Carpetas conocidas: como las llamas -> nombres reales posibles en disco.
KNOWN_FOLDERS: dict[str, tuple[str, ...]] = {
    "escritorio": ("Desktop", "Escritorio"),
    "desktop": ("Desktop", "Escritorio"),
    "documentos": ("Documents", "Documentos"),
    "documents": ("Documents", "Documentos"),
    "descargas": ("Downloads", "Descargas"),
    "downloads": ("Downloads", "Descargas"),
    "imagenes": ("Pictures", "Imágenes", "Imagenes"),
    "fotos": ("Pictures", "Imágenes", "Imagenes"),
    "pictures": ("Pictures", "Imágenes", "Imagenes"),
    "musica": ("Music", "Música", "Musica"),
    "music": ("Music", "Música", "Musica"),
    "videos": ("Videos", "Vídeos"),
    "peliculas": ("Videos", "Vídeos"),
}

# Carpetas que nunca se recorren: son ruido y ralentizan la busqueda.
SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".svn", "venv", ".venv", "env",
    "appdata", "$recycle.bin", "system volume information", "windows",
    "program files", "program files (x86)", "programdata", ".cache",
    "site-packages", "dist-packages", ".gradle", ".nuget", "temp", "tmp",
}


def home_folder(alias: str) -> Path | None:
    """Devuelve la ruta real de una carpeta personal ('descargas' -> C:/Users/tu/Downloads)."""
    names = KNOWN_FOLDERS.get(normalize(alias))
    if not names:
        return None
    for name in names:
        candidate = Path.home() / name
        if candidate.exists():
            return candidate
    return None


def search_roots() -> list[Path]:
    """Carpetas donde se busca, en orden de prioridad."""
    roots: list[Path] = []
    for extra in config.get("commands.search_paths") or []:
        p = Path(str(extra)).expanduser()
        if p.exists():
            roots.append(p)
    for name in ("Desktop", "Escritorio", "Documents", "Documentos",
                 "Downloads", "Descargas", "Pictures", "Imágenes",
                 "Music", "Música", "Videos", "Vídeos"):
        p = Path.home() / name
        if p.exists() and p not in roots:
            roots.append(p)
    return roots


def _score(name: str, query: str) -> int:
    """Puntua lo bien que un nombre encaja con lo buscado (0 = no encaja)."""
    n, q = normalize(name), normalize(query)
    stem = normalize(Path(name).stem)
    if stem == q:
        return 100
    if n == q:
        return 95
    if stem.startswith(q):
        return 80
    if n.startswith(q):
        return 70
    if q in n:
        return 50
    # todas las palabras buscadas aparecen en el nombre
    words = q.split()
    if len(words) > 1 and all(w in n for w in words):
        return 40
    return 0


def find_paths(query: str, want: str = "any", limit: int | None = None) -> list[Path]:
    """Busca archivos o carpetas cuyo nombre se parezca a `query`.

    want: "file", "folder" o "any".
    """
    limit = limit or config.get("commands.max_search_results", 8)
    timeout = config.get("commands.search_timeout", 12)
    deadline = time.time() + timeout

    found: list[tuple[int, Path]] = []
    seen: set[str] = set()

    for root in search_roots():
        if time.time() > deadline:
            break
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                if time.time() > deadline:
                    break
                # No entrar en carpetas de sistema ni ocultas.
                dirnames[:] = [
                    d for d in dirnames
                    if normalize(d) not in SKIP_DIRS and not d.startswith(".")
                ]

                if want in ("folder", "any"):
                    for d in dirnames:
                        s = _score(d, query)
                        if s:
                            p = Path(dirpath) / d
                            if str(p).lower() not in seen:
                                seen.add(str(p).lower())
                                found.append((s + 5, p))  # las carpetas puntuan algo mas

                if want in ("file", "any"):
                    for f in filenames:
                        s = _score(f, query)
                        if s:
                            p = Path(dirpath) / f
                            if str(p).lower() not in seen:
                                seen.add(str(p).lower())
                                found.append((s, p))

                if len(found) >= limit * 6:
                    break
        except (OSError, PermissionError):
            continue

    found.sort(key=lambda item: (-item[0], len(str(item[1]))))
    return [p for _, p in found[:limit]]


def open_path(path: Path) -> tuple[bool, str]:
    """Abre un archivo o carpeta con el programa predeterminado."""
    try:
        if IS_WINDOWS:
            os.startfile(str(path))                  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True, ""
    except OSError as exc:
        return False, str(exc)


def reveal_path(path: Path) -> tuple[bool, str]:
    """Abre el Explorador con el archivo seleccionado."""
    try:
        if IS_WINDOWS:
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            open_path(path.parent)
        return True, ""
    except OSError as exc:
        return False, str(exc)


# --------------------------------------------------------------------------
# Comandos
# --------------------------------------------------------------------------

def open_folder(name: str) -> CommandResult:
    """Abre una carpeta: primero prueba con las carpetas personales."""
    query = strip_filler(name).replace("carpeta ", "").strip()
    if not query:
        return CommandResult.fail("¿Qué carpeta quiere que abra?")

    known = home_folder(query)
    if known:
        ok, err = open_path(known)
        if ok:
            return CommandResult.done(f"Abriendo la carpeta {known.name}.", path=str(known))
        return CommandResult.fail(f"No he podido abrir {known}: {err}")

    # ¿Es una ruta completa?
    candidate = Path(name.strip().strip('"')).expanduser()
    if candidate.is_dir():
        ok, err = open_path(candidate)
        if ok:
            return CommandResult.done(f"Abriendo {candidate}.", path=str(candidate))
        return CommandResult.fail(f"No he podido abrir {candidate}: {err}")

    results = find_paths(query, want="folder")
    if not results:
        return CommandResult.fail(
            f"No he encontrado ninguna carpeta llamada «{query}» en sus carpetas personales."
        )
    ok, err = open_path(results[0])
    if not ok:
        return CommandResult.fail(f"No he podido abrir la carpeta: {err}")

    message = f"Abriendo la carpeta {results[0].name}."
    if len(results) > 1:
        otras = "\n".join(f"   · {p}" for p in results[1:4])
        message += f"\nTambién encontré:\n{otras}"
    return CommandResult.done(message, path=str(results[0]))


def open_file(name: str) -> CommandResult:
    """Busca un archivo por su nombre y lo abre."""
    query = strip_filler(name).replace("archivo ", "").replace("fichero ", "").strip()
    if not query:
        return CommandResult.fail("¿Qué archivo quiere que busque?")

    candidate = Path(name.strip().strip('"')).expanduser()
    if candidate.is_file():
        ok, err = open_path(candidate)
        return (CommandResult.done(f"Abriendo {candidate.name}.", path=str(candidate))
                if ok else CommandResult.fail(f"No he podido abrirlo: {err}"))

    results = find_paths(query, want="any")
    if not results:
        return CommandResult.fail(
            f"No he encontrado nada llamado «{query}». "
            "Puede añadir más carpetas de búsqueda en el archivo de configuración."
        )

    best = results[0]
    ok, err = open_path(best)
    if not ok:
        return CommandResult.fail(f"He encontrado {best.name} pero no he podido abrirlo: {err}")

    message = f"Abriendo {best.name}.\n   {best.parent}"
    if len(results) > 1:
        otros = "\n".join(f"   · {p.name}  —  {p.parent}" for p in results[1:4])
        message += f"\nOtras coincidencias:\n{otros}"
    return CommandResult.done(message, path=str(best))


def search_only(name: str) -> CommandResult:
    """Busca sin abrir nada y lista los resultados."""
    query = strip_filler(name)
    if not query:
        return CommandResult.fail("¿Qué quiere que busque?")
    results = find_paths(query, want="any")
    if not results:
        return CommandResult.fail(f"No he encontrado nada llamado «{query}».")
    listado = "\n".join(f"   {i}. {p.name}  —  {p.parent}" for i, p in enumerate(results, 1))
    return CommandResult.done(
        f"He encontrado {len(results)} coincidencia(s) de «{query}»:\n{listado}",
        results=[str(p) for p in results],
    )
