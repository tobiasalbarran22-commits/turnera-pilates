"""
Restricciones que hace cumplir la BASE DE DATOS MISMA para anular
condiciones de carrera en la reserva de turnos.

El problema: en reservar_clase (app/alumno/services.py) primero se
chequea en Python "¿hay cupo?" / "¿ya está reservado?" y RECIÉN
DESPUÉS se hace el INSERT de la Reserva. Si dos requests concurrentes
(dos alumnos apretando "Reservar" en el último lugar libre al mismo
tiempo, o el mismo alumno haciendo doble clic) pasan ese chequeo casi
al mismo instante, ninguno de los dos ve todavía el INSERT del otro:
los dos creen que hay cupo, y los dos terminan reservando - la clase
queda con más gente de la que su cupo_maximo permite.

SQLite no bloquea filas en un SELECT (solo al escribir), así que ese
"chequear y después actuar" en Python nunca es atómico por sí solo. La
única forma de cerrar esa ventana de verdad es que la propia base de
datos rechace el INSERT si viola la regla, sin importar qué haya visto
el código Python antes de intentarlo:

- Un índice ÚNICO PARCIAL evita que un mismo alumno quede con dos
  Reservas "reservada" activas para la misma Clase (doble clic/doble
  submit). Es "parcial" (con WHERE) porque sí tiene que poder volver a
  reservar esa misma Clase después de cancelar - ahí ya no hay ninguna
  fila con estado="reservada" para ese par, así que no choca.

- Un TRIGGER evita que una Clase termine con más Reservas "reservada"
  activas que su cupo_maximo, sin importar cuántos requests
  concurrentes intenten reservar el último lugar al mismo tiempo.

Ambas cosas viven acá (no como una migración de Alembic - este
proyecto no lo usa) y se aplican tanto desde seed.py (bases nuevas)
como desde migrar_datos.py (bases ya existentes), para que las dos
terminen siempre con las mismas restricciones. Son idempotentes
(se pueden correr las veces que hagan falta sin romper nada).

OJO si el día de mañana se migra de SQLite a otro motor (ej.
Postgres, como se charló para el despliegue en producción): esta
sintaxis (índice parcial + trigger con RAISE) es específica de
SQLite. Postgres logra lo mismo con un índice único parcial (misma
idea) más una función/trigger en PL/pgSQL, o directamente con un
EXCLUDE constraint - habría que reescribir esta parte, no se traduce
sola.
"""

SQL_RESTRICCIONES_CONCURRENCIA = [
    # Un alumno no puede tener dos Reservas "reservada" activas para
    # la misma Clase.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_reserva_activa_por_clase
    ON reservas(usuario_id, clase_id)
    WHERE estado = 'reservada'
    """,
    # Ninguna Clase puede superar su cupo_maximo de Reservas
    # "reservada" activas al CREARSE una reserva nueva.
    """
    CREATE TRIGGER IF NOT EXISTS trg_reserva_insert_respeta_cupo
    BEFORE INSERT ON reservas
    FOR EACH ROW WHEN NEW.estado = 'reservada'
    BEGIN
        SELECT RAISE(ABORT, 'CUPO_LLENO')
        WHERE (
            SELECT COUNT(*) FROM reservas
            WHERE clase_id = NEW.clase_id AND estado = 'reservada'
        ) >= (SELECT cupo_maximo FROM clases WHERE id = NEW.clase_id);
    END
    """,
    # Mismo chequeo si algún día se reactivara una reserva cancelada
    # con un UPDATE en vez de crear una fila nueva (hoy no pasa en el
    # código, pero así queda blindado igual).
    """
    CREATE TRIGGER IF NOT EXISTS trg_reserva_update_respeta_cupo
    BEFORE UPDATE OF estado ON reservas
    FOR EACH ROW WHEN NEW.estado = 'reservada' AND OLD.estado != 'reservada'
    BEGIN
        SELECT RAISE(ABORT, 'CUPO_LLENO')
        WHERE (
            SELECT COUNT(*) FROM reservas
            WHERE clase_id = NEW.clase_id AND estado = 'reservada' AND id != NEW.id
        ) >= (SELECT cupo_maximo FROM clases WHERE id = NEW.clase_id);
    END
    """,
]


def crear_restricciones_concurrencia(engine):
    conexion = engine.raw_connection()
    try:
        for sentencia in SQL_RESTRICCIONES_CONCURRENCIA:
            conexion.execute(sentencia)
        conexion.commit()
    finally:
        conexion.close()
