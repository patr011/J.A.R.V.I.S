"""Control del sistema: volumen, brillo, energia e informacion del equipo.

Los comandos delicados (apagar, reiniciar, cerrar sesion) NO se ejecutan de
inmediato: devuelven una accion pendiente de confirmacion. El asistente
pregunta "¿confirma?" y solo entonces la ejecuta. Ademas el apagado se
programa con unos segundos de retraso para que puedas decir "cancela".
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from ..config import config
from ..logging_setup import get_logger
from .base import CommandResult

log = get_logger("sistema")

IS_WINDOWS = sys.platform == "win32"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# --------------------------------------------------------------------------
# Volumen
# --------------------------------------------------------------------------

class VolumeController:
    """Volumen maestro de Windows mediante pycaw.

    Si pycaw no esta instalado se usan las teclas multimedia como plan B
    (funciona igual, pero solo en pasos de ~2 % y sin poder leer el nivel).
    """

    VK_VOLUME_MUTE = 0xAD
    VK_VOLUME_DOWN = 0xAE
    VK_VOLUME_UP = 0xAF

    def __init__(self) -> None:
        self._endpoint = None
        self.backend = "teclas multimedia"
        self.error = ""
        if IS_WINDOWS:
            self._init_pycaw()
        else:
            self.error = "el control de volumen solo funciona en Windows"

    def _init_pycaw(self) -> None:
        """Conecta con el mezclador de Windows.

        Si algo falla se guarda el motivo en `self.error` en vez de callarlo:
        sin eso, el panel se limita a poner «n/d» y no hay forma de saber si
        falta la libreria, si el equipo no tiene tarjeta de sonido activa o
        si es otra cosa.
        """
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        except ImportError as exc:
            self.error = f"falta la librería pycaw ({exc}). Instálala con: pip install pycaw comtypes"
            return

        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._endpoint = cast(interface, POINTER(IAudioEndpointVolume))
            self.backend = "pycaw"
        except Exception as exc:
            self._endpoint = None
            self.error = f"{type(exc).__name__}: {exc}"
            log.warning("pycaw no ha podido conectar con el mezclador", exc_info=True)

    def retry(self) -> bool:
        """Vuelve a intentar la conexión (útil si cambias de altavoces)."""
        if not IS_WINDOWS:
            return False
        self._endpoint = None
        self.error = ""
        self._init_pycaw()
        return self._endpoint is not None

    # -- plan B: teclas multimedia --------------------------------------

    def _tap(self, key: int, times: int = 1) -> None:
        if not IS_WINDOWS:
            return
        for _ in range(times):
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)   # pulsar
            ctypes.windll.user32.keybd_event(key, 0, 2, 0)   # soltar

    # -- API ------------------------------------------------------------

    def get_level(self) -> int | None:
        """Volumen actual en 0-100, o None si no se puede leer."""
        if self._endpoint is None:
            return None
        try:
            return int(round(self._endpoint.GetMasterVolumeLevelScalar() * 100))
        except Exception:
            return None

    def set_level(self, percent: int) -> CommandResult:
        percent = max(0, min(100, int(percent)))
        if self._endpoint is not None:
            try:
                self._endpoint.SetMasterVolumeLevelScalar(percent / 100.0, None)
                if percent > 0:
                    self._endpoint.SetMute(0, None)
                return CommandResult.done(f"Volumen al {percent} por ciento.", volume=percent)
            except Exception as exc:
                return CommandResult.fail(f"No he podido cambiar el volumen: {exc}")

        if not IS_WINDOWS:
            return CommandResult.fail("El control de volumen solo está disponible en Windows.")
        # Sin pycaw: bajar del todo y subir a golpe de tecla (~2 % por pulsacion).
        self._tap(self.VK_VOLUME_DOWN, 50)
        self._tap(self.VK_VOLUME_UP, max(0, percent // 2))
        return CommandResult.done(f"Volumen aproximado al {percent} por ciento.", volume=percent)

    def change(self, delta: int) -> CommandResult:
        current = self.get_level()
        if current is not None:
            return self.set_level(current + delta)
        if not IS_WINDOWS:
            return CommandResult.fail("El control de volumen solo está disponible en Windows.")
        steps = max(1, abs(delta) // 2)
        self._tap(self.VK_VOLUME_UP if delta > 0 else self.VK_VOLUME_DOWN, steps)
        verbo = "Subiendo" if delta > 0 else "Bajando"
        return CommandResult.done(f"{verbo} el volumen.")

    def mute(self, value: bool | None = None) -> CommandResult:
        if self._endpoint is not None:
            try:
                new_state = (not bool(self._endpoint.GetMute())) if value is None else bool(value)
                self._endpoint.SetMute(1 if new_state else 0, None)
                return CommandResult.done("Sonido silenciado." if new_state else "Sonido restaurado.",
                                          muted=new_state)
            except Exception as exc:
                return CommandResult.fail(f"No he podido silenciar el audio: {exc}")
        if not IS_WINDOWS:
            return CommandResult.fail("El control de volumen solo está disponible en Windows.")
        self._tap(self.VK_VOLUME_MUTE)
        return CommandResult.done("Silencio conmutado.")

    def status(self) -> str:
        level = self.get_level()
        if level is None:
            detalle = f" ({self.error})" if self.error else ""
            return (f"Volumen: no puedo leer el nivel{detalle}. "
                    "Puedo subirlo y bajarlo igualmente con las teclas multimedia.")
        try:
            muted = bool(self._endpoint.GetMute()) if self._endpoint else False
        except Exception:
            muted = False
        return f"Volumen: {level}%{' (silenciado)' if muted else ''}"


# --------------------------------------------------------------------------
# Reproduccion (musica y video)
# --------------------------------------------------------------------------

def is_running(process_name: str) -> bool:
    """¿Esta abierto ese programa? (por ejemplo 'spotify.exe')"""
    try:
        import psutil
        needle = process_name.lower()
        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if name == needle:
                return True
    except Exception:
        pass
    return False


class MediaController:
    """Play, pausa y cambio de pista con las teclas multimedia de Windows.

    Funciona sobre el reproductor que este sonando: Spotify, YouTube en el
    navegador, el reproductor de Windows... Es el mismo mecanismo que usan
    los botones de multimedia de los teclados.
    """

    VK_MEDIA_NEXT = 0xB0
    VK_MEDIA_PREV = 0xB1
    VK_MEDIA_STOP = 0xB2
    VK_MEDIA_PLAY_PAUSE = 0xB3

    def _tap(self, key: int) -> bool:
        if not IS_WINDOWS:
            return False
        try:
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)
            ctypes.windll.user32.keybd_event(key, 0, 2, 0)
            return True
        except Exception:
            return False

    def play_pause(self) -> CommandResult:
        if not self._tap(self.VK_MEDIA_PLAY_PAUSE):
            return CommandResult.fail("El control de reproducción solo funciona en Windows.")
        return CommandResult.done("Listo.")

    def next_track(self) -> CommandResult:
        if not self._tap(self.VK_MEDIA_NEXT):
            return CommandResult.fail("El control de reproducción solo funciona en Windows.")
        return CommandResult.done("Siguiente pista.")

    def previous_track(self) -> CommandResult:
        if not self._tap(self.VK_MEDIA_PREV):
            return CommandResult.fail("El control de reproducción solo funciona en Windows.")
        return CommandResult.done("Pista anterior.")

    def stop(self) -> CommandResult:
        if not self._tap(self.VK_MEDIA_STOP):
            return CommandResult.fail("El control de reproducción solo funciona en Windows.")
        return CommandResult.done("Reproducción detenida.")

    def play_music(self) -> CommandResult:
        """«Pon música» sin decir qué: reanuda Spotify o lo abre.

        Si Spotify ya está abierto basta con la tecla de play. Si no lo está,
        se abre, pero no se puede pulsar play a ciegas: el programa tarda
        varios segundos en cargar y la tecla se perdería. Por eso se avisa al
        usuario en lugar de fingir que ha sonado algo.
        """
        if is_running("spotify.exe"):
            self._tap(self.VK_MEDIA_PLAY_PAUSE)
            return CommandResult.done("Reanudando la música en Spotify.")

        from .apps import launcher
        result = launcher.open_app("Spotify")
        if result.ok:
            return CommandResult.done(
                "Abriendo Spotify. En cuanto cargue, dígame «play» y le doy a reproducir."
            )
        return CommandResult.fail(
            "No encuentro Spotify instalado. Puede decirme «reproduce <lo que sea> "
            "en YouTube» y se lo busco en el navegador."
        )


# --------------------------------------------------------------------------
# Brillo
# --------------------------------------------------------------------------

class BrightnessController:
    """Brillo de pantalla mediante screen_brightness_control.

    Ojo: muchos monitores de sobremesa conectados por HDMI no permiten
    cambiar el brillo por software. En portatiles funciona casi siempre.
    """

    def __init__(self) -> None:
        self._sbc = None
        try:
            import screen_brightness_control as sbc
            self._sbc = sbc
        except Exception:
            self._sbc = None

    @property
    def available(self) -> bool:
        return self._sbc is not None

    def get_level(self) -> int | None:
        if not self.available:
            return None
        try:
            values = self._sbc.get_brightness()
            if isinstance(values, list) and values:
                return int(values[0])
            if isinstance(values, (int, float)):
                return int(values)
        except Exception:
            return None
        return None

    def set_level(self, percent: int) -> CommandResult:
        if not self.available:
            return CommandResult.fail(
                "No tengo control del brillo. Instale la librería con:  "
                "pip install screen-brightness-control"
            )
        percent = max(0, min(100, int(percent)))
        try:
            self._sbc.set_brightness(percent)
            return CommandResult.done(f"Brillo al {percent} por ciento.", brightness=percent)
        except Exception as exc:
            return CommandResult.fail(
                f"No he podido cambiar el brillo ({exc}). "
                "Es posible que su monitor no lo permita por software."
            )

    def change(self, delta: int) -> CommandResult:
        current = self.get_level()
        if current is None:
            return CommandResult.fail(
                "No puedo leer el brillo actual. Pruebe indicando un valor, "
                "por ejemplo «brillo al 60»."
            )
        return self.set_level(current + delta)

    def status(self) -> str:
        level = self.get_level()
        return f"Brillo: {level}%" if level is not None else "Brillo: no disponible"


# --------------------------------------------------------------------------
# Energia (comandos delicados)
# --------------------------------------------------------------------------

class PowerController:
    """Apagar, reiniciar, suspender, bloquear y cerrar sesion."""

    def _run(self, args: list[str]) -> tuple[bool, str]:
        try:
            proc = subprocess.run(
                args, capture_output=True, text=True, timeout=15,
                creationflags=_NO_WINDOW,
            )
            if proc.returncode != 0:
                return False, (proc.stderr or proc.stdout or "error desconocido").strip()
            return True, ""
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)

    # -- acciones reales -------------------------------------------------

    def _do_shutdown(self) -> CommandResult:
        delay = int(config.get("commands.shutdown_delay", 15))
        ok, err = self._run(["shutdown", "/s", "/t", str(delay)])
        if ok:
            return CommandResult.done(
                f"Apagando el equipo en {delay} segundos. "
                "Diga «cancela el apagado» si cambia de idea.", action="shutdown")
        return CommandResult.fail(f"No he podido apagar el equipo: {err}")

    def _do_restart(self) -> CommandResult:
        delay = int(config.get("commands.shutdown_delay", 15))
        ok, err = self._run(["shutdown", "/r", "/t", str(delay)])
        if ok:
            return CommandResult.done(
                f"Reiniciando en {delay} segundos. "
                "Diga «cancela el apagado» si cambia de idea.", action="restart")
        return CommandResult.fail(f"No he podido reiniciar el equipo: {err}")

    def _do_logoff(self) -> CommandResult:
        ok, err = self._run(["shutdown", "/l"])
        return (CommandResult.done("Cerrando la sesión.", action="logoff")
                if ok else CommandResult.fail(f"No he podido cerrar la sesión: {err}"))

    # -- API --------------------------------------------------------------

    def shutdown(self) -> CommandResult:
        if not IS_WINDOWS:
            return CommandResult.fail("Este comando solo funciona en Windows.")
        if not config.get("commands.confirm_dangerous", True):
            return self._do_shutdown()
        delay = int(config.get("commands.shutdown_delay", 15))
        return CommandResult(
            message=f"Va a apagar el equipo (con {delay} segundos de margen). ¿Lo confirma?",
            confirm_action=self._do_shutdown,
            confirm_prompt="apagar el equipo",
        )

    def restart(self) -> CommandResult:
        if not IS_WINDOWS:
            return CommandResult.fail("Este comando solo funciona en Windows.")
        if not config.get("commands.confirm_dangerous", True):
            return self._do_restart()
        delay = int(config.get("commands.shutdown_delay", 15))
        return CommandResult(
            message=f"Va a reiniciar el equipo (con {delay} segundos de margen). ¿Lo confirma?",
            confirm_action=self._do_restart,
            confirm_prompt="reiniciar el equipo",
        )

    def log_off(self) -> CommandResult:
        if not IS_WINDOWS:
            return CommandResult.fail("Este comando solo funciona en Windows.")
        if not config.get("commands.confirm_dangerous", True):
            return self._do_logoff()
        return CommandResult(
            message="Va a cerrar la sesión y perderá el trabajo sin guardar. ¿Lo confirma?",
            confirm_action=self._do_logoff,
            confirm_prompt="cerrar la sesión",
        )

    def cancel_shutdown(self) -> CommandResult:
        if not IS_WINDOWS:
            return CommandResult.fail("Este comando solo funciona en Windows.")
        ok, err = self._run(["shutdown", "/a"])
        if ok:
            return CommandResult.done("Apagado cancelado.")
        return CommandResult.fail(
            "No había ningún apagado programado que cancelar." if "1116" in err
            else f"No he podido cancelar el apagado: {err}"
        )

    def sleep(self) -> CommandResult:
        """Suspension. No pide confirmacion: es reversible al instante."""
        if not IS_WINDOWS:
            return CommandResult.fail("Este comando solo funciona en Windows.")
        try:
            # El segundo parametro (0) = suspender, no hibernar.
            # Nota: si la hibernacion esta activada, Windows puede hibernar.
            ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
            return CommandResult.done("Suspendiendo el equipo.", action="sleep")
        except Exception as exc:
            return CommandResult.fail(f"No he podido suspender el equipo: {exc}")

    def lock(self) -> CommandResult:
        if not IS_WINDOWS:
            return CommandResult.fail("Este comando solo funciona en Windows.")
        try:
            ctypes.windll.user32.LockWorkStation()
            return CommandResult.done("Equipo bloqueado.", action="lock")
        except Exception as exc:
            return CommandResult.fail(f"No he podido bloquear el equipo: {exc}")


# --------------------------------------------------------------------------
# Informacion del equipo
# --------------------------------------------------------------------------

def system_stats() -> dict[str, float | int | str]:
    """CPU, RAM y bateria para el panel lateral de la interfaz."""
    stats: dict[str, float | int | str] = {
        "cpu": 0.0, "ram": 0.0, "battery": -1, "plugged": False,
    }
    try:
        import psutil
        stats["cpu"] = psutil.cpu_percent(interval=None)
        stats["ram"] = psutil.virtual_memory().percent
        battery = psutil.sensors_battery()
        if battery is not None:
            stats["battery"] = int(battery.percent)
            stats["plugged"] = bool(battery.power_plugged)
    except Exception:
        pass
    return stats


def system_report(volume: "VolumeController", brightness: "BrightnessController") -> CommandResult:
    """Resumen del estado del equipo."""
    stats = system_stats()
    lines = [
        f"CPU: {stats['cpu']:.0f}%",
        f"Memoria: {stats['ram']:.0f}%",
        volume.status(),
        brightness.status(),
    ]
    if isinstance(stats["battery"], int) and stats["battery"] >= 0:
        enchufada = " (cargando)" if stats["plugged"] else ""
        lines.append(f"Batería: {stats['battery']}%{enchufada}")
    lines.append(f"Hora: {datetime.now().strftime('%H:%M')}")
    return CommandResult.done("Estado del sistema:\n   " + "\n   ".join(lines))


def tell_time() -> CommandResult:
    ahora = datetime.now()
    return CommandResult.done(f"Son las {ahora.strftime('%H:%M')}.")


def tell_date() -> CommandResult:
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    hoy = datetime.now()
    return CommandResult.done(
        f"Hoy es {dias[hoy.weekday()]}, {hoy.day} de {meses[hoy.month - 1]} de {hoy.year}."
    )


def take_screenshot() -> CommandResult:
    """Captura de pantalla guardada en Imagenes."""
    try:
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen is None:
            return CommandResult.fail("No he podido acceder a la pantalla.")
        pixmap = screen.grabWindow(0)

        folder = Path.home()
        for name in ("Pictures", "Imágenes", "Imagenes"):
            candidate = Path.home() / name
            if candidate.exists():
                folder = candidate
                break
        target = folder / f"jarvis_captura_{datetime.now():%Y%m%d_%H%M%S}.png"
        if pixmap.save(str(target), "PNG"):
            return CommandResult.done(f"Captura guardada en {target}.", path=str(target))
        return CommandResult.fail("No he podido guardar la captura.")
    except Exception as exc:
        return CommandResult.fail(f"No he podido hacer la captura: {exc}")


# Instancias compartidas
volume = VolumeController()
brightness = BrightnessController()
power = PowerController()
media = MediaController()
