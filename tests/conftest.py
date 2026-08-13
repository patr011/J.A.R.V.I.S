"""Preparación común a todas las pruebas.

Lo más importante que hay aquí: las pruebas NUNCA deben tocar los datos
reales del usuario. Sin esto, ejecutarlas podría sobrescribir su memoria,
sus notas o sus alarmas de verdad.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def datos_en_carpeta_temporal(tmp_path, monkeypatch):
    """Redirige memoria, avisos y notas a una carpeta de usar y tirar."""
    from jarvis import config as config_module
    from jarvis.commands import reminders
    from jarvis.core import memory

    monkeypatch.setattr(config_module, "HOME_DIR", tmp_path, raising=False)
    monkeypatch.setattr(memory, "MEMORY_FILE", tmp_path / "memoria.json")
    monkeypatch.setattr(reminders, "REMINDERS_FILE", tmp_path / "avisos.json")

    try:
        from jarvis.commands import notes
        monkeypatch.setattr(notes, "NOTES_FILE", tmp_path / "notas.json")
    except ImportError:
        pass

    # Que ninguna prueba reescriba el config.json del usuario.
    monkeypatch.setattr(config_module.config, "save", lambda: True)
    yield
