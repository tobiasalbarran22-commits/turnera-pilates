"""
Utilidades de fecha/hora: horario de Buenos Aires y nombres en español.

Todos los horarios de clase (Horario.hora, Clase.fecha/hora_inicio) los
carga el admin pensando en la hora del estudio en Buenos Aires - nunca
en la hora del servidor. Si el servidor donde corre la app está en otra
zona horaria (lo más común en hosting: UTC), usar datetime.now()/
date.today() directamente compararía la hora del estudio contra la hora
del servidor y correría todo desfasado (ej: una clase de las 9 AM
apareciendo como "ya pasada" a las 6 AM hora de Buenos Aires, o el
"día de hoy" cambiando a medianoche UTC en vez de medianoche local).
Por eso, en vez de datetime.now()/date.today(), todo el código de
negocio usa ahora_estudio()/hoy_estudio() de acá, que siempre calculan
la hora actual EN Buenos Aires sin importar en qué zona horaria esté
el servidor. (Se llaman así, y no simplemente ahora()/hoy(), para no
pisar las variables locales "ahora"/"hoy" que ya se usan en todo el
código para guardar el resultado.)
"""

from datetime import datetime
from zoneinfo import ZoneInfo

ZONA_HORARIA_ESTUDIO = ZoneInfo("America/Argentina/Buenos_Aires")


def ahora_estudio():
    """
    Fecha y hora actual en Buenos Aires (UTC-3, sin horario de verano),
    como datetime "naive" (sin tzinfo). La devolvemos naive a propósito:
    Horario.hora y Clase.fecha/hora_inicio también son naive y
    representan directamente la hora del estudio, así que hace falta
    que "ahora" esté en las mismas unidades para poder compararlos o
    restarlos sin tener que convertir cada Clase a aware por separado.
    """
    return datetime.now(ZONA_HORARIA_ESTUDIO).replace(tzinfo=None)


def hoy_estudio():
    return ahora_estudio().date()


MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

DIAS_SEMANA_ES = [
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
]


def nombre_mes(fecha):
    return MESES_ES[fecha.month - 1]


def nombre_dia_semana(fecha):
    return DIAS_SEMANA_ES[fecha.weekday()]
