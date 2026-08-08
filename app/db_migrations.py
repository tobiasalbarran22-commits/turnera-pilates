"""
MIGRACIONES DE ESQUEMA (columnas nuevas en tablas que ya existen).

Por qué existe este archivo aparte de db.create_all(): create_all() SOLO
crea las tablas que faltan. Si a un modelo ya existente le agregamos una
columna nueva, create_all() no hace absolutamente nada - y la próxima
consulta a esa tabla falla con "no such column", porque SQLAlchemy
genera el SELECT con la columna nueva contra una tabla que todavía no
la tiene.

Eso ya era un problema latente de despliegue: render.yaml arranca la app
con `python seed.py && gunicorn run:app`, y seed.py solo llamaba a
create_all(). Las columnas nuevas vivían únicamente en migrar_datos.py,
que en producción no lo corre nadie -> cualquier columna agregada a un
modelo tiraba abajo la app en el próximo deploy, con la base ya cargada
de datos reales. Por eso la lista de columnas vive ACÁ y la aplican
tanto seed.py (cada arranque en Render) como migrar_datos.py (a mano en
local): las dos rutas terminan siempre con el mismo esquema.

Es idempotente: se puede correr las veces que haga falta.

OJO: la sintaxis (PRAGMA table_info + ALTER TABLE ADD COLUMN) es de
SQLite. Si algún día se migra a Postgres hay que reescribir esta parte
(o, mejor, pasar a Alembic, que es la herramienta pensada para esto).
"""

# (tabla, columna, definición SQL) de cada columna agregada a una tabla
# que ya podía existir en una base anterior. Agregar una fila acá es
# TODO lo que hace falta para que la columna llegue a producción.
COLUMNAS_NUEVAS = [
    ("usuarios", "modalidad", "VARCHAR(20) DEFAULT 'libre'"),
    ("reservas", "recordatorio_enviado", "BOOLEAN DEFAULT 0"),
    # Cuándo el admin canceló la clase entera. Sirve para distinguir las
    # reservas que canceló ESA acción (a las que hay que devolverles el
    # crédito si después se reactiva la clase) de las que el propio
    # alumno ya había cancelado por su cuenta antes - ver
    # admin/services.py: reactivar_clase.
    ("clases", "fecha_cancelada", "DATETIME"),
]


def _agregar_columna_si_falta(conexion, tabla, columna, definicion_sql, verboso=False):
    columnas_existentes = [fila[1] for fila in conexion.execute(f"PRAGMA table_info({tabla})").fetchall()]
    if columna not in columnas_existentes:
        conexion.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion_sql}")
        if verboso:
            print(f"  + columna {tabla}.{columna} agregada")
        return True
    if verboso:
        print(f"  · columna {tabla}.{columna} ya existía")
    return False


def aplicar_migraciones_pendientes(engine, verboso=False):
    """
    Agrega las columnas de COLUMNAS_NUEVAS que todavía no existan.
    Devuelve cuántas se agregaron.
    """
    conexion = engine.raw_connection()
    agregadas = 0
    try:
        for tabla, columna, definicion in COLUMNAS_NUEVAS:
            if _agregar_columna_si_falta(conexion, tabla, columna, definicion, verboso):
                agregadas += 1
        conexion.commit()
    finally:
        conexion.close()
    return agregadas
