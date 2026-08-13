"""Temporizadores, alarmas y recordatorios."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from jarvis.commands import reminders
from jarvis.commands.registry import CommandRouter
from jarvis.commands.reminders import ReminderManager, humanize, parse_duration, parse_time_of_day


@pytest.fixture
def gestor(tmp_path, monkeypatch):
    """Gestor que guarda en carpeta temporal, no en la del usuario."""
    monkeypatch.setattr(reminders, "REMINDERS_FILE", tmp_path / "avisos.json")
    return ReminderManager()


# --------------------------------------------------------------------------
# Entender el tiempo que dice el usuario
# --------------------------------------------------------------------------

DURACIONES = [
    ("un temporizador de 10 minutos", 10 * 60),
    ("avisame en 5 minutos", 5 * 60),
    ("en 2 horas", 2 * 3600),
    ("en media hora", 30 * 60),
    ("en hora y media", 90 * 60),
    ("un cuarto de hora", 15 * 60),
    ("en 30 segundos", 30),
    ("en 1 hora y 30 minutos", 90 * 60),
    ("en diez minutos", 10 * 60),
    ("en tres horas", 3 * 3600),
]


@pytest.mark.parametrize("frase,segundos", DURACIONES)
def test_entiende_las_duraciones(frase, segundos):
    duracion = parse_duration(frase)
    assert duracion is not None, f"no ha entendido «{frase}»"
    assert duracion.total_seconds() == segundos


@pytest.mark.parametrize("frase", ["hola que tal", "pon musica", "abre chrome"])
def test_no_ve_duraciones_donde_no_las_hay(frase):
    assert parse_duration(frase) is None


def test_entiende_las_horas():
    momento = parse_time_of_day("recuerdame a las 17:30 que llame")
    assert momento is not None
    assert (momento.hour, momento.minute) == (17, 30)


def test_las_siete_de_la_tarde_son_las_diecinueve():
    momento = parse_time_of_day("avisame a las 7 de la tarde")
    assert momento.hour == 19


def test_una_hora_que_ya_paso_se_entiende_para_manana():
    ahora = datetime.now()
    hora_pasada = (ahora - timedelta(hours=2)).hour
    momento = parse_time_of_day(f"avisame a las {hora_pasada}")
    assert momento > ahora


@pytest.mark.parametrize("segundos,texto", [
    (30, "30 segundos"), (60, "1 minuto"), (600, "10 minutos"),
    (3600, "1 hora"), (5400, "1 hora y 30 minutos"),
])
def test_dice_el_tiempo_en_cristiano(segundos, texto):
    assert humanize(timedelta(seconds=segundos)) == texto


# --------------------------------------------------------------------------
# El gestor
# --------------------------------------------------------------------------

def test_un_aviso_salta_cuando_toca(gestor):
    gestor.add(datetime.now() + timedelta(milliseconds=1), "sacar la basura")
    import time
    time.sleep(0.02)
    vencidos = gestor.check_due()
    assert len(vencidos) == 1
    assert vencidos[0].text == "sacar la basura"


def test_un_aviso_futuro_no_salta_antes_de_tiempo(gestor):
    gestor.add(datetime.now() + timedelta(hours=1), "reunión")
    assert gestor.check_due() == []
    assert len(gestor.pending()) == 1


def test_un_aviso_solo_salta_una_vez(gestor):
    gestor.add(datetime.now() - timedelta(seconds=1), "ya pasó")
    assert len(gestor.check_due()) == 1
    assert gestor.check_due() == []


def test_los_avisos_sobreviven_al_cierre(gestor, tmp_path, monkeypatch):
    gestor.add(datetime.now() + timedelta(hours=2), "cita médica")
    monkeypatch.setattr(reminders, "REMINDERS_FILE", tmp_path / "avisos.json")
    otro = ReminderManager()
    assert len(otro.pending()) == 1
    assert otro.pending()[0].text == "cita médica"


def test_un_aviso_atrasado_avisa_de_que_llega_tarde(gestor):
    """Si el asistente estaba cerrado, el aviso salta al abrir y lo dice."""
    gestor.add(datetime.now() - timedelta(hours=1), "llamar a mamá")
    vencido = gestor.check_due()[0]
    assert "retraso" in gestor.announcement(vencido)


def test_cancelar_todo(gestor):
    gestor.add(datetime.now() + timedelta(hours=1), "uno")
    gestor.add(datetime.now() + timedelta(hours=2), "dos")
    assert gestor.cancel("todos") == 2
    assert gestor.pending() == []


def test_cancelar_solo_uno(gestor):
    gestor.add(datetime.now() + timedelta(hours=1), "dentista")
    gestor.add(datetime.now() + timedelta(hours=2), "gimnasio")
    assert gestor.cancel("dentista") == 1
    assert len(gestor.pending()) == 1


def test_un_archivo_corrupto_no_impide_arrancar(tmp_path, monkeypatch):
    fichero = tmp_path / "avisos.json"
    fichero.write_text("{ esto no es json válido", encoding="utf-8")
    monkeypatch.setattr(reminders, "REMINDERS_FILE", fichero)
    assert ReminderManager().pending() == []


# --------------------------------------------------------------------------
# Las órdenes habladas
# --------------------------------------------------------------------------

def test_poner_un_temporizador(gestor):
    router = CommandRouter(reminder_manager=gestor)
    resultado = router.handle("ponme un temporizador de 10 minutos")
    assert resultado.ok
    assert len(gestor.pending()) == 1
    assert "10 minutos" in resultado.message


def test_recordatorio_con_asunto(gestor):
    router = CommandRouter(reminder_manager=gestor)
    router.handle("recuérdame en 5 minutos que saque la basura")
    assert gestor.pending()[0].text == "saque la basura"


def test_alarma_a_una_hora(gestor):
    router = CommandRouter(reminder_manager=gestor)
    resultado = router.handle("despiértame a las 7 de la mañana")
    assert resultado.ok
    aviso = gestor.pending()[0]
    assert aviso.when.hour == 7
    assert aviso.kind == "alarma"


def test_consultar_los_avisos(gestor):
    gestor.add(datetime.now() + timedelta(minutes=30), "café")
    router = CommandRouter(reminder_manager=gestor)
    resultado = router.handle("qué alarmas tengo")
    assert "café" in resultado.message


def test_sin_avisos_lo_dice(gestor):
    router = CommandRouter(reminder_manager=gestor)
    assert "ningún aviso" in router.handle("qué alarmas tengo").message


def test_cancelar_por_voz(gestor):
    gestor.add(datetime.now() + timedelta(minutes=30), "algo")
    router = CommandRouter(reminder_manager=gestor)
    resultado = router.handle("cancela las alarmas")
    assert resultado.ok
    assert gestor.pending() == []


def test_temporizador_sin_tiempo_pregunta(gestor):
    router = CommandRouter(reminder_manager=gestor)
    resultado = router.handle("ponme un temporizador")
    assert not resultado.ok
    assert "cuánto tiempo" in resultado.message


def test_poner_musica_no_crea_un_aviso(gestor):
    """«pon música» empieza por «pon», pero no es un temporizador."""
    from .dobles import sistema_simulado
    with sistema_simulado() as registro:
        CommandRouter(reminder_manager=gestor).handle("pon música")
        assert registro.primera == "musica"
        assert gestor.pending() == []
