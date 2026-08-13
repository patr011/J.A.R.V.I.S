"""Interprete de comandos: decide que hacer con lo que escribe o dice el usuario.

Funciona con reglas (expresiones regulares) en lugar de con IA, porque para
"abre Chrome" no hace falta un modelo de lenguaje: asi la respuesta es
instantanea y no falla. Todo lo que no encaja con ninguna regla se envia a
Ollama para que conteste el modelo.

El orden de comprobacion importa: primero lo mas especifico
(sistema, volumen, brillo, memoria) y al final lo mas generico ("abre X").
"""

from __future__ import annotations

import re
from typing import Callable

from ..config import config
from . import files, system, web
from .apps import launcher
from .base import CommandResult, normalize, strip_filler

# --------------------------------------------------------------------------
# Utilidades de texto
# --------------------------------------------------------------------------

NUMBER_WORDS = {
    "cero": 0, "cinco": 5, "diez": 10, "quince": 15, "veinte": 20,
    "veinticinco": 25, "treinta": 30, "cuarenta": 40, "cincuenta": 50,
    "sesenta": 60, "setenta": 70, "setenta y cinco": 75, "ochenta": 80,
    "noventa": 90, "cien": 100, "ciento": 100, "maximo": 100, "minimo": 0,
    "medio": 50, "mitad": 50,
}

AFFIRMATIVE = {
    "si", "sii", "claro", "confirmo", "confirmar", "adelante", "vale", "ok",
    "okay", "hazlo", "por supuesto", "afirmativo", "dale", "yes", "y", "correcto",
    "procede", "acepto",
}

NEGATIVE = {
    "no", "nop", "cancela", "cancelar", "para", "detente", "olvidalo",
    "mejor no", "negativo", "abortar", "aborta", "nunca", "cancel",
}


def extract_number(text: str, default: int | None = None) -> int | None:
    """Saca un numero del texto, ya venga en cifras o en palabras."""
    match = re.search(r"\b(\d{1,3})\b", text)
    if match:
        return max(0, min(100, int(match.group(1))))
    norm = normalize(text)
    for word, value in NUMBER_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", norm):
            return value
    return default


def is_affirmative(text: str) -> bool:
    norm = strip_filler(text)
    if not norm:
        return False
    return norm in AFFIRMATIVE or norm.split(" ")[0] in AFFIRMATIVE


def is_negative(text: str) -> bool:
    norm = strip_filler(text)
    if not norm:
        return False
    return norm in NEGATIVE or norm.split(" ")[0] in NEGATIVE


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

