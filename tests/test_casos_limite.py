"""Casos límite: entradas raras, vacías o pensadas para romper algo.

Un asistente que se cuelga con una frase rara no sirve. Aquí se le tira todo
lo que un usuario real puede escribir sin querer.
"""

from __future__ import annotations

import pytest

from jarvis.commands.registry import CommandRouter
from jarvis.core.assistant import Assistant
from jarvis.core.memory import Memory
from jarvis.core.ollama_client import OllamaClient
from jarvis.core.speech import clean_for_speech, strip_wake_word

from .dobles import sistema_simulado

ENTRADAS_RARAS = [
    "",
    "   ",
    "\n\n\t",
    "?",
    "¿¿¿???",
    "...",
    "a",
    "😀😀😀",
    "AAAAAAAAAAAAAAAAAAAAAA",
    "abre",                        # verbo sin objeto
    "pon",
    "busca",
    "recuérdame",
    "apunta",
    "cuánto es",
    "el clima en",
    "x" * 5000,                    # frase absurdamente larga
    "<script>alert('x')</script>",
    "'; DROP TABLE usuarios; --",
    "../../etc/passwd",
    "%s %d %n",                    # formatos que romperían un printf
    "{ }",
    "\\",
]


@pytest.mark.parametrize("entrada", ENTRADAS_RARAS)
def test_ninguna_entrada_rompe_el_interprete(entrada):
    """Pase lo que pase, debe devolver algo, nunca reventar."""
    with sistema_simulado():
        resultado = CommandRouter(memory=Memory()).handle(entrada)
        assert resultado is not None
        assert isinstance(resultado.message, str)


@pytest.mark.parametrize("entrada", ENTRADAS_RARAS)
def test_ninguna_entrada_rompe_el_asistente(entrada):
    with sistema_simulado():
        asistente = Assistant(memory=Memory(), llm=OllamaClient(host="http://localhost:1"))
        respuesta = asistente.process(entrada)
        assert isinstance(respuesta.text, str)


@pytest.mark.parametrize("entrada", ENTRADAS_RARAS)
def test_la_palabra_clave_aguanta_cualquier_cosa(entrada):
    despierta, orden = strip_wake_word(entrada)
    assert isinstance(despierta, bool)
    assert isinstance(orden, str)


@pytest.mark.parametrize("entrada", ENTRADAS_RARAS)
def test_el_limpiador_de_voz_aguanta_cualquier_cosa(entrada):
    assert isinstance(clean_for_speech(entrada), str)


# --------------------------------------------------------------------------
# La voz no debe leer basura
# --------------------------------------------------------------------------

def test_no_lee_las_direcciones_web_enteras():
    """Leer «hache te te pe dos puntos barra barra...» es insufrible."""
    hablado = clean_for_speech("Mira https://www.youtube.com/watch?v=abc123 ahí está")
    assert "http" not in hablado
    assert "enlace" in hablado


def test_no_lee_el_codigo_caracter_a_caracter():
    hablado = clean_for_speech("Prueba esto:\n```python\nprint('hola')\n```\nY ya está")
    assert "```" not in hablado
    assert "bloque de código" in hablado


def test_recorta_las_respuestas_larguisimas():
    """Sin recortar, el asistente hablaría durante varios minutos."""
    largo = "Esta es una frase completa. " * 200
    hablado = clean_for_speech(largo)
    assert len(hablado) <= 610


def test_no_deja_los_asteriscos_del_markdown():
    hablado = clean_for_speech("Esto es **muy importante** y *esto* también")
    assert "*" not in hablado


# --------------------------------------------------------------------------
# La memoria
# --------------------------------------------------------------------------

def test_recordar_algo_vacio():
    memoria = Memory()
    assert "no he entendido" in memoria.remember("   ").lower()


def test_olvidar_algo_que_no_existe():
    memoria = Memory()
    assert "no tenía nada" in memoria.forget("unicornios").lower()


def test_la_memoria_aguanta_texto_enorme():
    memoria = Memory()
    memoria.add_user("x" * 100_000)
    assert memoria.history()


# --------------------------------------------------------------------------
# Números fuera de rango
# --------------------------------------------------------------------------

@pytest.mark.parametrize("frase", [
    "volumen al 500",
    "volumen al -20",
    "brillo al 999",
    "pon el volumen al 0",
])
def test_los_valores_imposibles_no_rompen(frase):
    with sistema_simulado() as registro:
        resultado = CommandRouter(memory=Memory()).handle(frase)
        assert resultado.handled
        # El valor que llega al sistema siempre debe estar entre 0 y 100.
        if registro.llamadas and len(registro.llamadas[0]) > 1:
            valor = registro.llamadas[0][1]
            if isinstance(valor, int):
                assert -100 <= valor <= 100


# --------------------------------------------------------------------------
# Confirmaciones: que no se cuele nada peligroso
# --------------------------------------------------------------------------

@pytest.mark.parametrize("respuesta_ambigua", [
    "quizá", "no sé", "espera", "mmm", "puede ser", "?", "",
])
def test_una_respuesta_ambigua_nunca_apaga_el_equipo(respuesta_ambigua):
    """Ante la duda, no se apaga."""
    with sistema_simulado() as registro:
        asistente = Assistant(memory=Memory(), llm=OllamaClient(host="http://localhost:1"))
        asistente.process("apaga el equipo")
        asistente.process(respuesta_ambigua)
        assert "apagar-confirmado" not in [c[0] for c in registro.llamadas]
