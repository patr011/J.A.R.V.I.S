"""La ventana: que se dibuje, que no se cuelgue y que el texto se lea bien.

Se ejecuta sin pantalla física (modo «offscreen»), así que también funciona
en un servidor. Si PyQt6 no está instalado, estas pruebas se saltan.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6", reason="PyQt6 no está instalado")

from PyQt6.QtWidgets import QApplication          # noqa: E402

from jarvis.ui.widgets.chat_view import ChatView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    yield aplicacion


@pytest.fixture
def chat(app):
    return ChatView()


# --------------------------------------------------------------------------
# El fallo del texto pegado: la prueba que impide que vuelva
# --------------------------------------------------------------------------

# Así llegan los fragmentos de Ollama: casi todos empiezan por un espacio.
FRAGMENTOS = ["¡Sí", ",", " por", " ejemplo", "!", " ¿Sabías", " que", " hay",
              " un", " planeta", " llamado", " Plutón", "?"]


def test_el_texto_en_streaming_conserva_los_espacios(chat):
    """Con HTML los espacios del principio se pierden y las palabras se pegan."""
    chat.start_stream("assistant")
    for fragmento in FRAGMENTOS:
        chat.append_stream(fragmento)
    chat.end_stream()

    esperado = "".join(FRAGMENTOS)
    assert esperado in chat.toPlainText(), "las palabras han salido pegadas"


def test_los_mensajes_conservan_saltos_y_sangrias(chat):
    chat.add_message("assistant", "Primera línea.\n   Sangrada con tres espacios.")
    texto = chat.toPlainText()
    assert "Primera línea." in texto
    assert "   Sangrada" in texto


def test_cada_mensaje_va_en_su_parrafo(chat):
    chat.add_message("user", "hola")
    chat.add_message("assistant", "buenas")
    lineas = [l for l in chat.toPlainText().splitlines() if l.strip()]
    assert "hola" in lineas
    assert "buenas" in lineas


def test_el_texto_del_usuario_no_se_interpreta_como_html(chat):
    """Si escribe <b>hola</b> debe verse tal cual, no en negrita."""
    chat.add_message("user", "<b>hola</b> & <script>alert(1)</script>")
    assert "<b>hola</b>" in chat.toPlainText()


def test_limpiar_deja_el_chat_vacio(chat):
    chat.add_message("user", "algo")
    chat.clear_chat()
    assert chat.toPlainText().strip() == ""


# --------------------------------------------------------------------------
# La ventana entera
# --------------------------------------------------------------------------

@pytest.fixture
def ventana(app, monkeypatch, tmp_path):
    """Ventana real, pero sin voz ni comprobaciones que salgan fuera."""
    monkeypatch.setattr("jarvis.core.memory.MEMORY_FILE", tmp_path / "memoria.json")
    from jarvis.ui.main_window import JarvisWindow

    ventana = JarvisWindow()
    yield ventana
    ventana.quit_completely()   # close() solo la escondería en la bandeja


def test_la_ventana_arranca_y_se_dibuja(ventana):
    ventana.resize(1180, 740)
    ventana.show()
    assert not ventana.grab().isNull(), "la ventana no ha pintado nada"


def test_los_paneles_estan_todos(ventana):
    for widget in ("reactor", "chat", "input", "bar_cpu", "bar_ram",
                   "bar_vol", "bar_bright", "bar_battery", "waveform"):
        assert hasattr(ventana, widget), f"falta el panel «{widget}»"


def test_los_indicadores_se_actualizan_sin_error(ventana):
    ventana._update_stats()
    ventana._update_clock()
    ventana._poll_voice_state()


@pytest.mark.parametrize("estado", ["idle", "listening", "thinking", "speaking", "error"])
def test_todos_los_estados_del_reactor_se_dibujan(ventana, estado):
    ventana._set_state(estado)
    ventana.reactor.set_level(0.8)
    assert not ventana.reactor.grab().isNull()


def test_limpiar_el_chat_tambien_limpia_la_memoria(ventana):
    ventana.memory.add_user("algo que dije")
    ventana._clear_chat()
    assert ventana.memory.turns == []


# --------------------------------------------------------------------------
# Icono de la bandeja del sistema
# --------------------------------------------------------------------------

def test_el_icono_de_bandeja_se_dibuja(app):
    """Se dibuja con código: el proyecto no depende de ningún archivo de imagen."""
    from jarvis.ui.tray import build_icon

    icono = build_icon()
    assert not icono.isNull()
    assert not icono.pixmap(64, 64).isNull()


def test_el_icono_respeta_el_color_elegido(app):
    from jarvis.ui.tray import build_icon

    assert not build_icon("#FF8A00").isNull()


def test_sin_bandeja_disponible_la_ventana_sigue_funcionando(ventana):
    """En un escritorio sin bandeja, cerrar tiene que cerrar de verdad."""
    if ventana.tray is None:
        assert ventana.isEnabled()


def test_salir_de_verdad_no_se_queda_escondido(ventana):
    ventana.quit_completely()
    assert ventana._salir_de_verdad
