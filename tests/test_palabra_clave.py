"""La palabra clave: «Oye JARVIS, pon música»."""

from __future__ import annotations

import pytest

from jarvis.core.speech import strip_wake_word

# (lo que oye el micrófono, ¿despierta?, orden que queda)
CASOS = [
    ("Oye Jarvis, pon música", True, "pon música"),
    ("oye jarvis pon musica", True, "pon musica"),
    ("Hey Jarvis, ¿qué hora es?", True, "¿qué hora es?"),
    ("Jarvis, abre Chrome", True, "abre Chrome"),
    ("jarvis sube el volumen", True, "sube el volumen"),
    ("OK Jarvis, apaga el equipo", True, "apaga el equipo"),
    # solo el nombre: se queda esperando la orden
    ("Jarvis", True, ""),
    ("oye jarvis", True, ""),
    # sin palabra clave: se ignora
    ("pon música", False, "pon música"),
    ("hola qué tal", False, "hola qué tal"),
    ("", False, ""),
]


@pytest.mark.parametrize("oido,despierta,orden", CASOS)
def test_reconoce_la_llamada(oido, despierta, orden):
    resultado, extraida = strip_wake_word(oido)
    assert resultado is despierta, f"«{oido}» debería {'' if despierta else 'NO '}despertarlo"
    if despierta:
        assert extraida == orden


# El reconocedor de voz rara vez escribe "jarvis" exacto.
VARIANTES = ["Yarvis, pon música", "Jarbis pon música", "Jervis, pon música",
             "Charvis pon música", "Travis, pon música"]


@pytest.mark.parametrize("oido", VARIANTES)
def test_acepta_como_suena_de_verdad(oido):
    """Si solo aceptara «jarvis» perfecto, no funcionaría casi nunca."""
    despierta, orden = strip_wake_word(oido)
    assert despierta, f"«{oido}» debería reconocerse como la palabra clave"
    assert "música" in orden


def test_conserva_tildes_y_mayusculas():
    _, orden = strip_wake_word("Oye Jarvis, pon Melón en la lista")
    assert orden == "pon Melón en la lista"


def test_la_palabra_clave_se_puede_cambiar():
    despierta, orden = strip_wake_word("Oye Viernes, pon música", wake_word="viernes")
    assert despierta and orden == "pon música"


def test_una_palabra_parecida_no_lo_despierta():
    """«Jarrón» no debe activarlo."""
    despierta, _ = strip_wake_word("el jarrón está en la mesa")
    assert not despierta
