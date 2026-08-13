"""J.A.R.V.I.S. — punto de entrada.

Formas de arrancarlo:

    python main.py              -> interfaz gráfica (lo normal)
    python main.py --consola    -> modo texto en la terminal, sin ventana
    python main.py --check      -> diagnóstico: comprueba todo y sugiere modelo
    python main.py --voces      -> lista las voces de Windows disponibles
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite ejecutar el archivo desde cualquier carpeta.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jarvis import __version__                                    # noqa: E402
from jarvis.config import CONFIG_FILE, config                     # noqa: E402

BANNER = r"""
   ██  ▄▄▄       ██▀███   ██▒   █▓ ██▓  ██████
   ██ ▒████▄    ▓██ ▒ ██▒▓██░   █▒▓██▒▒██    ▒
   ██ ▒██  ▀█▄  ▓██ ░▄█ ▒ ▓██  █▒░▒██▒░ ▓██▄
   ██ ░██▄▄▄▄██ ▒██▀▀█▄    ▒██ █░░░██░  ▒   ██▒
   ██  ▓█   ▓██▒░██▓ ▒██▒   ▒▀█░  ░██░▒██████▒▒
       ▒▒   ▓▒█░░ ▒▓ ░▒▓░   ░ ▐░  ░▓  ▒ ▒▓▒ ▒ ░
        ▒   ▒▒ ░  ░▒ ░ ▒░   ░ ░░   ▒ ░░ ░▒  ░ ░
   Just A Rather Very Intelligent System
