"""El asistente de la clave: que no acepte basura y que no pise lo ya guardado.

Esto no es teoría: los primeros casos son errores que ya han pasado de verdad
al configurarlo por primera vez.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import poner_clave                                        # noqa: E402
from jarvis.core.secrets import parse_env_file            # noqa: E402

CLAUDE = poner_clave.SERVICIOS["claude"]
VOZ = poner_clave.SERVICIOS["voz"]

CLAVE_BUENA = "sk-ant-api03-" + "A" * 80
CLAVE_VOZ = "sk_" + "b" * 40


# --------------------------------------------------------------------------
# Lo que hay que rechazar
# --------------------------------------------------------------------------

@pytest.mark.parametrize("clave, motivo_esperado", [
    ("",                                    "No has pegado nada"),
    ("   ",                                 "No has pegado nada"),
    ("mi contraseña",                       "espacios"),
    ("chorizo",                             "no parece una clave"),
    ("sk-ant-api03-sk-ant-api03-7jmP5rFx",  "repetida"),
    ("sk-ant-corta",                        "corta"),
])
def test_se_rechaza_lo_que_no_es_una_clave(clave, motivo_esperado):
    motivo = poner_clave.validar(clave, CLAUDE)
    assert motivo, f"debería haber rechazado «{clave[:20]}…»"
    assert motivo_esperado in motivo


def test_la_clave_pegada_dos_veces_se_detecta():
    """El error real: pegar la clave encima del ejemplo sin borrarlo.

    Queda «sk-ant-api03-sk-ant-api03-...» y la API la rechaza con un 401
    que no dice nada útil. Mejor avisar aquí.
    """
    doble = "sk-ant-api03-" + CLAVE_BUENA
    assert "repetida" in poner_clave.validar(doble, CLAUDE)


def test_una_clave_normal_se_acepta():
    assert poner_clave.validar(CLAVE_BUENA, CLAUDE) == ""


def test_los_espacios_de_alrededor_no_molestan():
    """Al copiar suele venir un espacio o un salto de línea de propina."""
    assert poner_clave.validar(f"  {CLAVE_BUENA}\n", CLAUDE) == ""


def test_a_elevenlabs_no_se_le_exige_prefijo():
    """Sus claves han cambiado de formato: rechazar una válida sería peor."""
    assert poner_clave.validar(CLAVE_VOZ, VOZ) == ""
    assert poner_clave.validar("a" * 32, VOZ) == ""


def test_a_elevenlabs_si_se_le_exige_que_no_sea_basura():
    assert "corta" in poner_clave.validar("sk_123", VOZ)


# --------------------------------------------------------------------------
# El archivo que se escribe
# --------------------------------------------------------------------------

def test_el_env_se_escribe_donde_toca_y_se_puede_releer(tmp_path):
    destino = tmp_path / ".jarvis" / ".env"
    archivo = poner_clave.guardar(CLAVE_BUENA, CLAUDE, destino)

    assert archivo == destino and archivo.is_file()
    assert parse_env_file(archivo.read_text())["ANTHROPIC_API_KEY"] == CLAVE_BUENA


def test_guardar_la_voz_no_borra_la_de_claude(tmp_path):
    """El fallo evidente de sobrescribir el archivo entero.

    Dejaría al asistente sin cerebro por haber cambiado la voz.
    """
    destino = tmp_path / ".env"
    poner_clave.guardar(CLAVE_BUENA, CLAUDE, destino)
    poner_clave.guardar(CLAVE_VOZ, VOZ, destino)

    variables = parse_env_file(destino.read_text())
    assert variables["ANTHROPIC_API_KEY"] == CLAVE_BUENA
    assert variables["ELEVENLABS_API_KEY"] == CLAVE_VOZ


def test_volver_a_guardar_reemplaza_la_clave_vieja(tmp_path):
    destino = tmp_path / ".env"
    poner_clave.guardar(CLAVE_BUENA, CLAUDE, destino)
    nueva = "sk-ant-api03-" + "Z" * 80
    poner_clave.guardar(nueva, CLAUDE, destino)

    texto = destino.read_text()
    assert texto.count("ANTHROPIC_API_KEY") == 1
    assert parse_env_file(texto)["ANTHROPIC_API_KEY"] == nueva


def test_el_env_no_lleva_la_marca_invisible_de_windows(tmp_path):
    archivo = poner_clave.guardar(CLAVE_BUENA, CLAUDE, tmp_path / ".env")
    crudo = archivo.read_bytes()
    assert not crudo.startswith(b"\xef\xbb\xbf"), "se ha colado un BOM"
    assert b"\r" not in crudo, "saltos de línea de Windows en un archivo ascii"


def test_la_clave_se_guarda_limpia_de_espacios(tmp_path):
    archivo = poner_clave.guardar(f"  {CLAVE_BUENA}  ", CLAUDE, tmp_path / ".env")
    assert archivo.read_text() == f"ANTHROPIC_API_KEY={CLAVE_BUENA}\n"


def test_se_crea_la_carpeta_si_no_existe(tmp_path):
    destino = tmp_path / "ni" / "existe" / ".env"
    assert poner_clave.guardar(CLAVE_BUENA, CLAUDE, destino).is_file()


# --------------------------------------------------------------------------
# Elegir servicio
# --------------------------------------------------------------------------

@pytest.mark.parametrize("argumento, esperado", [
    ("claude", "claude"), ("anthropic", "claude"), ("IA", "claude"),
    ("voz", "voz"), ("elevenlabs", "voz"), ("Eleven", "voz"),
])
def test_se_puede_decir_por_argumento(argumento, esperado):
    assert poner_clave.elegir_servicio([argumento]) is poner_clave.SERVICIOS[esperado]


def test_un_argumento_raro_no_adivina_nada(capsys):
    assert poner_clave.elegir_servicio(["pepe"]) is None
    assert "No sé qué es" in capsys.readouterr().out


# --------------------------------------------------------------------------
# El programa entero
# --------------------------------------------------------------------------

def test_la_clave_nunca_se_imprime_entera(monkeypatch, tmp_path, capsys):
    """El sentido de todo esto: que la clave no acabe en pantalla."""
    monkeypatch.setattr(poner_clave, "HOME_DIR", tmp_path)
    monkeypatch.setattr(poner_clave.getpass, "getpass", lambda *_: CLAVE_BUENA)

    assert poner_clave.main(["claude"]) == 0

    salida = capsys.readouterr().out
    assert CLAVE_BUENA not in salida, "¡la clave ha salido entera por pantalla!"
    assert "…AAAA" in salida
    assert (tmp_path / ".env").is_file()


def test_con_una_clave_mala_no_se_escribe_nada(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(poner_clave, "HOME_DIR", tmp_path)
    monkeypatch.setattr(poner_clave.getpass, "getpass", lambda *_: "sk-ant-x")

    assert poner_clave.main(["claude"]) == 1
    assert not (tmp_path / ".env").exists()
    assert "[ERROR]" in capsys.readouterr().out


def test_cancelar_con_ctrl_c_no_rompe_nada(monkeypatch, tmp_path):
    def cancelado(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(poner_clave, "HOME_DIR", tmp_path)
    monkeypatch.setattr(poner_clave.getpass, "getpass", cancelado)

    assert poner_clave.main(["claude"]) == 1
    assert not (tmp_path / ".env").exists()


def test_guardar_la_de_la_voz_explica_el_siguiente_paso(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(poner_clave, "HOME_DIR", tmp_path)
    monkeypatch.setattr(poner_clave.getpass, "getpass", lambda *_: CLAVE_VOZ)

    assert poner_clave.main(["voz"]) == 0
    salida = capsys.readouterr().out
    assert "Buscar mis voces" in salida
    assert CLAVE_VOZ not in salida
