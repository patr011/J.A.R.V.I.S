"""Notas y listas."""

from __future__ import annotations

import pytest

from jarvis.commands import notes
from jarvis.commands.notes import NoteBook, normalizar_lista
from jarvis.commands.registry import CommandRouter

from .dobles import sistema_simulado


@pytest.fixture
def libreta():
    return NoteBook()


@pytest.fixture
def router(libreta):
    return CommandRouter(notebook=libreta)


# --------------------------------------------------------------------------
# Nombres de lista
# --------------------------------------------------------------------------

@pytest.mark.parametrize("dicho,esperado", [
    ("la compra", "compra"),
    ("lista de la compra", "compra"),
    ("supermercado", "compra"),
    ("mis tareas", "tareas"),
    ("pendientes", "tareas"),
    ("libros", "libros"),
])
def test_reconoce_como_se_llama_cada_lista(dicho, esperado):
    assert normalizar_lista(dicho) == esperado


# --------------------------------------------------------------------------
# Operaciones
# --------------------------------------------------------------------------

def test_apuntar_y_leer(libreta):
    libreta.add("compra", "leche")
    libreta.add("compra", "pan")
    leido = libreta.read("compra")
    assert "leche" in leido and "pan" in leido


def test_no_apunta_dos_veces_lo_mismo(libreta):
    libreta.add("compra", "leche")
    respuesta = libreta.add("compra", "Leche")
    assert "ya estaba" in respuesta
    assert len(libreta.lists["compra"]) == 1


def test_quitar_un_elemento(libreta):
    libreta.add("compra", "leche")
    libreta.add("compra", "pan")
    libreta.remove("compra", "leche")
    assert libreta.lists["compra"] == ["pan"]


def test_quitar_algo_que_no_esta(libreta):
    libreta.add("compra", "pan")
    assert "No encuentro" in libreta.remove("compra", "caviar")


def test_borrar_la_lista_entera(libreta):
    libreta.add("compra", "pan")
    libreta.clear("compra")
    assert "compra" not in libreta.lists


def test_lista_vacia(libreta):
    assert "vacía" in libreta.read("compra")


def test_las_listas_sobreviven_al_cierre(libreta):
    libreta.add("compra", "aceite")
    assert "aceite" in NoteBook().read("compra")


def test_un_archivo_corrupto_no_impide_arrancar(tmp_path, monkeypatch):
    fichero = tmp_path / "notas.json"
    fichero.write_text("no soy json", encoding="utf-8")
    monkeypatch.setattr(notes, "NOTES_FILE", fichero)
    assert NoteBook().lists == {}


# --------------------------------------------------------------------------
# Órdenes habladas
# --------------------------------------------------------------------------

def test_apuntar_en_una_lista(router, libreta):
    resultado = router.handle("apunta leche en la lista de la compra")
    assert resultado.ok
    assert "leche" in libreta.lists["compra"]


def test_añadir_a_la_compra(router, libreta):
    router.handle("añade pan a la compra")
    assert "pan" in libreta.lists["compra"]


def test_conserva_tildes_y_mayusculas(router, libreta):
    router.handle("apunta Melón en la lista de la compra")
    assert "Melón" in libreta.lists["compra"]


def test_leer_la_lista(router, libreta):
    libreta.add("compra", "huevos")
    assert "huevos" in router.handle("lee mi lista de la compra").message


def test_quitar_por_voz(router, libreta):
    libreta.add("compra", "leche")
    router.handle("quita leche de la compra")
    assert libreta.lists["compra"] == []


def test_apuntar_sin_decir_lista(router, libreta):
    router.handle("apunta llamar al fontanero")
    assert "llamar al fontanero" in libreta.lists["notas"]


def test_ver_todas_las_listas(router, libreta):
    libreta.add("compra", "pan")
    libreta.add("tareas", "estudiar")
    mensaje = router.handle("qué listas tengo").message
    assert "compra" in mensaje and "tareas" in mensaje


# --------------------------------------------------------------------------
# Que no se pise con otros comandos
# --------------------------------------------------------------------------

def test_poner_musica_en_spotify_no_es_una_nota(libreta):
    with sistema_simulado() as registro:
        CommandRouter(notebook=libreta).handle("pon Shakira en Spotify")
        assert registro.primera == "spotify"
        assert libreta.lists == {}


def test_poner_el_volumen_no_es_una_nota(libreta):
    with sistema_simulado() as registro:
        CommandRouter(notebook=libreta).handle("pon el volumen en 75")
        assert registro.primera == "volumen-fijar"
        assert libreta.lists == {}
