"""
Script de migración: actualiza una base de datos que ya existía ANTES
de este cambio (columnas y tablas nuevas para modalidad fija/libre,
horarios fijos, campanita de cupo y recordatorios), sin perder los
datos que ya estaban cargados.

Se puede correr las veces que haga falta: es "idempotente" (si una
columna ya existe no la vuelve a crear, si un plan ya tiene el nombre
correcto no lo toca).

    python migrar_datos.py
"""

from app import create_app
from app.extensions import db
from app.models import Plan
from app.db_constraints import crear_restricciones_concurrencia
from app.db_migrations import aplicar_migraciones_pendientes

app = create_app()

# Los 4 planes del estudio. Se identifican por la cantidad de clases
# por mes (no por el nombre), así si alguno ya existía con otro nombre
# (ej: "Plan libre (12 clases/mes)") lo renombramos en vez de duplicarlo.
PLANES_ESPERADOS = [
    ("4 clases por mes", 4),
    ("8 clases por mes", 8),
    ("12 clases por mes", 12),
    ("16 clases por mes", 16),
]

with app.app_context():
    # 1) Tablas nuevas (inscripciones_fijas, avisos_cupo): create_all()
    # solo crea las tablas que faltan, no toca las que ya existen.
    db.create_all()
    print("Tablas nuevas verificadas/creadas.")

    # 2) Columnas nuevas en tablas ya existentes. La lista y la lógica
    # viven en app/db_migrations.py (no acá) porque seed.py -el que
    # corre Render en cada arranque- necesita aplicar exactamente lo
    # mismo; si esto viviera solo en este script, una columna nueva
    # nunca llegaría a producción.
    aplicar_migraciones_pendientes(db.engine, verboso=True)

    # 3) Planes: nos aseguramos de que existan exactamente estos 4, sin
    # borrar ni recrear los que ya estén en uso por algún alumno (los
    # actualizamos por cantidad de clases, no por nombre).
    for nombre, clases_por_mes in PLANES_ESPERADOS:
        plan = Plan.query.filter_by(clases_por_mes=clases_por_mes).first()
        if plan:
            if plan.nombre != nombre:
                print(f"  · plan renombrado: '{plan.nombre}' -> '{nombre}'")
                plan.nombre = nombre
            plan.activo = True
        else:
            db.session.add(Plan(nombre=nombre, clases_por_mes=clases_por_mes))
            print(f"  + plan creado: {nombre}")
    db.session.commit()
    print("Planes verificados: 4, 8, 12 y 16 clases por mes.")

    # 4) Índice único parcial + triggers que anulan condiciones de
    # carrera en la reserva de turnos (ver app/db_constraints.py). Si
    # ya hay datos que violarían estas reglas (ej: alguien quedó
    # reservado dos veces en la misma clase por un bug viejo), esto va
    # a fallar con un error explícito en vez de crear la restricción a
    # medias - hay que limpiar esos datos primero.
    crear_restricciones_concurrencia(db.engine)
    print("Restricciones de concurrencia (índice + triggers de cupo) verificadas/creadas.")

    print("Migración completa.")
