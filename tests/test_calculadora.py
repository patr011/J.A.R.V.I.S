"""La calculadora: resultados correctos y, sobre todo, segura."""

from __future__ import annotations

import pytest

from jarvis.commands import calc

CUENTAS = [
    ("cuánto es 7 + 39", "46"),
    ("cuanto es 100 - 58", "42"),
    ("calcula 12 * 12", "144"),
    ("cuánto es 7 por 8", "56"),
    ("cuanto es 100 entre 4", "25"),
    ("cuánto es 10 dividido entre 4", "2.5"),
    ("el 20 por ciento de 350", "70"),
    ("raiz cuadrada de 144", "12"),
    ("cuanto es 2 elevado a 10", "1024"),
    ("cuanto es 15 + 3 * 2", "21"),          # prioridad de operaciones
    ("cuanto es (15 + 3) * 2", "36"),
]


@pytest.mark.parametrize("frase,esperado", CUENTAS)
def test_las_cuentas_salen_bien(frase, esperado):
    resultado = calc.calculate(frase)
    assert resultado.ok, resultado.message
    assert resultado.message.split("=")[-1].strip() == esperado


def test_dividir_entre_cero_no_rompe():
    resultado = calc.calculate("cuanto es 10 entre 0")
    assert not resultado.ok
    assert "cero" in resultado.message


def test_exponente_gigante_no_cuelga_el_programa():
    """2 elevado a un millón tardaría minutos y congelaría la ventana."""
    resultado = calc.calculate("2 ** 999999")
    assert not resultado.ok


# --------------------------------------------------------------------------
# Seguridad: la calculadora NO debe ejecutar código
# --------------------------------------------------------------------------

CODIGO_MALICIOSO = [
    "__import__('os').system('calc')",
    "open('C:/Windows/System32/config/SAM').read()",
    "().__class__.__bases__[0].__subclasses__()",
    "exec('print(1)')",
    "[x for x in range(10)]",
]


@pytest.mark.parametrize("intento", CODIGO_MALICIOSO)
def test_no_ejecuta_codigo(intento):
    """Por eso no se usa eval(): esto ejecutaría cualquier cosa."""
    assert not calc.calculate(intento).ok


NO_SON_CUENTAS = [
    "cuentame un chiste",
    "quien invento el telefono 2 veces",
    "que opinas de python 3",
    "hola que tal",
    "pon la cancion 99 problems",
]


@pytest.mark.parametrize("frase", NO_SON_CUENTAS)
def test_no_confunde_frases_con_cuentas(frase):
    assert calc.looks_like_math(frase) is False