"""


# --------------------------------------------------------------------------
# Comprobaciones previas
# --------------------------------------------------------------------------

def check_dependencies(verbose: bool = True) -> bool:
    """Comprueba las librerias. Devuelve False si falta alguna obligatoria."""
    obligatorias = {
        "PyQt6": "PyQt6",
        "requests": "requests",
        "psutil": "psutil",
    }
    opcionales = {
        "pyttsx3": "pyttsx3 (voz del asistente)",
        "speech_recognition": "SpeechRecognition (micrófono)",
        "pyaudio": "PyAudio (micrófono)",
        "pycaw": "pycaw (volumen preciso)",
        "screen_brightness_control": "screen-brightness-control (brillo)",
    }

    faltan: list[str] = []
    for module, nombre in obligatorias.items():
        try:
            __import__(module)
            if verbose:
                print(f"  [OK]    {nombre}")
        except ImportError:
            faltan.append(nombre)
            if verbose:
                print(f"  [FALTA] {nombre}")

    if verbose:
        for module, nombre in opcionales.items():
            try:
                __import__(module)
                print(f"  [OK]    {nombre}")
            except ImportError:
                print(f"  [-]     {nombre}  (opcional, no instalada)")

    if faltan:
        print("\nFaltan librerías obligatorias. Instálalas con:")
        print("   pip install -r requirements.txt")
        return False
    return True


def run_diagnostics() -> int:
    """Modo --check: revisa dependencias, Ollama, micrófono y hardware."""
    from jarvis.core.ollama_client import OllamaClient, suggest_model
    from jarvis.core.speech import SpeechToText, TextToSpeech

    print(BANNER)
    print(f"Versión {__version__}\n")
    print("Configuración:", CONFIG_FILE)

    print("\n--- LIBRERÍAS ---")
    ok = check_dependencies(verbose=True)

    print("\n--- HARDWARE Y MODELO RECOMENDADO ---")
    suggestion, hardware = suggest_model()
    print(f"  RAM: {hardware.get('ram_gb', '?')} GB")
    print(f"  Núcleos: {hardware.get('cores', '?')}")
    print(f"  GPU: {hardware.get('gpu') or 'no detectada'}")
    print(f"\n  Modelo recomendado: {suggestion.name}  ({suggestion.size})")
    print(f"  {suggestion.reason}")
    print(f"  Instálalo con:  {suggestion.command}")

    print("\n--- OLLAMA ---")
    llm = OllamaClient()
    if llm.is_running():
        print(f"  [OK]    Servidor activo en {llm.host}")
        models = llm.list_models()
        if models:
            print(f"  Modelos descargados: {', '.join(models)}")
            resolved = llm.resolve_model()
            print(f"  Modelo que se usará: {resolved}")
        else:
            print("  [AVISO] No hay ningún modelo descargado.")
            print(f"          Ejecuta:  {suggestion.command}")
    else:
        print(f"  [FALLO] No responde en {llm.host}")
        print("          Instálalo desde https://ollama.com/download")
        print("          y luego ejecuta en una terminal:  ollama serve")

    print("\n--- VOZ ---")
    tts = TextToSpeech()
    print(f"  Texto a voz: {'disponible' if tts.available else tts.error}")
    stt = SpeechToText()
    mic_ok, mic_msg = stt.check_microphone()
    print(f"  Micrófono: {mic_msg}")
    tts.shutdown()

    print("\nDiagnóstico terminado.")
    return 0 if ok else 1


def list_voices() -> int:
    from jarvis.core.speech import TextToSpeech
    tts = TextToSpeech()
    voices = tts.list_voices()
    if not voices:
        print("No se han encontrado voces (¿está pyttsx3 instalado?).")
        tts.shutdown()
        return 1
    print("Voces disponibles en este equipo:\n")
    for voice_id, name in voices:
        print(f"  {name}\n     id: {voice_id}\n")
    print("Para fijar una voz, edita", CONFIG_FILE)
    print('y pon su id en  "voice": { "voice_id": "..." }')
    tts.shutdown()
    return 0


# --------------------------------------------------------------------------
# Modos de ejecucion
# --------------------------------------------------------------------------

def run_console() -> int:
    """Modo terminal: util para probar sin interfaz grafica."""
    from jarvis.core.assistant import Assistant

    print(BANNER)
    assistant = Assistant()
    ready, message = assistant.llm_status()
    print(f"[{'OK' if ready else 'AVISO'}] {message}\n")
    print(assistant.greeting())
    print('\n(escribe "salir" para terminar)\n')

    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            return 0
        if text.lower() in ("salir", "exit", "quit", "adios"):
            print("Hasta luego.")
            return 0
        if not text:
            continue

        print("\nJARVIS: ", end="", flush=True)
        printed = {"any": False}

        def on_token(token: str) -> None:
            printed["any"] = True
            print(token, end="", flush=True)

        response = assistant.process(text, on_token=on_token)
        if not printed["any"]:
            print(response.text)
        else:
            print()
        print()


def run_gui() -> int:
    from PyQt6.QtWidgets import QApplication
    from jarvis.ui.main_window import JarvisWindow

    app = QApplication(sys.argv)
    app.setApplicationName("J.A.R.V.I.S.")
    app.setApplicationVersion(__version__)

    window = JarvisWindow()
    if config.get("ui.start_maximized", False):
        window.showMaximized()
    else:
        window.show()
    return app.exec()


# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Asistente de escritorio local estilo J.A.R.V.I.S.",
    )
    parser.add_argument("--consola", action="store_true",
                        help="ejecutar en modo texto, sin ventana")
    parser.add_argument("--check", action="store_true",
                        help="comprobar librerías, Ollama, micrófono y hardware")
    parser.add_argument("--voces", action="store_true",
                        help="listar las voces de texto a voz disponibles")
    parser.add_argument("--modelo", metavar="NOMBRE",
                        help="usar este modelo de Ollama en esta ejecución")
    parser.add_argument("--version", action="version", version=f"J.A.R.V.I.S. {__version__}")
    args = parser.parse_args()

    if args.modelo:
        config.set("ollama.model", args.modelo)
        config.save()

    if args.check:
        return run_diagnostics()
    if args.voces:
        return list_voices()
    if args.consola:
        return run_console()

    if not check_dependencies(verbose=False):
        print("\nEjecuta  python main.py --check  para ver el detalle.")
        return 1
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
