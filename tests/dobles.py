"""Dobles de prueba: sustituyen todo lo que tocaría el sistema de verdad.

Sin esto, ejecutar las pruebas abriría programas, cambiaría el volumen y, en
el peor de los casos, apagaría el ordenador. Aquí cada acción se limita a
apuntar que la han llamado.
"""

from __future__ import annotations

from contextlib import contextmanager

from jarvis.commands import calc, files, system, weather, web
from jarvis.commands.apps import launcher
from jarvis.commands.base import CommandResult


class Registro:
    """Apunta qué comandos se han ejecutado y con qué argumentos."""

    def __init__(self) -> None:
        self.llamadas: list[tuple] = []

    def apuntar(self, nombre: str, *args):
        self.llamadas.append((nombre,) + args)
        return CommandResult.done(f"{nombre}:{args}")

    @property
    def primera(self) -> str:
        return self.llamadas[0][0] if self.llamadas else "SIN-LLAMADA"

    @property
    def primer_argumento(self):
        if self.llamadas and len(self.llamadas[0]) > 1:
            return self.llamadas[0][1]
        return None

    def limpiar(self) -> None:
        self.llamadas.clear()


@contextmanager
def sistema_simulado():
    """Sustituye las acciones reales y las restaura al terminar."""
    registro = Registro()
    originales: list[tuple[object, str, object]] = []

    def sustituir(modulo, nombre, funcion):
        originales.append((modulo, nombre, getattr(modulo, nombre)))
        setattr(modulo, nombre, funcion)

    # --- aplicaciones, archivos y web ---
    sustituir(launcher, "open_app", lambda n: registro.apuntar("app", n))
    sustituir(files, "open_folder", lambda n: registro.apuntar("carpeta", n))
    sustituir(files, "open_file", lambda n: registro.apuntar("archivo", n))
    sustituir(files, "search_only", lambda n: registro.apuntar("buscar", n))
    sustituir(files, "find_paths", lambda *a, **k: [])
    sustituir(web, "open_site", lambda t: registro.apuntar("web", t))
    sustituir(web, "search", lambda t, engine="google": registro.apuntar("buscar-web", t, engine))
    sustituir(web, "play_song", lambda t: registro.apuntar("cancion", t))
    sustituir(web, "play_on_youtube", lambda t: registro.apuntar("youtube", t))
    sustituir(web, "open_in_spotify", lambda t: registro.apuntar("spotify", t))
    sustituir(weather, "get_weather", lambda c="": registro.apuntar("clima", c))

    # --- volumen, brillo y multimedia ---
    sustituir(system.volume, "set_level", lambda v: registro.apuntar("volumen-fijar", v))
    sustituir(system.volume, "change", lambda d: registro.apuntar("volumen-cambiar", d))
    sustituir(system.volume, "mute", lambda v=None: registro.apuntar("silenciar", v))
    sustituir(system.volume, "status", lambda: "Volumen: 50%")
    sustituir(system.brightness, "set_level", lambda v: registro.apuntar("brillo-fijar", v))
    sustituir(system.brightness, "change", lambda d: registro.apuntar("brillo-cambiar", d))
    sustituir(system.brightness, "status", lambda: "Brillo: 50%")
    sustituir(system.media, "play_pause", lambda: registro.apuntar("play-pausa"))
    sustituir(system.media, "next_track", lambda: registro.apuntar("siguiente"))
    sustituir(system.media, "previous_track", lambda: registro.apuntar("anterior"))
    sustituir(system.media, "play_music", lambda: registro.apuntar("musica"))

    # --- energia: NUNCA se ejecuta de verdad ---
    def confirmable(nombre: str, texto: str):
        def _accion():
            registro.apuntar(nombre)
            return CommandResult(
                message="¿Lo confirma?",
                confirm_action=lambda: registro.apuntar(f"{nombre}-confirmado"),
                confirm_prompt=texto,
            )
        return _accion

    sustituir(system.power, "shutdown", confirmable("apagar", "apagar el equipo"))
    sustituir(system.power, "restart", confirmable("reiniciar", "reiniciar el equipo"))
    sustituir(system.power, "log_off", confirmable("cerrar-sesion", "cerrar la sesión"))
    sustituir(system.power, "sleep", lambda: registro.apuntar("suspender"))
    sustituir(system.power, "lock", lambda: registro.apuntar("bloquear"))
    sustituir(system.power, "cancel_shutdown", lambda: registro.apuntar("cancelar-apagado"))
    sustituir(system, "take_screenshot", lambda: registro.apuntar("captura"))

    try:
        yield registro
    finally:
        for modulo, nombre, original in reversed(originales):
            setattr(modulo, nombre, original)
