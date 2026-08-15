"""El asistente de la clave: que no acepte basura y que escriba un .env legible.

Esto no es teoría: los tres primeros casos son errores que ya han pasado de
verdad al configurarlo por primera vez.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import poner_clave                                        # noqa: E402
from jarvis.core.secrets import parse_env_file            # noqa: E402

CLAVE_BUENA = "sk-ant-api03-" + "A" * 80


# --------------------------------------------------------------------------
# Lo que hay que rechazar
# --------------------------------------------------------------------------

@pytest.mark.parametrize("clave, motivo_esperado", [
    ("",                                    "No has pegado nada"),
    ("   ",                                 "No has pegado nada"),
    ("mi contraseña",                       "no parece una clave"),
    ("sk-ant-api03-sk-ant-api03-7jmP5rFx",  "repetida"),
    ("sk-ant-corta",                        "corta"),
    ("sk-ant-api03-" + "A" * 40 + " " + "B" * 20, "espacios"),
])
def test_se_rechaza_lo_que_no_es_una_clave(clave, motivo_esperado):
    motivo = poner_clave.validar(clave)
    assert motivo, f"debería haber rechazado «{clave[:20]}…»"
    assert motivo_esperado in motivo


def test_la_clave_pegada_dos_veces_se_detecta():
    """El error real: pegar la clave encima del ejemplo sin borrarlo.

    Queda «sk-ant-api03-sk-ant-api03-...» y la API la rechaza con un 401
    que no dice nada útil. Mejor avisar aquí.
    """
    doble = "sk-ant-api03-" + CLAVE_BUENA
    assert "repetida" in poner_clave.validar(doble)


def test_una_clave_normal_se_acepta():
    assert poner_clave.validar(CLAVE_BUENA) == ""


def test_los_espacios_de_alrededor_no_molestan():
    """Al copiar suele venir un espacio o un salto de línea de propina."""
    assert poner_clave.validar(f"  {CLAVE_BUENA}\n") == ""


# --------------------------------------------------------------------------
# El archivo que se escribe
# --------------------------------------------------------------------------

def test_el_env_se_escribe_donde_toca_y_se_puede_releer(tmp_path):
    destino = tmp_path / ".jarvis" / ".env"
    archivo = poner_clave.guardar(CLAVE_BUENA, destino)

    assert archivo == destino and archivo.is_file()
    assert parse_env_file(archivo.read_text())["ANTHROPIC_API_KEY"] == CLAVE_BUENA


def test_el_env_no_lleva_la_marca_invisible_de_windows(tmp_path):
    archivo = poner_clave.guardar(CLAVE_BUENA, tmp_path / ".env")
    crudo = archivo.read_bytes()
    assert not crudo.startswith(b"\xef\xbb\xbf"), "se ha colado un BOM"
    assert b"\r" not in crudo, "saltos de línea de Windows en un archivo ascii"


def test_la_clave_se_guarda_limpia_de_espacios(tmp_path):
    archivo = poner_clave.guardar(f"  {CLAVE_BUENA}  ", tmp_path / ".env")
    assert archivo.read_text() == f"ANTHROPIC_API_KEY={CLAVE_BUENA}\n"


def test_se_crea_la_carpeta_si_no_existe(tmp_path):
    destino = tmp_path / "ni" / "existe" / ".env"
    assert poner_clave.guardar(CLAVE_BUENA, destino).is_file()


# --------------------------------------------------------------------------
# El programa entero
# --------------------------------------------------------------------------

def test_la_clave_nunca_se_imprime_entera(monkeypatch, tmp_path, capsys):
    """El sentido de todo esto: que la clave no acabe en pantalla."""
    monkeypatch.setattr("jarvis.config.HOME_DIR", tmp_path)
    monkeypatch.setattr(poner_clave, "HOME_DIR", tmp_path)
    monkeypatch.setattr(poner_clave.getpass, "getpass", lambda *_: CLAVE_BUENA)

    assert poner_clave.main() == 0

    salida = capsys.readouterr().out
    assert CLAVE_BUENA not in salida, "¡la clave ha salido entera por pantalla!"
    assert "sk-ant-…AAAA" in salida or "…AAAA" in salida
    assert (tmp_path / ".env").is_file()


def test_con_una_clave_mala_no_se_escribe_nada(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(poner_clave, "HOME_DIR", tmp_path)
    monkeypatch.setattr(poner_clave.getpass, "getpass", lambda *_: "sk-ant-x")

    assert poner_clave.main() == 1
    assert not (tmp_path / ".env").exists()
    assert "[ERROR]" in capsys.readouterr().out


def test_cancelar_con_ctrl_c_no_rompe_nada(monkeypatch, tmp_path):
    def cancelado(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(poner_clave, "HOME_DIR", tmp_path)
    monkeypatch.setattr(poner_clave.getpass, "getpass", cancelado)

    assert poner_clave.main() == 1
    assert not (tmp_path / ".env").exists()
