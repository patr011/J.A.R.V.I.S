"""Temporizadores, alarmas y recordatorios.

    «ponme un temporizador de 10 minutos»
    «avísame en media hora»
    «recuérdame a las 17:30 que llame al dentista»
    «despiértame a las 7 de la mañana»
    «¿qué alarmas tengo?»  ·  «cancela el temporizador»

Los avisos se guardan en disco, así que si cierras el asistente y lo vuelves
a abrir siguen ahí. Un aviso cuya hora ya pasó mientras estaba cerrado salta
al arrancar, avisando de que llega tarde.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from ..config import HOME_DIR
from .base import CommandResult, normalize

REMINDERS_FILE = HOME_DIR / "avisos.json"


# --------------------------------------------------------------------------
# Modelo
# --------------------------------------------------------------------------

@dataclass
class Reminder:
    """Un aviso programado."""

    when: datetime
    text: str = ""
    kind: str = "temporizador"           # "temporizador" | "alarma" | "recordatorio"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    fired: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "when": self.when.isoformat(), "text": self.text,
                "kind": self.kind, "fired": self.fired}

    @staticmethod
    def from_dict(data: dict) -> "Reminder | None":
        try:
            return Reminder(
                when=datetime.fromisoformat(data["when"]),
                text=str(data.get("text", "")),
                kind=str(data.get("kind", "temporizador")),
                id=str(data.get("id", uuid.uuid4().hex[:8])),
                fired=bool(data.get("fired", False)),
            )
        except (KeyError, ValueError, TypeError):
            return None

    def remaining(self) -> timedelta:
        return self.when - datetime.now()

    def describe_remaining(self) -> str:
        return humanize(self.remaining())

    def describe(self) -> str:
        cuando = self.when.strftime("%H:%M")
        if self.when.date() != datetime.now().date():
            cuando = self.when.strftime("%d/%m a las %H:%M")
        etiqueta = f"{self.kind.capitalize()} de las {cuando}" \
            if self.kind == "alarma" else f"{self.kind.capitalize()} para las {cuando}"
        if self.text:
            etiqueta += f": {self.text}"
        return f"{etiqueta} (faltan {self.describe_remaining()})"


def humanize(delta: timedelta) -> str:
    """timedelta -> «2 horas y 5 minutos»."""
    total = int(delta.total_seconds())
    if total < 0:
        return "nada, ya ha pasado"
    if total < 60:
        return f"{total} segundo{'s' if total != 1 else ''}"

    minutos, horas = (total // 60) % 60, total // 3600
    partes = []
    if horas:
        partes.append(f"{horas} hora{'s' if horas != 1 else ''}")
    if minutos:
        partes.append(f"{minutos} minuto{'s' if minutos != 1 else ''}")
    if not partes:
        partes.append("menos de un minuto")
    return " y ".join(partes)


# --------------------------------------------------------------------------
# Interpretar lo que dice el usuario
# --------------------------------------------------------------------------

UNIT_SECONDS = {
    "segundo": 1, "segundos": 1, "seg": 1,
    "minuto": 60, "minutos": 60, "min": 60,
    "hora": 3600, "horas": 3600, "h": 3600,
    "dia": 86400, "dias": 86400,
}

NUMBER_WORDS = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
    "doce": 12, "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40,
    "cuarenta y cinco": 45, "cincuenta": 50, "sesenta": 60, "noventa": 90,
}


def parse_duration(text: str) -> timedelta | None:
    """«10 minutos», «media hora», «hora y media», «2 h 30 min» -> timedelta."""
    norm = normalize(text)

    if re.search(r"\bmedia hora\b", norm):
        return timedelta(minutes=30)
    if re.search(r"\b(una\s+)?hora y media\b", norm):
        return timedelta(minutes=90)
    if re.search(r"\bcuarto de hora\b", norm):
        return timedelta(minutes=15)

    total = 0
    encontrado = False

    # Con cifras: "2 horas", "30 min"
    for cantidad, unidad in re.findall(r"(\d+)\s*([a-z]+)", norm):
        segundos = UNIT_SECONDS.get(unidad)
        if segundos:
            total += int(cantidad) * segundos
            encontrado = True

    # Con palabras: "diez minutos"
    if not encontrado:
        for palabra, valor in sorted(NUMBER_WORDS.items(), key=lambda x: -len(x[0])):
            patron = rf"\b{re.escape(palabra)}\s+(segundos?|minutos?|horas?|dias?)\b"
            m = re.search(patron, norm)
            if m:
                total += valor * UNIT_SECONDS.get(m.group(1), 60)
                encontrado = True
                break

    return timedelta(seconds=total) if encontrado and total > 0 else None


def parse_time_of_day(text: str) -> datetime | None:
    """«a las 7», «a las 17:30», «a las 7 de la tarde» -> momento concreto."""
    norm = normalize(text)
    m = re.search(r"\ba\s+las?\s+(\d{1,2})(?:[:.](\d{2}))?", norm)
    if not m:
        return None

    hora = int(m.group(1))
    minuto = int(m.group(2) or 0)
    if hora > 23 or minuto > 59:
        return None

    # "de la tarde" / "de la noche" -> formato de 24 horas
    resto = norm[m.end():]
    if re.search(r"\b(de la tarde|de la noche|pm|p m)\b", resto) and hora < 12:
        hora += 12
    elif re.search(r"\b(de la mañana|de la manana|am|a m)\b", resto) and hora == 12:
        hora = 0

    objetivo = datetime.now().replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if re.search(r"\bmañana\b", norm) and not re.search(r"\bde la mañana\b", norm):
        objetivo += timedelta(days=1)
    elif objetivo <= datetime.now():
        # Una hora que ya pasó se entiende para mañana.
        objetivo += timedelta(days=1)
    return objetivo


def extract_subject(text: str) -> str:
    """Saca el «qué» de «recuérdame en 5 minutos que saque la basura»."""
    m = re.search(r"\bque\s+(.+)$", text.strip(), flags=re.IGNORECASE)
    if m:
        return m.group(1).strip(" .,")
    m = re.search(r"\b(?:de|para)\s+(?!la\s+tarde|la\s+noche|la\s+mañana)(.+)$",
                  text.strip(), flags=re.IGNORECASE)
    if m:
        candidato = m.group(1).strip(" .,")
        # "de 10 minutos" no es el asunto, es la duración.
        if not re.match(r"^\d+\s*(segundos?|minutos?|horas?|dias?)", normalize(candidato)):
            return candidato
    return ""


# --------------------------------------------------------------------------
# Gestor
# --------------------------------------------------------------------------

class ReminderManager:
    """Guarda los avisos, los vigila y llama cuando toca.

    No usa un hilo con temporizadores: la interfaz le pregunta cada segundo
    con `check_due()`. Así todo ocurre en el hilo de la ventana y no hay
    riesgo de tocar widgets desde otro sitio.
    """

    def __init__(self, on_fire: Callable[[Reminder], None] | None = None) -> None:
        self._lock = threading.RLock()
        self.reminders: list[Reminder] = []
        self.on_fire = on_fire
        self.load()

    # -- persistencia ---------------------------------------------------

    def load(self) -> None:
        try:
            if REMINDERS_FILE.exists():
                with open(REMINDERS_FILE, "r", encoding="utf-8") as fh:
                    datos = json.load(fh)
                cargados = [Reminder.from_dict(d) for d in datos.get("avisos", [])]
                with self._lock:
                    self.reminders = [r for r in cargados if r and not r.fired]
        except (json.JSONDecodeError, OSError, AttributeError):
            self.reminders = []

    def save(self) -> None:
        try:
            HOME_DIR.mkdir(parents=True, exist_ok=True)
            with self._lock:
                datos = {"avisos": [r.to_dict() for r in self.reminders if not r.fired]}
            tmp = Path(str(REMINDERS_FILE) + ".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(datos, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, REMINDERS_FILE)
        except OSError:
            pass

    # -- alta y baja ----------------------------------------------------

    def add(self, when: datetime, text: str = "", kind: str = "temporizador") -> Reminder:
        aviso = Reminder(when=when, text=text, kind=kind)
        with self._lock:
            self.reminders.append(aviso)
            self.reminders.sort(key=lambda r: r.when)
        self.save()
        return aviso

    def cancel(self, needle: str = "") -> int:
        """Cancela avisos. Sin texto, los cancela todos."""
        needle = normalize(needle).strip()
        with self._lock:
            antes = len(self.reminders)
            if not needle or needle in ("todo", "todos", "todas"):
                self.reminders.clear()
            else:
                self.reminders = [
                    r for r in self.reminders
                    if needle not in normalize(r.text) and needle not in normalize(r.kind)
                    and needle != r.id
                ]
            borrados = antes - len(self.reminders)
        self.save()
        return borrados

    def pending(self) -> list[Reminder]:
        with self._lock:
            return [r for r in self.reminders if not r.fired]

    # -- vigilancia ------------------------------------------------------

    def check_due(self) -> list[Reminder]:
        """Devuelve los avisos que ya tocan y los marca como avisados."""
        ahora = datetime.now()
        vencidos: list[Reminder] = []
        with self._lock:
            for aviso in self.reminders:
                if not aviso.fired and aviso.when <= ahora:
                    aviso.fired = True
                    vencidos.append(aviso)
            if vencidos:
                self.reminders = [r for r in self.reminders if not r.fired]
        if vencidos:
            self.save()
            for aviso in vencidos:
                if self.on_fire:
                    self.on_fire(aviso)
        return vencidos

    def announcement(self, aviso: Reminder) -> str:
        """El texto que se dice y se escribe cuando salta el aviso."""
        retraso = datetime.now() - aviso.when
        tarde = " (con retraso: el asistente estaba cerrado)" \
            if retraso > timedelta(minutes=1) else ""
        if aviso.text:
            return f"Aviso{tarde}: {aviso.text}."
        if aviso.kind == "alarma":
            return f"Es la hora: son las {aviso.when.strftime('%H:%M')}{tarde}."
        return f"Se acabó el tiempo{tarde}."


# --------------------------------------------------------------------------
# Comandos
# --------------------------------------------------------------------------

def handle(manager: ReminderManager, raw: str, norm: str) -> CommandResult | None:
    """Interpreta las frases relacionadas con avisos."""

    # --- consultar ---
    if re.search(r"\b(que|cuantas|cuales)\b.*\b(alarmas?|temporizador(es)?|"
                 r"recordatorios?|avisos?)\b", norm) or \
            re.fullmatch(r"(mis\s+)?(alarmas|temporizadores|recordatorios|avisos)", norm):
        pendientes = manager.pending()
        if not pendientes:
            return CommandResult.done("No tiene ningún aviso programado.")
        listado = "\n".join(f"   · {r.describe()}" for r in pendientes)
        return CommandResult.done(f"Tiene {len(pendientes)} aviso(s):\n{listado}")

    # --- cancelar ---
    m = re.match(r"^(cancela|cancelar|quita|elimina|borra|anula)\s+"
                 r"(el|la|los|las|mi|mis)?\s*"
                 r"(alarmas?|temporizador(?:es)?|recordatorios?|avisos?)\s*(.*)$", norm)
    if m:
        objetivo = (m.group(4) or "").strip()
        borrados = manager.cancel(objetivo or "todos")
        if not borrados:
            return CommandResult.done("No había ningún aviso que cancelar.")
        return CommandResult.done(
            f"Cancelado{'s' if borrados > 1 else ''} {borrados} aviso"
            f"{'s' if borrados > 1 else ''}.")

    # --- crear ---
    disparador = re.match(
        r"^(ponme?|pon|programa|crea|echa|activa|avisame|avisarme|recuerdame|"
        r"despiertame|necesito)\b", norm)
    palabra_clave = re.search(r"\b(temporizador|alarma|recordatorio|cuenta atras|aviso)\b", norm)
    if not disparador and not palabra_clave:
        return None
    # «pon música» no es un aviso.
    if re.search(r"\b(musica|cancion|volumen|brillo)\b", norm) and not palabra_clave:
        return None

    asunto = extract_subject(raw)

    # ¿A una hora concreta?
    momento = parse_time_of_day(raw)
    if momento is not None:
        tipo = "alarma" if re.search(r"\b(alarma|despiertame|despertar)\b", norm) else "recordatorio"
        aviso = manager.add(momento, asunto, tipo)
        cuando = momento.strftime("%H:%M")
        dia = "" if momento.date() == datetime.now().date() else " de mañana"
        detalle = f" para {asunto}" if asunto else ""
        return CommandResult.done(
            f"{tipo.capitalize()} puesta a las {cuando}{dia}{detalle}. "
            f"Le avisaré en {aviso.describe_remaining()}.")

    # ¿Dentro de un rato?
    duracion = parse_duration(raw)
    if duracion is not None:
        tipo = "temporizador" if re.search(r"\b(temporizador|cuenta atras)\b", norm) else "recordatorio"
        aviso = manager.add(datetime.now() + duracion, asunto, tipo)
        detalle = f" para {asunto}" if asunto else ""
        return CommandResult.done(
            f"{tipo.capitalize()} de {humanize(duracion)}{detalle}. "
            f"Le aviso cuando termine.")

    if palabra_clave:
        return CommandResult.fail(
            "¿De cuánto tiempo? Dígame por ejemplo «ponme un temporizador de 10 minutos» "
            "o «avísame a las 17:30».")
    return None
