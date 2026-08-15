"""Guarda la clave de la API de Claude sin que aparezca en pantalla.

Se usa con doble clic en  poner_clave.bat , o desde la terminal:

    python poner_clave.py

Por qué existe: la forma «obvia» de crear el .env es escribir la clave en la
consola. Es la peor de todas. Queda a la vista de quien pase por detrás, sale
entera en cualquier captura de pantalla y, encima, PowerShell la guarda en su
archivo de historial. Aquí se pide con getpass (no se ve nada al teclear ni
al pegar) y solo se confirma enmascarada.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jarvis.config import HOME_DIR                    # noqa: E402
from jarvis.core.secrets import API_KEY_VAR, mask_api_key   # noqa: E402

PREFIJO = "sk-ant-"
CONSOLA = "https://console.anthropic.com/settings/keys"


def validar(clave: str) -> str:
    """Devuelve el motivo por el que la clave no vale, o '' si está bien.

    Los tres errores que se ven de verdad: no pegar nada, pegar algo que no
    es una clave, y dejarse el ejemplo delante de la clave buena (con lo que
    el «sk-ant-» acaba repetido).
    """
    clave = clave.strip()
    if not clave:
        return "No has pegado nada."
    if clave.count(PREFIJO) > 1:
        return ("La clave aparece repetida: el texto lleva «sk-ant-» dos veces.\n"
                "   Copia solo la clave, sin dejar delante el ejemplo.")
    if not clave.startswith(PREFIJO):
        return (f"Eso no parece una clave de Anthropic: tendría que empezar "
                f"por «{PREFIJO}».\n   Comprueba que la copiaste entera.")
    if len(clave) < 40:
        return ("La clave se ha quedado corta; parece que falta un trozo.\n"
                "   Cópiala otra vez completa.")
    if any(c.isspace() for c in clave):
        return "La clave lleva espacios o saltos de línea por medio."
    return ""


def guardar(clave: str, destino: Path | None = None) -> Path:
    """Escribe el .env con la clave. Devuelve la ruta del archivo."""
    archivo = destino or (HOME_DIR / ".env")
    archivo.parent.mkdir(parents=True, exist_ok=True)
    # Sin BOM y con saltos de línea normales: así lo lee cualquier cosa.
    archivo.write_text(f"{API_KEY_VAR}={clave.strip()}\n",
                       encoding="ascii", newline="\n")
    try:
        archivo.chmod(0o600)      # en Windows no hace nada, pero no molesta
    except OSError:
        pass
    return archivo


def main() -> int:
    print()
    print("  ============================================================")
    print("    J.A.R.V.I.S.  -  Guardar la clave de la API de Claude")
    print("  ============================================================")
    print()
    print(f"  Tu clave se saca en:  {CONSOLA}")
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

    motivo = validar(clave)
    if motivo:
        print(f"\n  [ERROR] {motivo}")
        print("\n  No se ha guardado nada. Vuelve a ejecutar este archivo")
        print("  cuando tengas la clave copiada.")
        return 1

    archivo = guardar(clave)
    print(f"\n  [OK] Clave guardada en:  {archivo}")
    print(f"       {mask_api_key(clave.strip())}   "
          f"({len(clave.strip())} caracteres)")
    print()
    print("  Ese archivo está fuera del proyecto, así que no se sube a")
    print("  GitHub ni por accidente.")
    print()
    print("  Ahora comprueba que la API responde:")
    print("      python main.py --check")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
