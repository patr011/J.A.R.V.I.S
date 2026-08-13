"""Lanza todas las pruebas de J.A.R.V.I.S.

    python probar.py            todas las pruebas
    python probar.py -v         con el detalle de cada una
    python probar.py comandos   solo las que llevan «comandos» en el nombre

Ninguna prueba toca el sistema de verdad: no abre programas, no cambia el
volumen y, por supuesto, no apaga el ordenador.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

# La interfaz se prueba sin pantalla física.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    try:
        import pytest
    except ImportError:
        print("Falta pytest. Instálalo con:\n")
        print("    pip install pytest\n")
        return 1

    argumentos = ["tests", "--tb=short", "-q"]
    for arg in sys.argv[1:]:
        if arg.startswith("-"):
            argumentos.append(arg)
        else:
            argumentos += ["-k", arg]

    print("=" * 62)
    print("  J.A.R.V.I.S.  -  Pruebas")
    print("=" * 62)
    codigo = pytest.main(argumentos)

    print()
    if codigo == 0:
        print("  Todo correcto: el asistente se comporta como debe.")
    else:
        print("  Hay fallos. Arriba está el detalle de cada uno.")
    return int(codigo)


if __name__ == "__main__":
    sys.exit(main())
