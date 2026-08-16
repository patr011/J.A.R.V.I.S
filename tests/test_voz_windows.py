"""La voz de Windows y el fallo de «saluda y luego se calla».

Lo que pasaba en un equipo real: el asistente decía «Buenos días, Señor» y a
partir de ahí no volvía a hablar nunca más, sin ningún aviso.

La causa: cada vez que el usuario manda un mensaje, la ventana corta la voz
(para que no siga hablando de lo anterior). pyttsx3 se queda tocado con esa
interrupción y todas las llamadas siguientes fallan con «run loop already
started». La frase se tiraba a la basura en silencio.

Aquí se reproduce con un motor de mentira que se comporta igual de mal.
"""

from __future__ import annotations

import pytest

from jarvis.core import speech as modulo_voz


class MotorRencoroso:
    """Como pyttsx3: si le cortan una frase, no vuelve a funcionar jamás."""

    def __init__(self) -> None:
        self.dicho: list[str] = []
        self.roto = False
        self.propiedades: dict[str, object] = {}

    def setProperty(self, nombre, valor):           # noqa: N802 (nombre de pyttsx3)
        self.propiedades[nombre] = valor

    def getProperty(self, nombre):                  # noqa: N802
        return [] if nombre == "voices" else self.propiedades.get(nombre)

    def say(self, texto):
        if self.roto:
            raise RuntimeError("run loop already started")
        self.dicho.append(texto)

    def runAndWait(self):                           # noqa: N802
        if self.roto:
            raise RuntimeError("run loop already started")

    def stop(self):
        # Justo lo que hace la ventana al mandar un mensaje nuevo.
        self.roto = True


@pytest.fixture
def voz(monkeypatch):
    """Un TextToSpeech con motores de mentira, sin hilos ni audio."""
    motores: list[MotorRencoroso] = []

    def crear(self):
        motor = MotorRencoroso()
        motores.append(motor)
        return motor

    monkeypatch.setattr(modulo_voz, "TTS_AVAILABLE", True)
    monkeypatch.setattr(modulo_voz.TextToSpeech, "_crear_motor", crear)

    tts = modulo_voz.TextToSpeech.__new__(modulo_voz.TextToSpeech)
    tts._eleven = None
    tts.eleven_error = ""
    tts.engine_name = "windows"
    tts._engine = None
    tts._failures = 0
    tts._motor_por_frase = False
    tts.error = ""
    tts.enabled = True
    tts.available = True
    tts.motores = motores
    return tts


def _dicho(voz) -> list[str]:
    return [frase for motor in voz.motores for frase in motor.dicho]


# --------------------------------------------------------------------------
# El fallo reportado
# --------------------------------------------------------------------------

def test_habla_la_primera_frase(voz):
    assert voz._decir_con_windows("Buenos días, Señor.") is True
    assert _dicho(voz) == ["Buenos días, Señor."]


def test_despues_de_cortarle_sigue_hablando(voz):
    """El fallo exacto: saludaba y ya no decía nada más.

    Antes, la segunda frase se perdía sin dejar rastro. Ahora se rehace el
    motor y la frase se dice igualmente.
    """
    voz._decir_con_windows("Buenos días, Señor.")
    voz._engine.stop()                      # la ventana corta la voz

    assert voz._decir_con_windows("Son las tres y media.") is True
    assert "Son las tres y media." in _dicho(voz)


def test_aguanta_que_le_corten_una_y_otra_vez(voz):
    """Cortar la voz es lo normal: pasa con cada mensaje que se manda."""
    for numero in range(5):
        voz._decir_con_windows(f"frase {numero}")
        voz._engine.stop() if voz._engine else None

    dicho = _dicho(voz)
    for numero in range(5):
        assert f"frase {numero}" in dicho, f"se ha perdido la frase {numero}"


def test_si_el_motor_compartido_da_guerra_se_usa_uno_por_frase(voz):
    """Modo lento pero seguro: no hay estado que se pueda corromper."""
    voz._decir_con_windows("una")
    voz._engine.stop()
    voz._decir_con_windows("dos")           # aquí se rehace el motor

    # Ahora, además del motor actual roto, los nuevos también nacen rotos:
    # ya no queda más remedio que cambiar de modo.
    voz._engine.stop()

    def nace_roto(self):
        motor = MotorRencoroso()
        motor.roto = True
        voz.motores.append(motor)
        return motor

    original = type(voz)._crear_motor
    type(voz)._crear_motor = nace_roto
    try:
        voz._decir_con_windows("tres")
    finally:
        type(voz)._crear_motor = original

    assert voz._motor_por_frase is True


# --------------------------------------------------------------------------
# Cuando de verdad no hay manera
# --------------------------------------------------------------------------

def test_un_motor_que_nunca_va_acaba_desactivando_la_voz(voz, monkeypatch):
    """Insistir eternamente solo retrasaría cada respuesta."""
    def nace_roto(self):
        motor = MotorRencoroso()
        motor.roto = True
        return motor

    monkeypatch.setattr(modulo_voz.TextToSpeech, "_crear_motor", nace_roto)
    voz._motor_por_frase = True

    for _ in range(3):
        assert voz._decir_con_windows("hola") is False

    assert voz.enabled is False
    assert "se desactiva" in voz.error


def test_el_error_queda_escrito_para_que_la_ventana_lo_enseñe(voz, monkeypatch):
    """Con pythonw no hay consola: si no se guarda, el fallo es invisible."""
    def nace_roto(self):
        motor = MotorRencoroso()
        motor.roto = True
        return motor

    monkeypatch.setattr(modulo_voz.TextToSpeech, "_crear_motor", nace_roto)
    voz._motor_por_frase = True
    voz._decir_con_windows("hola")

    assert "Error al hablar" in voz.error
    assert "run loop already started" in voz.error


def test_una_frase_buena_borra_la_cuenta_de_fallos(voz, monkeypatch):
    """Un tropiezo suelto no puede acabar desactivando la voz."""
    voz._motor_por_frase = True
    voz._failures = 2
    voz._decir_con_windows("hola")
    assert voz._failures == 0
    assert voz.enabled is True
