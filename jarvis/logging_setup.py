"""Registro de errores en archivo.

El asistente arranca con pythonw.exe para no dejar una consola negra abierta,
y eso tiene un precio: si algo falla, el mensaje de error no se ve en ningún
sitio. Aquí se manda todo a ~/.jarvis/jarvis.log, que es lo que hay que mirar
(o mandarme) cuando algo se comporta de forma rara.

El archivo se rota al llegar a 1 MB para que no crezca sin control.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback
from types import TracebackType

from .config import HOME_DIR, LOG_FILE

_configurado = False


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Prepara el registro. Se puede llamar varias veces sin duplicar nada."""
    global _configurado
    logger = logging.getLogger("jarvis")
    if _configurado:
        return logger

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    formato = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        HOME_DIR.mkdir(parents=True, exist_ok=True)
        archivo = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        archivo.setFormatter(formato)
        archivo.setLevel(logging.DEBUG)
        logger.addHandler(archivo)
    except OSError:
        pass                                     # sin log, pero el programa sigue

    # En modo consola también se ve por pantalla.
    if verbose or sys.stderr is not None and sys.stderr.isatty():
        consola = logging.StreamHandler()
        consola.setFormatter(formato)
        consola.setLevel(logging.WARNING)
        logger.addHandler(consola)

    _configurado = True
    logger.info("=" * 60)
    logger.info("J.A.R.V.I.S. iniciado")
    return logger


def get_logger(nombre: str = "") -> logging.Logger:
    return logging.getLogger(f"jarvis.{nombre}" if nombre else "jarvis")


def install_exception_hook(on_error=None) -> None:
    """Captura los errores que nadie ha recogido y los deja en el log.

    Sin esto, un fallo inesperado cierra la ventana sin dejar rastro y el
    usuario solo ve que «el programa se ha cerrado solo».
    """
    logger = get_logger("fallo")
    anterior = sys.excepthook

    def gancho(tipo: type[BaseException], valor: BaseException,
               rastro: TracebackType | None) -> None:
        if issubclass(tipo, KeyboardInterrupt):
            anterior(tipo, valor, rastro)
            return
        detalle = "".join(traceback.format_exception(tipo, valor, rastro))
        logger.error("Error no controlado:\n%s", detalle)
        if on_error is not None:
            try:
                on_error(f"{tipo.__name__}: {valor}")
            except Exception:
                pass
        anterior(tipo, valor, rastro)

    sys.excepthook = gancho
