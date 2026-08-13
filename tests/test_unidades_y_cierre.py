"""Conversión de unidades y cierre de aplicaciones."""

from __future__ import annotations

import pytest

from jarvis.commands import units
from jarvis.commands.apps import AppLauncher
from jarvis.commands.registry import CommandRouter

# --------------------------------------------------------------------------
# Conversiones
# --------------------------------------------------------------------------

CONVERSIONES = [
    ("cuántos kilómetros son 5 millas", 8.04672),
    ("convierte 3 libras a kilos", 1.360777),
    ("10 metros en centimetros", 1000),
    ("2 horas en minutos", 120),
    ("1 gigabyte en megabytes", 1024),
    ("100 kilometros por hora en millas por hora", 62.137119),
    ("1 pulgada en centimetros", 2.54),
]


@pytest.mark.parametrize("frase,esperado", CONVERSIONES)
def test_las_conversiones_salen_bien(frase, esperado):
    resultado = units.convert(frase)
    assert resultado is not None and resultado.ok, f"no ha convertido «{frase}»"
    assert resultado.data["result"] == pytest.approx(esperado, rel=1e-4)


TEMPERATURAS = [
    ("25 grados centigrados en fahrenheit", 77.0),
    ("100 celsius en kelvin", 373.15),
    ("32 fahrenheit en celsius", 0.0),
    ("0 kelvin en celsius", -273.15),
]


@pytest.mark.parametrize("frase,esperado", TEMPERATURAS)
def test_las_temperaturas_no_se_convierten_multiplicando(frase, esperado):
    """La temperatura tiene desplazamiento: 0 °C no son 0 °F."""
    resultado = units.convert(frase)
    assert resultado is not None and resultado.ok
    assert resultado.data["result"] == pytest.approx(esperado, abs=0.01)


def test_no_mezcla_magnitudes_distintas():
    resultado = units.convert("5 kilos en metros")
    assert resultado is not None and not resultado.ok
    assert "distintas" in resultado.message


@pytest.mark.parametrize("frase", [
    "hola qué tal", "abre chrome", "pon música", "cuéntame algo",
    "quiero 3 cosas", "cuánto es 7 + 39",
])
def test_no_ve_conversiones_donde_no_las_hay(frase):
    assert not units.looks_like_conversion(frase) or units.convert(frase) is None


def test_la_conversion_gana_a_la_calculadora():
    """«5 millas en km» tiene números, pero no es una cuenta."""
    resultado = CommandRouter().handle("cuántos kilómetros son 5 millas")
    assert resultado.handled
    assert "8" in resultado.message


def test_la_calculadora_sigue_funcionando():
    resultado = CommandRouter().handle("cuánto es 7 + 39")
    assert "46" in resultado.message


# --------------------------------------------------------------------------
# Cerrar aplicaciones
# --------------------------------------------------------------------------

class ProcesoFalso:
    def __init__(self, nombre, pid=1234):
        self.info = {"name": nombre, "pid": pid}
        self.terminado = False

    def terminate(self):
        self.terminado = True


@pytest.fixture
def procesos(monkeypatch):
    """Simula la lista de procesos abiertos del sistema."""
    abiertos: list[ProcesoFalso] = []

    class PsutilFalso:
        @staticmethod
        def process_iter(campos=None):
            return list(abiertos)

        @staticmethod
        def wait_procs(lista, timeout=None):
            return [], []

    import sys
    monkeypatch.setitem(sys.modules, "psutil", PsutilFalso)
    return abiertos


def test_cierra_la_aplicacion_pedida(procesos):
    chrome = ProcesoFalso("chrome.exe")
    spotify = ProcesoFalso("Spotify.exe")
    procesos.extend([chrome, spotify])

    resultado = AppLauncher().close_app("Chrome")
    assert resultado.ok
    assert chrome.terminado
    assert not spotify.terminado, "no debe cerrar lo que no se le ha pedido"


def test_avisa_si_no_esta_abierta(procesos):
    procesos.append(ProcesoFalso("notepad.exe"))
    resultado = AppLauncher().close_app("Spotify")
    assert not resultado.ok
    assert "no veo" in resultado.message.lower()


def test_nunca_se_cierra_a_si_mismo(procesos):
    """Cerrar «python» apagaría el propio asistente."""
    yo = ProcesoFalso("pythonw.exe")
    procesos.append(yo)
    resultado = AppLauncher().close_app("python")
    assert not yo.terminado
    assert not resultado.ok


def test_nunca_tumba_el_explorador_de_windows(procesos):
    """Matar explorer.exe deja el escritorio sin barra de tareas."""
    explorador = ProcesoFalso("explorer.exe")
    procesos.append(explorador)
    AppLauncher().close_app("explorer")
    assert not explorador.terminado


def test_cerrar_la_sesion_no_es_cerrar_una_aplicacion():
    """«cierra la sesión» debe seguir siendo el comando de Windows."""
    from .dobles import sistema_simulado
    with sistema_simulado() as registro:
        CommandRouter().handle("cierra la sesion")
        assert registro.primera == "cerrar-sesion"
