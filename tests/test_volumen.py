"""El volumen y su trampa: un objeto COM pertenece al hilo que lo creó.

El panel enseñaba «n/d» con pycaw perfectamente instalado. El motivo: el
enlace con el mezclador se creaba una vez y se compartía entre hilos, y desde
cualquier otro hilo las llamadas fallaban. Como el error se tragaba en
silencio, solo se veía el «n/d».

Aquí se prueba la lógica de reparto por hilos con un mezclador de mentira,
que es la única forma de comprobarlo sin estar en Windows.
"""

from __future__ import annotations

import threading

import pytest

from jarvis.commands import system as syscmd


class MezcladorFalso:
    """Se comporta como el endpoint de pycaw, pero solo para su hilo."""

    def __init__(self, nivel: float = 0.42) -> None:
        self.nivel = nivel
        self.silenciado = False
        self.hilo = threading.get_ident()

    def _comprobar_hilo(self) -> None:
        if threading.get_ident() != self.hilo:
            raise OSError("CoInitialize has not been called")

    def GetMasterVolumeLevelScalar(self):          # noqa: N802 (nombre de COM)
        self._comprobar_hilo()
        return self.nivel

    def SetMasterVolumeLevelScalar(self, valor, _):  # noqa: N802
        self._comprobar_hilo()
        self.nivel = valor

    def GetMute(self):                              # noqa: N802
        self._comprobar_hilo()
        return int(self.silenciado)

    def SetMute(self, valor, _):                    # noqa: N802
        self._comprobar_hilo()
        self.silenciado = bool(valor)


@pytest.fixture
def control(monkeypatch):
    """Un VolumeController que se cree que está en Windows."""
    monkeypatch.setattr(syscmd, "IS_WINDOWS", True)
    creados: list[MezcladorFalso] = []

    def crear(self):
        mezclador = MezcladorFalso()
        creados.append(mezclador)
        return mezclador

    monkeypatch.setattr(syscmd.VolumeController, "_crear_endpoint", crear)
    control = syscmd.VolumeController()
    control.creados = creados
    return control


# --------------------------------------------------------------------------
# El fallo que se veía como «n/d»
# --------------------------------------------------------------------------

def test_se_lee_el_volumen_desde_el_hilo_principal(control):
    assert control.get_level() == 42
    assert control.backend == "pycaw"
    assert control.error == ""


def test_tambien_se_lee_desde_otro_hilo(control):
    """Esta es la prueba que importa: antes devolvía None.

    La ventana refresca desde el hilo de la interfaz y los comandos se
    ejecutan en hilos de trabajo. Compartir un solo objeto COM entre los dos
    hacía que uno de ellos siempre fallara.
    """
    resultado = {}

    def leer():
        resultado["nivel"] = control.get_level()

    hilo = threading.Thread(target=leer)
    hilo.start()
    hilo.join()

    assert resultado["nivel"] == 42, "el volumen no se puede leer desde otro hilo"


def test_cada_hilo_tiene_su_propio_enlace(control):
    control.get_level()

    def leer():
        control.get_level()

    hilo = threading.Thread(target=leer)
    hilo.start()
    hilo.join()

    assert len(control.creados) == 2, "los hilos deberían tener un enlace cada uno"


def test_no_se_reconecta_en_cada_lectura(control):
    """Se lee cada dos segundos: abrir el mezclador cada vez sería absurdo."""
    for _ in range(5):
        control.get_level()
    assert len(control.creados) == 1


# --------------------------------------------------------------------------
# Cuando de verdad no se puede
# --------------------------------------------------------------------------

def test_si_falta_pycaw_se_explica_como_instalarlo(monkeypatch):
    monkeypatch.setattr(syscmd, "IS_WINDOWS", True)

    def sin_pycaw(self):
        raise ImportError("No module named 'pycaw'")

    monkeypatch.setattr(syscmd.VolumeController, "_crear_endpoint", sin_pycaw)
    control = syscmd.VolumeController()

    assert control.get_level() is None
    assert "pip install pycaw" in control.error


def test_un_fallo_no_se_reintenta_sin_parar(monkeypatch):
    """Reintentar cada dos segundos para siempre no arregla nada y molesta."""
    monkeypatch.setattr(syscmd, "IS_WINDOWS", True)
    intentos = []

    def falla(self):
        intentos.append(1)
        raise OSError("no hay tarjeta de sonido")

    monkeypatch.setattr(syscmd.VolumeController, "_crear_endpoint", falla)
    control = syscmd.VolumeController()
    for _ in range(5):
        control.get_level()

    assert len(intentos) == 1
    assert "no hay tarjeta de sonido" in control.error


def test_reintentar_a_mano_si_cambias_de_altavoces(monkeypatch):
    monkeypatch.setattr(syscmd, "IS_WINDOWS", True)
    estado = {"va": False}

    def a_veces(self):
        if not estado["va"]:
            raise OSError("altavoces desconectados")
        return MezcladorFalso()

    monkeypatch.setattr(syscmd.VolumeController, "_crear_endpoint", a_veces)
    control = syscmd.VolumeController()
    assert control.get_level() is None

    estado["va"] = True
    assert control.retry() is True
    assert control.get_level() == 42


