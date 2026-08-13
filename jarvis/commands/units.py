"""Conversión de unidades, sin internet.

    «cuántos kilómetros son 5 millas»
    «25 grados centígrados en fahrenheit»
    «3 libras en kilos»
    «convierte 2 horas a minutos»

Se hace aquí y no con el modelo de lenguaje por la misma razón que las
cuentas: un modelo se equivoca de vez en cuando, y una conversión mal hecha
puede acabar en una receta arruinada o en un tornillo del tamaño que no es.
"""

from __future__ import annotations

import re

from .base import CommandResult, normalize

# Cada unidad se guarda con su factor respecto a una unidad base por familia.
#   longitud -> metros    peso -> gramos    volumen -> litros
#   tiempo   -> segundos  datos -> bytes    velocidad -> m/s
FAMILIAS: dict[str, dict[str, float]] = {
    "longitud": {
        "milimetro": 0.001, "milimetros": 0.001, "mm": 0.001,
        "centimetro": 0.01, "centimetros": 0.01, "cm": 0.01,
        "metro": 1.0, "metros": 1.0, "m": 1.0,
        "kilometro": 1000.0, "kilometros": 1000.0, "km": 1000.0,
        "pulgada": 0.0254, "pulgadas": 0.0254,
        "pie": 0.3048, "pies": 0.3048,
        "yarda": 0.9144, "yardas": 0.9144,
        "milla": 1609.344, "millas": 1609.344,
        "milla nautica": 1852.0, "millas nauticas": 1852.0,
    },
    "peso": {
        "miligramo": 0.001, "miligramos": 0.001, "mg": 0.001,
        "gramo": 1.0, "gramos": 1.0, "g": 1.0,
        "kilo": 1000.0, "kilos": 1000.0, "kilogramo": 1000.0,
        "kilogramos": 1000.0, "kg": 1000.0,
        "tonelada": 1_000_000.0, "toneladas": 1_000_000.0,
        "libra": 453.59237, "libras": 453.59237, "lb": 453.59237,
        "onza": 28.349523125, "onzas": 28.349523125, "oz": 28.349523125,
    },
    "volumen": {
        "mililitro": 0.001, "mililitros": 0.001, "ml": 0.001,
        "litro": 1.0, "litros": 1.0, "l": 1.0,
        "galon": 3.785411784, "galones": 3.785411784,
        "taza": 0.2366, "tazas": 0.2366,
        "cucharada": 0.0148, "cucharadas": 0.0148,
    },
    "tiempo": {
        "segundo": 1.0, "segundos": 1.0, "s": 1.0,
        "minuto": 60.0, "minutos": 60.0, "min": 60.0,
        "hora": 3600.0, "horas": 3600.0, "h": 3600.0,
        "dia": 86400.0, "dias": 86400.0,
        "semana": 604800.0, "semanas": 604800.0,
        "mes": 2_592_000.0, "meses": 2_592_000.0,
        "año": 31_536_000.0, "años": 31_536_000.0,
    },
    "datos": {
        "byte": 1.0, "bytes": 1.0,
        "kilobyte": 1024.0, "kilobytes": 1024.0, "kb": 1024.0,
        "megabyte": 1024.0 ** 2, "megabytes": 1024.0 ** 2, "mb": 1024.0 ** 2,
        "gigabyte": 1024.0 ** 3, "gigabytes": 1024.0 ** 3, "gb": 1024.0 ** 3,
        "terabyte": 1024.0 ** 4, "terabytes": 1024.0 ** 4, "tb": 1024.0 ** 4,
    },
    "velocidad": {
        "kilometros por hora": 1 / 3.6, "km/h": 1 / 3.6, "kmh": 1 / 3.6,
        "metros por segundo": 1.0, "m/s": 1.0,
        "millas por hora": 0.44704, "mph": 0.44704,
        "nudo": 0.514444, "nudos": 0.514444,
    },
}

# La temperatura no se convierte multiplicando: necesita su propia función.
TEMPERATURAS = {
    "celsius": "c", "centigrados": "c", "centigrado": "c", "grados": "c", "c": "c",
    "fahrenheit": "f", "f": "f",
    "kelvin": "k", "k": "k",
}


def _familia_de(unidad: str) -> str | None:
    for nombre, tabla in FAMILIAS.items():
        if unidad in tabla:
            return nombre
    return None


