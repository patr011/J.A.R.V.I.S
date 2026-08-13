"""Que cada frase acabe en el comando correcto.

Esta es la prueba más importante del proyecto: si el intérprete se equivoca,
«apaga la música» podría apagar el ordenador.
"""

from __future__ import annotations

import pytest

from jarvis.commands.registry import CommandRouter
from jarvis.core.memory import Memory

from .dobles import sistema_simulado

# (lo que dice el usuario, comando que debe ejecutarse)
FRASES = [
    # --- aplicaciones ---
    ("abre Chrome", "app"),
    ("abre la calculadora", "app"),
    ("inicia Spotify", "app"),
    ("ejecuta word", "app"),
    ("arranca el bloc de notas", "app"),
    # --- archivos ---
    ("abre la carpeta descargas", "carpeta"),
    ("abre el archivo presupuesto", "archivo"),
    ("busca el archivo informe anual", "buscar"),
    # --- web ---
    ("abre YouTube", "web"),
    ("abre google.com", "web"),
    ("abre la pagina de netflix", "web"),
    ("busca gatos en Google", "buscar-web"),
    # --- musica ---
    ("pon Bohemian Rhapsody", "cancion"),
    ("pon la cancion Despacito", "cancion"),
    ("reproduce Numb de Linkin Park", "cancion"),
    ("ponme musica de rock", "cancion"),
    ("pon Shakira en Spotify", "spotify"),
    ("pon musica", "musica"),
    ("play", "play-pausa"),
    ("pausa", "play-pausa"),
    ("siguiente cancion", "siguiente"),
    ("cancion anterior", "anterior"),
    # --- volumen y brillo ---
    ("sube el volumen", "volumen-cambiar"),
    ("baja el volumen 20", "volumen-cambiar"),
    ("volumen al 40", "volumen-fijar"),
    ("pon el volumen en 75", "volumen-fijar"),
    ("silencia el sonido", "silenciar"),
    ("sube el brillo", "brillo-cambiar"),
    ("brillo al 70", "brillo-fijar"),
    ("pon el brillo al 40", "brillo-fijar"),
    # --- energia ---
    ("apaga el equipo", "apagar"),
    ("apaga la computadora", "apagar"),
    ("reinicia el ordenador", "reiniciar"),
    ("suspende el equipo", "suspender"),
    ("bloquea el equipo", "bloquear"),
    ("cancela el apagado", "cancelar-apagado"),
    ("cierra la sesion", "cerrar-sesion"),
    # --- informacion ---
    ("que tiempo hace", "clima"),
    ("el clima en Valencia", "clima"),
    ("va a llover", "clima"),
]


@pytest.mark.parametrize("frase,esperado", FRASES)
def test_la_frase_llega_al_comando_correcto(frase, esperado):
    with sistema_simulado() as registro:
        CommandRouter(memory=Memory()).handle(frase)
        assert registro.primera == esperado, (
            f"«{frase}» acabó en «{registro.primera}» y debía ir a «{esperado}»")


# Frases que NO son órdenes: tienen que llegar al modelo de lenguaje.
CONVERSACION = [
    "quien invento el telefono",
    "cuentame un chiste",
    "explicame la fotosintesis",
    "que opinas de python",
    "hola, como estas",
    "escribeme un correo de disculpa",
    "cuanto tiempo llevo hablando contigo",
    "hace tiempo que no programo",
]


@pytest.mark.parametrize("frase", CONVERSACION)
def test_la_conversacion_va_al_modelo(frase):
    with sistema_simulado():
        assert CommandRouter(memory=Memory()).handle(frase).handled is False, (
            f"«{frase}» no es una orden y no debería capturarla ningún comando")


# --------------------------------------------------------------------------
# Casos peligrosos: lo que NUNCA debe pasar
# --------------------------------------------------------------------------

NO_DEBE_APAGAR = [
    "apaga la musica",
    "apaga la luz del salon",
    "baja el volumen y apaga la cancion",
    "apaga la pantalla",
]


@pytest.mark.parametrize("frase", NO_DEBE_APAGAR)
def test_apagar_otra_cosa_no_apaga_el_equipo(frase):
    with sistema_simulado() as registro:
        CommandRouter(memory=Memory()).handle(frase)
        ejecutados = [c[0] for c in registro.llamadas]
        assert "apagar" not in ejecutados, f"«{frase}» ha intentado apagar el equipo"
        assert "apagar-confirmado" not in ejecutados


def test_apagar_siempre_pide_confirmacion():
    """Nada de apagar a la primera: primero se pregunta."""
    with sistema_simulado() as registro:
        resultado = CommandRouter(memory=Memory()).handle("apaga el equipo")
        assert resultado.needs_confirmation, "el apagado debe pedir confirmación"
        ejecutados = [c[0] for c in registro.llamadas]
        assert "apagar-confirmado" not in ejecutados, "¡se ha apagado sin confirmar!"