def test_si_los_altavoces_desaparecen_se_rehace_el_enlace(control):
    """Desconectar unos auriculares no puede dejar el volumen en «n/d»."""
    control.get_level()
    # El mezclador actual se rompe, como cuando cambia la salida de audio.
    control._local.endpoint.hilo = -1
    assert control.get_level() is None          # esta lectura se pierde
    assert control.get_level() == 42            # la siguiente ya va


# --------------------------------------------------------------------------
# Que el resto siga funcionando
# --------------------------------------------------------------------------

def test_subir_y_bajar_el_volumen(control):
    control.set_level(70)
    assert control.get_level() == 70
    control.change(-20)
    assert control.get_level() == 50


def test_silenciar_y_restaurar(control):
    control.mute(True)
    assert "silenciado" in control.status().lower()
    control.mute(False)
    assert "silenciado" not in control.status().lower()


def test_subir_el_volumen_quita_el_silencio(control):
    """Si está en silencio y pides volumen, lo que quieres es oír algo."""
    control.mute(True)
    control.set_level(40)
    assert control._local.endpoint.silenciado is False


def test_fuera_de_windows_lo_dice_claramente(monkeypatch):
    monkeypatch.setattr(syscmd, "IS_WINDOWS", False)
    control = syscmd.VolumeController()
    assert control.get_level() is None
    assert "Windows" in control.error


# --------------------------------------------------------------------------
# pycaw ha cambiado de forma con los años
# --------------------------------------------------------------------------
#
# El fallo real visto en Windows:
#     AttributeError: 'AudioDevice' object has no attribute 'Activate'
# El codigo clasico -el que sale en toda la documentacion- dejo de valer
# cuando GetSpeakers() empezo a devolver un envoltorio.

class DispositivoClasico:
    """pycaw de siempre: el objeto COM crudo, con su Activate."""

    def __init__(self, mezclador):
        self._mezclador = mezclador

    def Activate(self, _iid, _ctx, _params):        # noqa: N802 (nombre de COM)
        return self._mezclador


class AudioDeviceNuevo:
    """pycaw nueva: un envoltorio que NO tiene Activate."""

    def __init__(self, mezclador):
        self._dev = DispositivoClasico(mezclador)
        self.id = "{0.0.0.00000000}"


class AudioDeviceSinNada:
    """Un envoltorio que no deja llegar al dispositivo por ningún lado."""

    def __init__(self):
        self.id = "{0.0.0.00000000}"


def _preparar(monkeypatch, altavoces, directo=None):
    """Monta un VolumeController con la forma de pycaw que se quiera probar."""
    monkeypatch.setattr(syscmd, "IS_WINDOWS", True)
    mezclador = MezcladorFalso()

    monkeypatch.setattr(syscmd.VolumeController, "_altavoces",
                        staticmethod(lambda: altavoces(mezclador)))
    monkeypatch.setattr(syscmd.VolumeController, "_activar",
                        lambda self, dispositivo: dispositivo.Activate(None, None, None))
    monkeypatch.setattr(syscmd.VolumeController, "_endpoint_directo",
                        lambda self: directo(mezclador) if directo else None)
    return syscmd.VolumeController()


def test_con_la_pycaw_de_siempre_funciona(monkeypatch):
    control = _preparar(monkeypatch, DispositivoClasico)
    assert control.get_level() == 42


def test_con_la_pycaw_nueva_tambien(monkeypatch):
    """Este es el fallo del usuario: «AudioDevice no tiene Activate»."""
    control = _preparar(monkeypatch, AudioDeviceNuevo)
    assert control.get_level() == 42, "no ha sabido sacar el dispositivo del envoltorio"
    assert control.error == ""


def test_si_los_envoltorios_no_sirven_queda_la_via_directa(monkeypatch):
    """Si pycaw vuelve a cambiar, se le pide el mezclador a Windows y ya."""
    control = _preparar(monkeypatch, lambda _: AudioDeviceSinNada(),
                        directo=lambda mezclador: mezclador)
    assert control.get_level() == 42


def test_si_no_funciona_ninguna_via_se_explica_cual_ha_fallado(monkeypatch):
    control = _preparar(monkeypatch, lambda _: AudioDeviceSinNada())
    assert control.get_level() is None
    assert "ninguna forma" in control.error


def test_un_mezclador_que_existe_pero_no_responde_no_cuela(monkeypatch):
    """Devolver un objeto no basta: tiene que saber decir el volumen.

    Sin comprobarlo, el panel enseñaría «n/d» igualmente pero sin motivo.
    """
    class Mudo:
        def GetMasterVolumeLevelScalar(self):        # noqa: N802
            raise OSError("el dispositivo no responde")

    monkeypatch.setattr(syscmd, "IS_WINDOWS", True)
    monkeypatch.setattr(syscmd.VolumeController, "_altavoces",
                        staticmethod(lambda: DispositivoClasico(Mudo())))
    monkeypatch.setattr(syscmd.VolumeController, "_activar",
                        lambda self, d: d.Activate(None, None, None))
    monkeypatch.setattr(syscmd.VolumeController, "_endpoint_directo",
                        lambda self: None)

    control = syscmd.VolumeController()
    assert control.get_level() is None
    assert "no responde" in control.error