def convertir_temperatura(valor: float, desde: str, hacia: str) -> float:
    grados_c = valor
    if desde == "f":
        grados_c = (valor - 32) * 5 / 9
    elif desde == "k":
        grados_c = valor - 273.15

    if hacia == "f":
        return grados_c * 9 / 5 + 32
    if hacia == "k":
        return grados_c + 273.15
    return grados_c


def _formatear(valor: float) -> str:
    if abs(valor) >= 1000:
        return f"{valor:,.2f}".replace(",", " ").rstrip("0").rstrip(".")
    if valor == int(valor):
        return str(int(valor))
    return f"{valor:.4f}".rstrip("0").rstrip(".")


# «5 millas en kilometros», «convierte 3 libras a kilos», «cuantos km son 5 millas»
PATRON = re.compile(
    r"(?:cuant[oa]s?\s+(?P<destino1>[\w/ ]+?)\s+(?:son|hay en|es)\s+)?"
    r"(?P<valor>-?\d+(?:[.,]\d+)?)\s*"
    r"(?P<origen>[\w/°]+(?:\s+(?:por\s+\w+|nauticas?))?)"
    r"(?:\s+(?:a|en|to)\s+(?P<destino2>[\w/ ]+))?"
)


def convert(text: str) -> CommandResult | None:
    """Convierte si la frase es una conversión; None si no lo es."""
    norm = normalize(text)
    norm = re.sub(r"^(convierte|convertir|cuanto es|pasa|pasar)\s+", "", norm)
    norm = norm.replace("°", " grados ")

    # «25 grados centigrados» es una sola unidad de dos palabras: se reduce a
    # una sola para que el patron la reconozca como tal.
    for expresion, unidad in (
        (r"\bgrados?\s+(centigrados?|celsius)\b", "celsius"),
        (r"\bgrados?\s+fahrenheit\b", "fahrenheit"),
        (r"\bgrados?\s+kelvin\b", "kelvin"),
        (r"\bkelvin\s+grados?\b", "kelvin"),
    ):
        norm = re.sub(expresion, unidad, norm)

    coincidencia = PATRON.search(norm)
    if not coincidencia:
        return None

    try:
        valor = float(coincidencia.group("valor").replace(",", "."))
    except (TypeError, ValueError):
        return None

    origen = (coincidencia.group("origen") or "").strip()
    destino = (coincidencia.group("destino2") or coincidencia.group("destino1") or "").strip()
    destino = re.sub(r"\b(grados|de)\b", " ", destino).strip() or destino
    if not origen or not destino:
        return None

    # --- temperatura ---
    origen_temp = TEMPERATURAS.get(origen)
    destino_temp = TEMPERATURAS.get(destino)
    if origen_temp and destino_temp:
        resultado = convertir_temperatura(valor, origen_temp, destino_temp)
        nombres = {"c": "grados Celsius", "f": "grados Fahrenheit", "k": "kelvin"}
        return CommandResult.done(
            f"{_formatear(valor)} {nombres[origen_temp]} son "
            f"{_formatear(round(resultado, 2))} {nombres[destino_temp]}.",
            result=resultado)

    # --- el resto ---
    familia_origen = _familia_de(origen)
    familia_destino = _familia_de(destino)
    if not familia_origen or not familia_destino:
        return None
    if familia_origen != familia_destino:
        return CommandResult.fail(
            f"No puedo convertir {origen} en {destino}: son magnitudes distintas.")

    tabla = FAMILIAS[familia_origen]
    resultado = valor * tabla[origen] / tabla[destino]
    return CommandResult.done(
        f"{_formatear(valor)} {origen} son {_formatear(round(resultado, 6))} {destino}.",
        result=resultado)


def looks_like_conversion(text: str) -> bool:
    """¿Merece la pena intentar convertir esta frase?"""
    norm = normalize(text)
    if not re.search(r"\d", norm):
        return False
    if not re.search(r"\b(a|en|to|son|convierte|convertir|pasa)\b", norm):
        return False
    todas = set(TEMPERATURAS)
    for tabla in FAMILIAS.values():
        todas.update(tabla)
    return any(re.search(rf"\b{re.escape(u)}\b", norm) for u in todas if len(u) > 1)
