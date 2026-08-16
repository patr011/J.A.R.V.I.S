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
from jarvis.config import CONFIG_FILE, LOG_FILE, config           # noqa: E402
from jarvis.logging_setup import (get_logger, install_exception_hook,  # noqa: E402
                                  setup_logging)

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
        "anthropic": "anthropic (API de Claude)",
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
    from jarvis.core.secrets import get_elevenlabs_key
    from jarvis.core.speech import SpeechToText, TextToSpeech

    print(BANNER)
    print(f"Versión {__version__}\n")
    print("Configuración:", CONFIG_FILE)
    print("Registro de errores:", LOG_FILE)

    print("\n--- LIBRERÍAS ---")
    ok = check_dependencies(verbose=True)

    print("\n--- HARDWARE (solo importa para el modelo local) ---")
    suggestion, hardware = suggest_model()
    print(f"  RAM: {hardware.get('ram_gb', '?')} GB")
    print(f"  Núcleos: {hardware.get('cores', '?')}")
    print(f"  GPU: {hardware.get('gpu') or 'no detectada'}")
    print(f"\n  Modelo recomendado: {suggestion.name}  ({suggestion.size})")
    print(f"  {suggestion.reason}")
    print(f"  Instálalo con:  {suggestion.command}")

    print("\n--- NÚCLEO DE IA ---")
    from jarvis.core.llm import PROVIDERS, current_provider
    from jarvis.core.secrets import has_api_key, mask_api_key, where_to_put_the_key

    proveedor = current_provider()
    print(f"  Cerebro configurado: {PROVIDERS[proveedor]}")

    if proveedor == "claude":
        try:
            import anthropic                                  # noqa: F401
            print("  [OK]    Librería anthropic instalada")
        except ImportError:
            print("  [FALLO] Falta la librería. Ejecuta:  pip install anthropic")
            return 1

        if not has_api_key():
            print("  [FALLO] No hay clave de API configurada.")
            for linea in where_to_put_the_key().splitlines()[1:]:
                print("  " + linea)
            return 1

        print(f"  [OK]    Clave detectada: {mask_api_key()}")
        from jarvis.core.claude_client import ClaudeClient, model_info
        cliente = ClaudeClient()
        datos = model_info(cliente.model)
        print(f"  Modelo: {datos.nombre}  ({datos.nota})")
        print(f"  Precio: ${datos.entrada:.2f} entrada / ${datos.salida:.2f} salida "
              "por millón de tokens")
        if cliente.is_running():
            print("  [OK]    La API responde correctamente")
        else:
            print(f"  [FALLO] {cliente.error}")

        print("\n--- OLLAMA (alternativa local, opcional) ---")

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

    print("\n--- CONTROL DEL SISTEMA ---")
    from jarvis.commands.system import brightness, volume
    nivel = volume.get_level()
    if nivel is not None:
        print(f"  [OK]    Volumen: {nivel}%  (usando {volume.backend})")
    else:
        print("  [FALLO] Volumen: no se puede leer el nivel")
        if volume.error:
            print(f"          Motivo: {volume.error}")
        print("          Subir y bajar el volumen seguira funcionando con las teclas multimedia.")

    nivel = brightness.get_level()
    if nivel is not None:
        print(f"  [OK]    Brillo: {nivel}%")
    else:
        print("  [AVISO] Brillo: no disponible")
        print("          Normal en monitores de sobremesa: muchos no lo permiten por software.")

    print("\n--- VOZ ---")
    tts = TextToSpeech()
    print(f"  Texto a voz: {'disponible' if tts.available else tts.error}")
    print(f"  Motor elegido: {config.get('voice.engine', 'windows')}")

    if str(config.get("voice.engine", "windows")).lower() == "elevenlabs":
        from jarvis.core.secrets import has_elevenlabs_key, mask_api_key
        from jarvis.core.tts_elevenlabs import CONSOLA, ElevenLabsTTS

        if not has_elevenlabs_key():
            print("  [FALLO] No hay clave de ElevenLabs.")
            print(f"          Sácala en {CONSOLA} y guárdala con:")
            print("            python poner_clave.py voz")
        else:
            print(f"  [OK]    Clave de ElevenLabs: {mask_api_key(get_elevenlabs_key())}")
            cliente = ElevenLabsTTS()
            listo, motivo = cliente.esta_listo()
            print(f"  {'[OK]   ' if listo else '[FALLO]'} {motivo}")
            if listo:
                voces = cliente.list_voices()
                if voces:
                    print(f"  Voces en tu cuenta: {len(voces)}")
                    elegida = next((v for v in voces if v.voice_id == cliente.voice_id), None)
                    print(f"  Voz elegida: {elegida.nombre if elegida else cliente.voice_id}")
                else:
                    print(f"  [AVISO] No he podido leer tus voces. {cliente.error}")
                cliente.actualizar_cupo()
                if cliente.gasto.cupo_total:
                    queda = cliente.gasto.cupo_total - cliente.gasto.cupo_usado
                    print(f"  Cupo del mes: quedan {queda} de "
                          f"{cliente.gasto.cupo_total} caracteres")
        print(f"  Si ElevenLabs falla, hablará la voz de Windows: "
              f"{'disponible' if tts.available else 'tampoco disponible'}")

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
        # Los temporizadores tambien tienen que sonar aqui, no solo en la
        # ventana: si no, en modo consola se quedarian mudos para siempre.
        for aviso in assistant.reminders.check_due():
            print(f"\n  [AVISO] {assistant.reminders.announcement(aviso)}\n")

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

    log = get_logger("arranque")
    log.info("Abriendo la interfaz grafica")
    app = QApplication(sys.argv)
    app.setApplicationName("J.A.R.V.I.S.")
    app.setApplicationVersion(__version__)

    window = JarvisWindow()

    # Un fallo inesperado ya queda en el log; ademas se enseña en la ventana,
    # para que el usuario no vea solo que "se ha cerrado solo".
    def avisar(mensaje: str) -> None:
        window.chat.add_message(
            "error", f"Error interno: {mensaje}\n   Detalle completo en {LOG_FILE}")
    install_exception_hook(on_error=avisar)

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
    parser.add_argument("--cerebro", action="store_true",
                        help="escribir que cerebro esta configurado (claude u ollama)")
    parser.add_argument("--modelo", metavar="NOMBRE",
                        help="usar este modelo de Ollama en esta ejecución")
    parser.add_argument("--version", action="version", version=f"J.A.R.V.I.S. {__version__}")
    args = parser.parse_args()

    setup_logging(verbose=args.consola or args.check)
    install_exception_hook()

    # Los .env se leen al arrancar para que la clave este disponible en todo
    # el programa. Nunca se escribe en el log ni en la configuracion.
    from jarvis.core.secrets import load_env_files
    for ruta in load_env_files():
        get_logger("arranque").info("Variables leidas de %s", ruta)

    if args.modelo:
        config.set("ollama.model", args.modelo)
        config.save()

    if args.cerebro:
        # Lo usa ejecutar.bat para saber si merece la pena arrancar Ollama.
        # Escribe una sola palabra y nada mas, para poder leerla desde un
        # archivo por lotes sin tener que interpretar nada.
        from jarvis.core.llm import current_provider
        print(current_provider())
        return 0

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
