"""
Nombres de mes y de día de la semana en español.

Python usa el locale del sistema operativo para strftime('%B')/('%A'),
y en la mayoría de los servidores (sobre todo Windows) ese locale es
"C"/inglés por default, así que devuelven "August"/"Monday" en vez de
"agosto"/"lunes". En vez de depender de que el locale correcto esté
instalado en cada máquina donde corra esto, armamos las listas a mano
e indexamos por número de mes/día (ver create_app en app/__init__.py,
donde se registran como filtros de Jinja "mes_es" y "dia_semana_es").
"""

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