class CommandRouter:
    """Convierte una frase en la ejecucion de un comando."""

    def __init__(self, memory=None) -> None:
        self.memory = memory

    # -- entrada principal ----------------------------------------------

    def handle(self, text: str) -> CommandResult:
        raw = text.strip()
        if not raw:
            return CommandResult.unhandled()
        norm = normalize(raw)

        handlers: list[Callable[[str, str], CommandResult | None]] = [
            self._power,
            self._volume,
            self._brightness,
            self._media,
            self._memory,
            self._info,
            self._web,
            self._files,
            self._apps,
        ]
        for handler in handlers:
            result = handler(raw, norm)
            if result is not None:
                return result
        return CommandResult.unhandled()

    # ------------------------------------------------------------------
    # 1. Energia
    # ------------------------------------------------------------------

    def _power(self, raw: str, norm: str) -> CommandResult | None:
        if re.search(r"\b(cancela|cancelar|anula|detén|deten)\b.*\b(apagado|reinicio|apagar)\b", norm) \
                or norm in ("cancela el apagado", "cancelar apagado"):
            return system.power.cancel_shutdown()

        # "apaga la musica" / "apaga la luz" NO deben apagar el ordenador.
        equipo = r"(equipo|ordenador|computadora|computador|pc|sistema|maquina|todo)"

        if re.search(rf"\b(apaga|apagar|apague)\b(\s+(el|la|mi)\s+)?\s*{equipo}?\b", norm):
            if re.search(r"\b(musica|cancion|luz|luces|pantalla|monitor|sonido|volumen)\b", norm):
                return None
            return system.power.shutdown()

        if re.search(r"\b(reinicia|reiniciar|reinicie|reset)\b", norm):
            if re.search(r"\b(router|wifi|programa|aplicacion|app)\b", norm):
                return None
            return system.power.restart()

        if re.search(r"\b(suspende|suspender|suspension|hiberna|hibernar|duerme|dormir|reposo)\b", norm):
            return system.power.sleep()

        if re.search(r"\b(bloquea|bloquear|bloquee)\b", norm):
            return system.power.lock()

        if re.search(r"\bcerrar?\s+(la\s+)?sesion\b|\bcierra\s+(la\s+)?sesion\b", norm):
            return system.power.log_off()

        return None

    # ------------------------------------------------------------------
    # 2. Volumen
    # ------------------------------------------------------------------

    def _volume(self, raw: str, norm: str) -> CommandResult | None:
        if not re.search(r"\b(volumen|sonido|audio|silencia|silenciar|mute|altavoces)\b", norm):
            return None

        if re.search(r"\b(silencia|silenciar|mute|silencio|calla|callate)\b", norm):
            if re.search(r"\b(quita|desactiva|desilencia|restaura|vuelve)\b", norm):
                return system.volume.mute(False)
            return system.volume.mute(True)

        if re.search(r"\b(cual|cuanto|que)\b.*\bvolumen\b|\bvolumen\b.*\b(actual|tienes|esta)\b", norm):
            return CommandResult.done(system.volume.status())

        # "volumen al 40", "pon el volumen en 70 por ciento"
        if re.search(r"\b(al|a|en)\s+\d", norm) or re.search(r"\bpon\b|\bponer\b|\bajusta\b|\bfija\b", norm):
            value = extract_number(norm)
            if value is not None:
                return system.volume.set_level(value)

        if re.search(r"\b(sube|subir|aumenta|aumentar|mas|incrementa)\b", norm):
            step = extract_number(norm, 10) or 10
            return system.volume.change(step)

        if re.search(r"\b(baja|bajar|reduce|reducir|menos|disminuye)\b", norm):
            step = extract_number(norm, 10) or 10
            return system.volume.change(-step)

        if re.search(r"\b(maximo|al maximo|tope)\b", norm):
            return system.volume.set_level(100)

        value = extract_number(norm)
        if value is not None:
            return system.volume.set_level(value)
        return CommandResult.done(system.volume.status())

    # ------------------------------------------------------------------
    # 3. Brillo
    # ------------------------------------------------------------------

    def _brightness(self, raw: str, norm: str) -> CommandResult | None:
        if not re.search(r"\b(brillo|luminosidad|pantalla mas|brightness)\b", norm):
            return None

        if re.search(r"\b(cual|cuanto|que)\b", norm) and not re.search(r"\b(pon|sube|baja)\b", norm):
            return CommandResult.done(system.brightness.status())

        if re.search(r"\b(al|a|en)\s+\d", norm) or re.search(r"\bpon\b|\bponer\b|\bajusta\b|\bfija\b", norm):
            value = extract_number(norm)
            if value is not None:
                return system.brightness.set_level(value)

        if re.search(r"\b(sube|subir|aumenta|aumentar|mas|incrementa|ilumina)\b", norm):
            return system.brightness.change(extract_number(norm, 15) or 15)

        if re.search(r"\b(baja|bajar|reduce|reducir|menos|disminuye|oscurece)\b", norm):
            return system.brightness.change(-(extract_number(norm, 15) or 15))

        value = extract_number(norm)
        if value is not None:
            return system.brightness.set_level(value)
        return CommandResult.done(system.brightness.status())

    # ------------------------------------------------------------------
    # 4. Musica y reproduccion
    # ------------------------------------------------------------------

    def _media(self, raw: str, norm: str) -> CommandResult | None:
        """Poner canciones y controlar lo que suena.

        Va despues de volumen y brillo a proposito: asi «pon el volumen al 50»
        se resuelve alli y no acaba buscando una cancion llamada «el volumen».
        """
        # --- controles del reproductor ---
        if re.fullmatch(r"(dale\s+)?(play|reanuda|reanudar|continua|sigue)"
                        r"(\s+(la\s+)?(musica|cancion|reproduccion))?", norm):
            return system.media.play_pause()

        if re.search(r"\b(pausa|pausar|pausala)\b", norm) or \
                re.search(r"\b(para|paralo|deten|detener)\b.*\b(musica|cancion|reproduccion|video)\b", norm):
            return system.media.play_pause()

        # El adjetivo puede ir delante o detrás: «siguiente canción» y
        # «canción siguiente» son la misma orden.
        pista = r"(cancion|pista|tema|video)"
        if re.search(rf"\b(siguiente|proxima|otra|cambia de)\b.*\b{pista}\b", norm) or \
                re.search(rf"\b{pista}\s+(siguiente|proxima)\b", norm) or \
                re.fullmatch(r"siguiente|pasa de cancion|salta", norm):
            return system.media.next_track()

        if re.search(rf"\b(anterior|previa|vuelve a la)\b.*\b{pista}\b", norm) or \
                re.search(rf"\b{pista}\s+(anterior|previa)\b", norm) or \
                re.fullmatch(r"anterior", norm):
            return system.media.previous_track()

        # --- poner algo ---
        m = re.match(r"^(pon|ponme|reproduce|reproducir|escucha|escuchar|"
                     r"quiero escuchar|quiero oir|pon una|pon la)\s+(.+)$", norm)
        if not m:
            return None

        target = m.group(2).strip()

        # ¿Ha dicho dónde? "... en youtube" / "... en spotify"
        engine = ""
        tail = re.search(r"\s+en\s+(youtube|spotify)$", target)
        if tail:
            engine = tail.group(1)
            target = target[: tail.start()].strip()

        # Quita el envoltorio: "la cancion de X" -> "X", "musica" -> ""
        target = re.sub(r"^(la\s+|una\s+|algo\s+de\s+|un\s+)?"
                        r"(cancion|cancion es|canciones|musica|tema|video|videoclip)\b"
                        r"(\s+de\b|\s+llamada\b|\s+titulada\b)?", "", target).strip(" .,")

        # "pon música" a secas: no hay canción concreta que buscar.
        if not target:
            if engine == "youtube":
                return web.play_song("música para trabajar")
            return system.media.play_music()

        if engine == "spotify":
            return web.open_in_spotify(target)
        return web.play_song(target)

    # ------------------------------------------------------------------
    # 5. Memoria
    # ------------------------------------------------------------------

    def _memory(self, raw: str, norm: str) -> CommandResult | None:
        if self.memory is None:
            return None

        m = re.match(r"^(recuerda|apunta|anota|memoriza|no olvides)\s+(que\s+)?(.+)$", norm)
        if m:
            # Se guarda el texto original (con acentos y mayusculas), no el normalizado.
            payload = re.sub(
                r"^(recuerda|apunta|anota|memoriza|no olvides)\s+(que\s+)?",
                "", raw.strip(), flags=re.IGNORECASE)
            return CommandResult.done(self.memory.remember(payload or m.group(3)))

        m = re.match(r"^(olvida|borra|elimina)\s+(lo de\s+|todo lo de\s+|que\s+)?(.*)$", norm)
        if m and re.search(r"\b(olvida|borra|elimina)\b", norm):
            target = (m.group(3) or "").strip()
            if target in ("", "todo", "la memoria", "tu memoria", "todo lo que sabes"):
                return CommandResult.done(self.memory.forget("todo"))
            return CommandResult.done(self.memory.forget(target))

        if re.search(r"\b(que\s+(te\s+)?(he\s+)?dich[oa]|que\s+te\s+dije|de\s+que\s+hablamos|"
                     r"resumen de la conversacion|que recuerdas)\b", norm):
            recent = self.memory.recent_text(8)
            facts = self.memory.facts_text()
            partes = []
            if recent:
                partes.append("Esto es lo último que hemos hablado:\n" + recent)
            if facts:
                partes.append("Y esto es lo que me pidió recordar:\n" + facts)
            if not partes:
                return CommandResult.done("Todavía no hemos hablado de nada en esta sesión.")
            return CommandResult.done("\n\n".join(partes))

        if re.search(r"\b(limpia|borra|reinicia)\b.*\b(chat|conversacion|historial|pantalla)\b", norm):
            self.memory.clear()
            return CommandResult.done("Conversación reiniciada.", clear_chat=True)

        return None

    # ------------------------------------------------------------------
    # 5. Informacion / utilidades
    # ------------------------------------------------------------------

    def _info(self, raw: str, norm: str) -> CommandResult | None:
        if re.search(r"\bque hora es\b|\bdime la hora\b|\bla hora\b$", norm):
            return system.tell_time()

        if re.search(r"\bque dia es\b|\bque fecha\b|\bla fecha\b|\bdime la fecha\b", norm):
            return system.tell_date()

        if re.search(r"\b(estado del sistema|como esta el (equipo|sistema|pc)|"
                     r"uso de (cpu|memoria|ram)|diagnostico|informe del sistema)\b", norm):
            return system.system_report(system.volume, system.brightness)

        if re.search(r"\b(captura|screenshot|pantallazo|foto de la pantalla)\b", norm):
            return system.take_screenshot()

        if re.search(r"^(ayuda|help|que sabes hacer|que puedes hacer|comandos)$", norm.strip(" ¿?")):
            return CommandResult.done(help_text())

        return None

    # ------------------------------------------------------------------
    # 6. Web
    # ------------------------------------------------------------------

    def _web(self, raw: str, norm: str) -> CommandResult | None:
        # "busca X en google" / "busca en google X"
        m = re.match(r"^(busca|buscar|buscame|googlea)\s+(en\s+(google|youtube|wikipedia|bing)\s+)?(.+)$", norm)
        if m:
            term = m.group(4).strip()
            engine = m.group(3) or ""
            tail = re.match(r"^(.*?)\s+en\s+(google|youtube|wikipedia|bing)$", term)
            if tail:
                term, engine = tail.group(1), tail.group(2)
            # "busca el archivo X" es cosa del buscador de archivos, no de la web.
            if re.match(r"^(el\s+)?(archivo|fichero|documento|carpeta)\b", term):
                return None
            if engine:
                return web.search(term, engine)
            if re.search(r"\b(en internet|en la web|en google)\b", norm):
                return web.search(term)
            # Sin buscador explicito: si es un sitio conocido lo abre, si no busca en Google.
            return web.open_site(term) if web.match_site(term) else web.search(term)

        # "abre la pagina X" / "abre youtube" / "abre google.com"
        m = re.match(r"^(abre|abrir|abreme|ve a|entra en|lanza|inicia|ir a)\s+(.+)$", norm)
        if m:
            target = m.group(2).strip()
            explicit = re.match(r"^(la\s+)?(pagina|pagina web|web|sitio|url|link|enlace)\s+(de\s+)?(.+)$", target)
            if explicit:
                return web.open_site(explicit.group(4))
            if web.match_site(target):
                return web.open_site(target)
        return None

    # ------------------------------------------------------------------
    # 7. Archivos y carpetas
    # ------------------------------------------------------------------

    def _files(self, raw: str, norm: str) -> CommandResult | None:
        m = re.match(r"^(abre|abrir|abreme|muestra|ve a)\s+(la\s+)?carpeta\s+(de\s+)?(.+)$", norm)
        if m:
            return files.open_folder(m.group(4))

        m = re.match(r"^(abre|abrir|abreme)\s+(el\s+)?(archivo|fichero|documento)\s+(de\s+)?(.+)$", norm)
        if m:
            return files.open_file(m.group(5))

        m = re.match(r"^(busca|buscar|buscame|encuentra|localiza)\s+(el\s+|la\s+|los\s+|las\s+)?"
                     r"(archivo|fichero|documento|carpeta)s?\s+(llamad[oa]\s+)?(.+)$", norm)
        if m:
            return files.search_only(m.group(5))

        # "abre descargas" -> carpeta personal conocida
        m = re.match(r"^(abre|abrir|abreme|muestra)\s+(mis\s+|mi\s+|la\s+|el\s+)?(.+)$", norm)
        if m and files.home_folder(m.group(3).strip()):
            return files.open_folder(m.group(3))
        return None

    # ------------------------------------------------------------------
    # 8. Aplicaciones
    # ------------------------------------------------------------------

    def _apps(self, raw: str, norm: str) -> CommandResult | None:
        m = re.match(
            r"^(abre|abrir|abreme|inicia|iniciar|lanza|lanzar|ejecuta|ejecutar|arranca|pon en marcha)"
            r"\s+(.+)$", norm)
        if not m:
            return None

        target = m.group(2).strip()
        result = launcher.open_app(target)
        if result.ok:
            return result

        # No es una app: quiza sea un archivo o una carpeta con ese nombre.
        matches = files.find_paths(strip_filler(target), want="any", limit=3)
        if matches:
            ok, err = files.open_path(matches[0])
            if ok:
                return CommandResult.done(
                    f"No es una aplicación, pero he encontrado y abierto «{matches[0].name}».",
                    path=str(matches[0]))
        return result


