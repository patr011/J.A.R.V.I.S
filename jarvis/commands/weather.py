"""El tiempo, de verdad.

Un modelo de lenguaje no sabe qué tiempo hace: fue entrenado hace meses y no
tiene forma de mirar por la ventana. Por eso el clima no se le pregunta al
modelo, se consulta aquí.

Se usa Open-Meteo, que es gratuito y NO necesita clave de API ni registro:

    https://geocoding-api.open-meteo.com/v1/search   ciudad -> coordenadas
    https://api.open-meteo.com/v1/forecast           coordenadas -> tiempo

La ciudad se guarda en la configuración la primera vez que la dices, para no
tener que repetirla.
"""

from __future__ import annotations

import requests

from ..config import config
from .base import CommandResult

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 10

# Codigos WMO que devuelve Open-Meteo, traducidos.
WEATHER_CODES: dict[int, str] = {
    0: "despejado",
    1: "casi despejado",
    2: "parcialmente nublado",
    3: "nublado",
    45: "con niebla",
    48: "con niebla helada",
    51: "con llovizna ligera",
    53: "con llovizna",
    55: "con llovizna intensa",
    56: "con llovizna helada",
    57: "con llovizna helada intensa",
    61: "con lluvia ligera",
    63: "lloviendo",
    65: "con lluvia fuerte",
    66: "con lluvia helada",
    67: "con lluvia helada fuerte",
    71: "nevando ligeramente",
    73: "nevando",
    75: "con nevada fuerte",
    77: "con granizo fino",
    80: "con chubascos ligeros",
    81: "con chubascos",
    82: "con chubascos torrenciales",
    85: "con nevadas dispersas",
    86: "con nevadas fuertes",
    95: "con tormenta",
    96: "con tormenta y granizo",
    99: "con tormenta fuerte y granizo",
}


def describe_code(code: int) -> str:
    return WEATHER_CODES.get(int(code), "con el cielo variable")


def find_city(name: str) -> dict | None:
    """Convierte el nombre de una ciudad en coordenadas."""
    try:
        response = requests.get(
            GEOCODE_URL,
            params={"name": name, "count": 1, "language": "es", "format": "json"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
    except (requests.RequestException, ValueError):
        return None
    return results[0] if results else None


def fetch_weather(latitude: float, longitude: float) -> dict | None:
    try:
        response = requests.get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": ("temperature_2m,apparent_temperature,relative_humidity_2m,"
                            "weather_code,wind_speed_10m,precipitation"),
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": 1,
                "timezone": "auto",
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return None


def get_weather(city: str = "") -> CommandResult:
    """Devuelve el tiempo actual de la ciudad indicada o de la guardada."""
    city = (city or "").strip(" ¿?.,")
    remembered = str(config.get("commands.city", "") or "")

    if not city:
        if not remembered:
            return CommandResult.fail(
                "No sé desde dónde me habla. Dígame «el tiempo en Madrid» "
                "(o su ciudad) y me la guardo para las próximas veces."
            )
        city = remembered

    place = find_city(city)
    if place is None:
        return CommandResult.fail(
            f"No he encontrado la ciudad «{city}», o no hay conexión a internet "
            "en este momento."
        )

    data = fetch_weather(place["latitude"], place["longitude"])
    if data is None:
        return CommandResult.fail(
            "No he podido consultar el servicio meteorológico. Puede que no haya conexión."
        )

    current = data.get("current") or {}
    daily = data.get("daily") or {}

    temp = current.get("temperature_2m")
    feels = current.get("apparent_temperature")
    humidity = current.get("relative_humidity_2m")
    wind = current.get("wind_speed_10m")
    code = current.get("weather_code", 0)

    def first(key: str):
        values = daily.get(key) or []
        return values[0] if values else None

    maxima, minima = first("temperature_2m_max"), first("temperature_2m_min")
    lluvia = first("precipitation_probability_max")

    nombre = place.get("name", city)
    region = place.get("admin1") or place.get("country") or ""
    ubicacion = f"{nombre}" + (f" ({region})" if region and region != nombre else "")

    partes = [f"En {ubicacion} está {describe_code(code)}"]
    if temp is not None:
        partes.append(f"con {temp:.0f} grados")
        if feels is not None and abs(feels - temp) >= 2:
            partes[-1] += f" (sensación de {feels:.0f})"
    frase = ", ".join(partes) + "."

    detalles = []
    if minima is not None and maxima is not None:
        detalles.append(f"Hoy entre {minima:.0f} y {maxima:.0f} grados.")
    if lluvia is not None:
        if lluvia >= 50:
            detalles.append(f"Probabilidad de lluvia del {lluvia:.0f} por ciento: llévese paraguas.")
        elif lluvia >= 20:
            detalles.append(f"Probabilidad de lluvia del {lluvia:.0f} por ciento.")
    if humidity is not None:
        detalles.append(f"Humedad {humidity:.0f} por ciento.")
    if wind is not None:
        detalles.append(f"Viento a {wind:.0f} kilómetros por hora.")

    mensaje = frase + (" " + " ".join(detalles) if detalles else "")

    # Se recuerda la ciudad para no tener que repetirla nunca más.
    if nombre and nombre.lower() != remembered.lower():
        config.set("commands.city", nombre)
        config.save()

    return CommandResult.done(mensaje, city=nombre, temperature=temp)
