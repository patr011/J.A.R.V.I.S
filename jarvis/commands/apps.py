"""Abrir aplicaciones instaladas por su nombre.

Como encuentra los programas:

1. Alias definidos en la configuracion ("navegador" -> "Google Chrome").
2. Ejecutables del sistema que Windows conoce (calc, notepad, mspaint...).
3. Indice de accesos directos del Menu Inicio (.lnk y .url), que es donde
   estan practicamente todos los programas instalados.
4. Busqueda aproximada: si dices "cromo" y tienes "Google Chrome",
   lo encuentra igual.
"""

from __future__ import annotations

import difflib
import os
import subprocess
import sys
import time
from pathlib import Path

from ..config import config
from .base import CommandResult, normalize, strip_filler

IS_WINDOWS = sys.platform == "win32"

# Ejecutables y URIs que Windows resuelve directamente sin buscar nada.
BUILTIN_TARGETS = {
    "calc": "Calculadora",
    "notepad": "Bloc de notas",
    "mspaint": "Paint",
    "explorer": "Explorador de archivos",
    "cmd": "Símbolo del sistema",
    "powershell": "PowerShell",
    "wt": "Terminal de Windows",
    "taskmgr": "Administrador de tareas",
    "control": "Panel de control",
    "snippingtool": "Recortes",
    "charmap": "Mapa de caracteres",
    "magnify": "Lupa",
    "osk": "Teclado en pantalla",
    "write": "WordPad",
    "ms-settings:": "Configuración",
    "microsoft.windows.camera:": "Cámara",
}

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AppLauncher:
    """Indice de aplicaciones instaladas + lanzador."""

    CACHE_SECONDS = 300  # el indice se refresca cada 5 minutos

    def __init__(self) -> None:
        self._index: dict[str, Path] = {}
        self._indexed_at: float = 0.0

    # ------------------------------------------------------------------
    # Indice del Menu Inicio
    # ------------------------------------------------------------------

    def _start_menu_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        if IS_WINDOWS:
            program_data = os.environ.get("ProgramData", r"C:\ProgramData")
            appdata = os.environ.get("APPDATA", "")
            dirs += [
                Path(program_data) / "Microsoft/Windows/Start Menu/Programs",
                Path(appdata) / "Microsoft/Windows/Start Menu/Programs" if appdata else Path(),
                Path.home() / "Desktop",
                Path(os.environ.get("PUBLIC", "C:/Users/Public")) / "Desktop",
            ]
        else:  # Linux / macOS: sirve para poder probar el codigo fuera de Windows
            dirs += [
                Path("/usr/share/applications"),
                Path.home() / ".local/share/applications",
                Path("/Applications"),
            ]
        return [d for d in dirs if d and d.exists()]

    def build_index(self, force: bool = False) -> dict[str, Path]:
        """Recorre el Menu Inicio y guarda {nombre_normalizado: ruta}."""
        fresh = (time.time() - self._indexed_at) < self.CACHE_SECONDS
        if self._index and fresh and not force:
            return self._index

        index: dict[str, Path] = {}
        patterns = ("*.lnk", "*.url") if IS_WINDOWS else ("*.desktop", "*.app")
        for base in self._start_menu_dirs():
            for pattern in patterns:
                try:
                    for path in base.rglob(pattern):
                        key = normalize(path.stem)
                        # El primero gana: el Menu Inicio del usuario tiene
                        # prioridad sobre duplicados de subcarpetas.
                        index.setdefault(key, path)
                except (OSError, PermissionError):
                    continue

        self._index = index
        self._indexed_at = time.time()
        return index

    def find(self, query: str) -> tuple[str, Path] | None:
        """Busca la app que mejor encaja con lo que pidio el usuario."""
        index = self.build_index()
        if not index:
            return None
        key = normalize(query)

        # 1) coincidencia exacta
        if key in index:
            return key, index[key]

        # 2) el nombre empieza por lo pedido ("word" -> "word 2021")
        starts = [k for k in index if k.startswith(key)]
        if starts:
            best = min(starts, key=len)
            return best, index[best]

        # 3) lo pedido aparece dentro del nombre
        contains = [k for k in index if key in k]
        if contains:
            best = min(contains, key=len)
            return best, index[best]

        # 4) parecido fonetico/ortografico
        close = difflib.get_close_matches(key, list(index.keys()), n=1, cutoff=0.72)
        if close:
            return close[0], index[close[0]]
        return None

    # ------------------------------------------------------------------
    # Lanzar
    # ------------------------------------------------------------------

    @staticmethod
    def _start(target: str | Path) -> tuple[bool, str]:
        """Abre un archivo, acceso directo, ejecutable o URI."""
        try:
            if IS_WINDOWS:
                os.startfile(str(target))            # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
            return True, ""
        except FileNotFoundError:
            return False, "no se encontró el archivo"
        except OSError as exc:
            return False, str(exc)

    @staticmethod
    def _run_command(command: str) -> tuple[bool, str]:
        """Ejecuta un comando suelto (calc, notepad...) sin abrir consola."""
        try:
            if IS_WINDOWS:
                subprocess.Popen(
                    ["cmd", "/c", "start", "", command],
                    shell=False,
                    creationflags=_NO_WINDOW,
                )
            else:
                subprocess.Popen([command])
            return True, ""
        except (OSError, ValueError) as exc:
            return False, str(exc)

    def open_app(self, spoken_name: str) -> CommandResult:
        """Punto de entrada: abre la aplicacion que el usuario ha pedido."""
        raw = strip_filler(spoken_name)
        if not raw:
            return CommandResult.fail("¿Qué aplicación quiere que abra?")

        # 1) Alias configurados por el usuario
        aliases = {normalize(k): v for k, v in (config.get("app_aliases") or {}).items()}
        target_name = aliases.get(raw, raw)
        norm_target = normalize(target_name)

        # 2) Ejecutables/URIs que Windows ya conoce
        if norm_target in BUILTIN_TARGETS:
            ok, err = self._run_command(target_name)
            if ok:
                return CommandResult.done(
                    f"Abriendo {BUILTIN_TARGETS[norm_target]}.", app=target_name
                )
            return CommandResult.fail(f"No he podido abrir {target_name}: {err}")

        # 3) Menu Inicio
        match = self.find(target_name)
        if match:
            name, path = match
            ok, err = self._start(path)
            if ok:
                return CommandResult.done(
                    f"Abriendo {path.stem}.", app=path.stem, path=str(path)
                )
            return CommandResult.fail(f"He encontrado {path.stem} pero no he podido abrirlo: {err}")

        # 4) Ultimo intento: que lo resuelva el propio Windows
        if IS_WINDOWS and " " not in target_name:
            ok, _ = self._run_command(target_name)
            if ok:
                return CommandResult.done(f"Intentando abrir {target_name}.", app=target_name)

        sugerencias = self.suggest(target_name)
        extra = f" ¿Quizá se refería a: {sugerencias}?" if sugerencias else ""
        return CommandResult.fail(
            f"No encuentro ninguna aplicación llamada «{spoken_name.strip()}».{extra}"
        )

    def suggest(self, query: str, limit: int = 3) -> str:
        """Nombres parecidos, para ayudar cuando no se encuentra la app."""
        index = self.build_index()
        if not index:
            return ""
        matches = difflib.get_close_matches(normalize(query), list(index.keys()), n=limit, cutoff=0.45)
        return ", ".join(index[m].stem for m in matches)

    def list_apps(self, limit: int = 40) -> list[str]:
        index = self.build_index()
        return sorted({p.stem for p in index.values()})[:limit]


# Instancia compartida (el indice se construye una sola vez).
launcher = AppLauncher()


def open_app(name: str) -> CommandResult:
    return launcher.open_app(name)