# --------------------------------------------------------------------------
# Ayuda
# --------------------------------------------------------------------------

def help_text() -> str:
    return (
        "Esto es lo que puedo hacer:\n"
        "\n  APLICACIONES\n"
        "   · «abre Chrome», «inicia Spotify», «abre la calculadora»\n"
        "\n  ARCHIVOS Y CARPETAS\n"
        "   · «abre la carpeta descargas», «busca el archivo presupuesto»\n"
        "\n  WEB\n"
        "   · «abre YouTube», «busca gatos en Google»\n"
        "\n  MÚSICA\n"
        "   · «pon Bohemian Rhapsody» — la busca y la reproduce\n"
        "   · «pon música» — reanuda o abre Spotify\n"
        "   · «pon Shakira en Spotify», «pausa», «play», «siguiente canción»\n"
        "\n  SISTEMA\n"
        "   · «sube el volumen», «volumen al 40», «silencia»\n"
        "   · «sube el brillo», «brillo al 70»\n"
        "   · «apaga el equipo», «reinicia», «suspende», «bloquea el equipo»\n"
        "   · «cancela el apagado», «estado del sistema», «captura de pantalla»\n"
        "\n  MEMORIA\n"
        "   · «recuerda que mañana tengo dentista», «¿qué te dije?», «olvida todo»\n"
        "\n  CONVERSACIÓN\n"
        "   · Cualquier otra cosa se la pregunto al modelo local de Ollama.\n"
    )
