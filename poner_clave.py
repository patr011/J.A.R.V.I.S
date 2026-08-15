"""Guarda las claves de API sin que aparezcan en pantalla.

Se usa con doble clic en  poner_clave.bat , o desde la terminal:

    python poner_clave.py              -> pregunta cuál quieres guardar
    python poner_clave.py claude       -> directamente la de Claude
    python poner_clave.py voz          -> directamente la de ElevenLabs

Por qué existe: la forma «obvia» de crear el .env es escribir la clave en la
consola. Es la peor de todas. Queda a la vista de quien pase por detrás, sale
entera en cualquier captura de pantalla y, encima, PowerShell la guarda en su
archivo de historial. Aquí se pide con getpass (no se ve nada al teclear ni
al pegar) y solo se confirma enmascarada.
"""

from __future__ import annotations

import getpass
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jarvis.config import HOME_DIR                            # noqa: E402
from jarvis.core.secrets import (API_KEY_VAR, ELEVENLABS_KEY_VAR,  # noqa: E402
                                 mask_api_key, parse_env_file)


@dataclass
class Servicio:
    """Los datos de una clave: dónde se saca y qué pinta tiene."""

    nombre: str
    variable: str
    consola: str
    prefijo: str = ""           # vacío = no se exige ninguno
    para_que: str = ""


SERVICIOS = {
    "claude": Servicio(
        nombre="Claude (Anthropic)",
        variable=API_KEY_VAR,
        consola="https://console.anthropic.com/settings/keys",
        prefijo="sk-ant-",
        para_que="es la que hace pensar al asistente. Sin ella no conversa.",
    ),
    "voz": Servicio(
        nombre="ElevenLabs",
        variable=ELEVENLABS_KEY_VAR,
        consola="https://elevenlabs.io/app/settings/api-keys",
        # Las claves de ElevenLabs han cambiado de formato con los años, asi
        # que no se exige prefijo: rechazar una valida seria peor que dejar
        # pasar una mal copiada, que ademas se detecta al primer intento.
        para_que="es opcional: solo cambia la voz con la que habla.",
    ),
}


def validar(clave: str, servicio: Servicio) -> str:
    """Devuelve el motivo por el que la clave no vale, o '' si está bien.

    Los errores que se ven de verdad: no pegar nada, pegar algo que no es una
    clave, y dejarse el ejemplo delante de la clave buena (con lo que el
    prefijo acaba repetido).
    """
    clave = clave.strip()
    if not clave:
        return "No has pegado nada."
    if any(c.isspace() for c in clave):
        return "La clave lleva espacios o saltos de línea por medio."
    if servicio.prefijo:
        if clave.count(servicio.prefijo) > 1:
            return (f"La clave aparece repetida: el texto lleva "
                    f"«{servicio.prefijo}» dos veces.\n"
                    "   Copia solo la clave, sin dejar delante el ejemplo.")
        if not clave.startswith(servicio.prefijo):
            return (f"Eso no parece una clave de {servicio.nombre}: tendría que "
                    f"empezar por «{servicio.prefijo}».\n"
                    "   Comprueba que la copiaste entera.")
    if len(clave) < 20:
        return ("La clave se ha quedado corta; parece que falta un trozo.\n"
                "   Cópiala otra vez completa.")
    return ""


def guardar(clave: str, servicio: Servicio, destino: Path | None = None) -> Path:
    """Escribe la clave en el .env conservando las demás.

    Importante lo de conservar: guardar la clave de la voz no puede borrar la
    de Claude y dejar el asistente mudo de pensamiento.
    """
    archivo = destino or (HOME_DIR / ".env")
    archivo.parent.mkdir(parents=True, exist_ok=True)

    variables: dict[str, str] = {}
    if archivo.is_file():
        try:
            variables = parse_env_file(archivo.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            variables = {}
    variables[servicio.variable] = clave.strip()

    lineas = [f"{nombre}={valor}" for nombre, valor in variables.items()]
    # Sin BOM y con saltos de linea normales: asi lo lee cualquier cosa.
    archivo.write_text("\n".join(lineas) + "\n", encoding="ascii", newline="\n")
    try:
        archivo.chmod(0o600)      # en Windows no hace nada, pero no molesta
    except OSError:
        pass
    return archivo


def elegir_servicio(argumentos: list[str]) -> Servicio | None:
    """Qué clave se va a guardar, por argumento o preguntando."""
    if argumentos:
        clave = argumentos[0].strip().lower()
        alias = {"claude": "claude", "anthropic": "claude", "ia": "claude",
                 "voz": "voz", "elevenlabs": "voz", "eleven": "voz"}
        if clave in alias:
            return SERVICIOS[alias[clave]]
        print(f"\n  No sé qué es «{argumentos[0]}». Usa: claude  o  voz")
        return None

    print("  ¿Qué clave quieres guardar?")
    print()
    for numero, (_, servicio) in enumerate(SERVICIOS.items(), start=1):
        print(f"    {numero}. {servicio.nombre} — {servicio.para_que}")
    print()
    try:
        elegido = input("  Escribe 1 o 2 y pulsa Enter: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if elegido == "1":
        return SERVICIOS["claude"]
    if elegido == "2":
        return SERVICIOS["voz"]
    print("\n  No has elegido ninguna de las dos.")
    return None


def main(argumentos: list[str] | None = None) -> int:
    argumentos = argumentos if argumentos is not None else sys.argv[1:]

    print()
    print("  ============================================================")
    print("    J.A.R.V.I.S.  -  Guardar una clave de API")
    print("  ============================================================")
    print()

    servicio = elegir_servicio(argumentos)
    if servicio is None:
        print("  No se ha guardado nada.")
        return 1

    print()
    print(f"  Clave de {servicio.nombre}")
    print(f"  Se saca en:  {servicio.consola}")
    print()
    print("  Pégala aquí debajo y pulsa Enter.")
    print("  NO se verá nada al pegarla, ni siquiera asteriscos: es a")
    print("  propósito, para que no quede a la vista ni en el historial.")
    print()

    try:
        clave = getpass.getpass("  Clave: ")
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelado. No se ha guardado nada.")
        return 1

    motivo = validar(clave, servicio)
    if motivo:
        print(f"\n  [ERROR] {motivo}")
        print("\n  No se ha guardado nada. Vuelve a ejecutar este archivo")
        print("  cuando tengas la clave copiada.")
        return 1

    archivo = guardar(clave, servicio)
    print(f"\n  [OK] Clave de {servicio.nombre} guardada en:  {archivo}")
    print(f"       {mask_api_key(clave.strip())}   "
          f"({len(clave.strip())} caracteres)")
    print()
    print("  Ese archivo está fuera del proyecto, así que no se sube a")
    print("  GitHub ni por accidente.")
    print()
    if servicio.variable == ELEVENLABS_KEY_VAR:
        print("  Ahora abre el asistente, entra en Ajustes (Ctrl+,) → Voz,")
        print("  elige «ElevenLabs» y pulsa «Buscar mis voces».")
    else:
        print("  Ahora comprueba que la API responde:")
        print("      python main.py --check")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
