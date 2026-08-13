"""Notas y listas.

    «apunta leche en la lista de la compra»
    «añade pan a la compra»
    «lee mi lista de la compra»
    «qué listas tengo»
    «quita leche de la compra»  ·  «borra la lista de la compra»

Todo se guarda en ~/.jarvis/notas.json, así que sigue ahí cuando vuelves a
abrir el asistente.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from ..config import HOME_DIR
from .base import CommandResult, normalize

NOTES_FILE = HOME_DIR / "notas.json"

LISTA_POR_DEFECTO = "notas"

# Cómo llama la gente a la misma lista.
ALIAS_LISTAS = {
    "compra": "compra",
    "la compra": "compra",
    "lista de la compra": "compra",
    "supermercado": "compra",
    "super": "compra",
    "tareas": "tareas",
    "pendientes": "tareas",
    "cosas por hacer": "tareas",
    "to do": "tareas",
    "notas": "notas",
    "apuntes": "notas",
    "ideas": "ideas",
    "peliculas": "peliculas",
    "libros": "libros",
}


def normalizar_lista(nombre: str) -> str:
    clave = normalize(nombre).strip(" .,")
    clave = re.sub(r"^(la|mi|el|mis)\s+", "", clave)
    clave = re.sub(r"^lista\s+de\s+(la\s+|los\s+|las\s+)?", "", clave)
    return ALIAS_LISTAS.get(clave, clave or LISTA_POR_DEFECTO)


class NoteBook:
    """Colección de listas con sus elementos."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.load()

    # -- disco ----------------------------------------------------------

    def load(self) -> None:
        try:
            if NOTES_FILE.exists():
                with open(NOTES_FILE, "r", encoding="utf-8") as fh:
                    datos = json.load(fh)
                listas = datos.get("listas", {})
                if isinstance(listas, dict):
                    self.lists = {str(k): [str(x) for x in v]
                                  for k, v in listas.items() if isinstance(v, list)}
        except (json.JSONDecodeError, OSError, AttributeError):
            self.lists = {}

    def save(self) -> None:
        try:
            HOME_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"listas": self.lists, "actualizado": datetime.now().isoformat()}
            tmp = Path(str(NOTES_FILE) + ".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, NOTES_FILE)
        except OSError:
            pass

    # -- operaciones -----------------------------------------------------

    def add(self, lista: str, elemento: str) -> str:
        lista = normalizar_lista(lista)
        elemento = elemento.strip(" .,")
        if not elemento:
            return "¿Qué quiere que apunte?"
        items = self.lists.setdefault(lista, [])
        if any(normalize(x) == normalize(elemento) for x in items):
            return f"«{elemento}» ya estaba en la lista de {lista}."
        items.append(elemento)
        self.save()
        return f"Apuntado «{elemento}» en la lista de {lista}. Van {len(items)}."

    def remove(self, lista: str, elemento: str) -> str:
        lista = normalizar_lista(lista)
        items = self.lists.get(lista)
        if not items:
            return f"No tiene ninguna lista de {lista}."
        objetivo = normalize(elemento)
        quedan = [x for x in items if normalize(x) != objetivo and objetivo not in normalize(x)]
        if len(quedan) == len(items):
            return f"No encuentro «{elemento}» en la lista de {lista}."
        self.lists[lista] = quedan
        self.save()
        return f"Quitado «{elemento}» de la lista de {lista}. Quedan {len(quedan)}."

    def read(self, lista: str) -> str:
        lista = normalizar_lista(lista)
        items = self.lists.get(lista)
        if not items:
            return f"La lista de {lista} está vacía."
        detalle = "\n".join(f"   {i}. {x}" for i, x in enumerate(items, 1))
        return f"Lista de {lista} ({len(items)}):\n{detalle}"

    def clear(self, lista: str) -> str:
        lista = normalizar_lista(lista)
        if lista not in self.lists:
            return f"No tiene ninguna lista de {lista}."
        cuantos = len(self.lists.pop(lista))
        self.save()
        return f"Borrada la lista de {lista} ({cuantos} elemento(s))."

    def all_lists(self) -> str:
        con_contenido = {k: v for k, v in self.lists.items() if v}
        if not con_contenido:
            return "No tiene ninguna lista todavía."
        detalle = "\n".join(f"   · {k}: {len(v)} elemento(s)" for k, v in con_contenido.items())
        return f"Tiene {len(con_contenido)} lista(s):\n{detalle}"


# --------------------------------------------------------------------------
# Comandos
# --------------------------------------------------------------------------

def handle(notebook: NoteBook, raw: str, norm: str) -> CommandResult | None:
    # --- ver todas las listas ---
    if re.search(r"\b(que|cuantas|cuales)\b.*\blistas?\b\s*(tengo|hay)?$", norm) or \
            re.fullmatch(r"(mis\s+)?listas", norm):
        return CommandResult.done(notebook.all_lists())

    # --- leer una lista ---
    m = re.match(r"^(lee|leeme|leer|muestra|muestrame|ensename|dime|que hay en|"
                 r"que tengo en|abre)\s+(la\s+|mi\s+|mis\s+)?"
                 r"(lista\s+de\s+(la\s+|los\s+|las\s+)?)?(.+)$", norm)
    if m and re.search(r"\blista\b|\bcompra\b|\btareas\b|\bpendientes\b|\bnotas\b", norm):
        return CommandResult.done(notebook.read(m.group(5)))

    # --- borrar una lista entera ---
    m = re.match(r"^(borra|vacia|elimina|limpia)\s+(la\s+|mi\s+)?"
                 r"lista\s+(de\s+(la\s+|los\s+|las\s+)?)?(.+)$", norm)
    if m:
        return CommandResult.done(notebook.clear(m.group(5)))

    # --- quitar un elemento ---
    m = re.match(r"^(quita|quitar|borra|elimina|tacha)\s+(.+?)\s+"
                 r"(?:de|del)\s+(la\s+|mi\s+)?(lista\s+de\s+(la\s+|los\s+|las\s+)?)?(.+)$", norm)
    if m:
        return CommandResult.done(notebook.remove(m.group(6), m.group(2)))

    # --- apuntar algo ---
    # "apunta X en la lista Y" / "añade X a la compra"
    m = re.match(r"^(apunta|apuntame|anota|añade|anade|agrega|mete|pon|guarda)\s+(.+?)\s+"
                 r"(?:en|a|al)\s+(la\s+|mi\s+)?(lista\s+de\s+(la\s+|los\s+|las\s+)?)?(.+)$", norm)
    if m:
        destino = m.group(6)
        # Solo si el destino parece una lista, para no robarle «pon X en Spotify».
        if re.search(r"\blista\b", norm) or normalizar_lista(destino) in ALIAS_LISTAS.values():
            # El texto original conserva mayúsculas y acentos.
            elemento = _recortar_original(raw, m.group(2))
            return CommandResult.done(notebook.add(destino, elemento))

    # "apunta que tengo que llamar" / "anota comprar pan"
    m = re.match(r"^(apunta|anota|apuntame)\s+(que\s+)?(.+)$", norm)
    if m:
        elemento = _recortar_original(raw, m.group(3))
        return CommandResult.done(notebook.add(LISTA_POR_DEFECTO, elemento))

    return None


def _recortar_original(raw: str, fragmento_normalizado: str) -> str:
    """Recupera el texto original (con tildes y mayúsculas) de un fragmento.

    El intérprete trabaja sobre texto normalizado, pero lo que se guarda debe
    verse bien: «Melón» y no «melon».
    """
    palabras = fragmento_normalizado.split()
    if not palabras:
        return fragmento_normalizado
    originales = raw.split()
    normalizadas = [normalize(p) for p in originales]
    for inicio in range(len(normalizadas)):
        if normalizadas[inicio:inicio + len(palabras)] == palabras:
            return " ".join(originales[inicio:inicio + len(palabras)]).strip(" .,")
    return fragmento_normalizado
