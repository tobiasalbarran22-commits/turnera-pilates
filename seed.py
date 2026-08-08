"""
Script de inicialización. Se corre UNA sola vez (o cada vez que
querramos resetear la base de datos desde cero) con:

    python seed.py

Hace dos cosas:
1. Crea todas las tablas en la base de datos (a partir de los
   modelos definidos en app/models.py).
2. Crea un usuario administrador inicial, para poder entrar por
   primera vez al sistema (si no, nadie podría loguearse nunca,
   porque solo un admin puede crear usuarios).
"""

from app import create_app
from app.extensions import db
from app.models import Usuario, Plan
from app.db_constraints import crear_restricciones_concurrencia
from app.db_migrations import aplicar_migraciones_pendientes

app = create_app()

with app.app_context():
    db.create_all()
    print("Tablas creadas correctamente.")

    # create_all() crea las TABLAS que faltan, pero no agrega columnas
    # nuevas a una tabla que ya existía. Este script es el que corre
    # Render en cada arranque (ver render.yaml), así que tiene que
    # aplicar también las columnas nuevas - si no, la primera consulta
    # después de un deploy con un modelo cambiado falla con
    # "no such column" sobre la base real. Ver app/db_migrations.py.
    agregadas = aplicar_migraciones_pendientes(db.engine)
    print(f"Migraciones de columnas verificadas ({agregadas} agregada/s).")

    # db.create_all() solo crea las tablas que salen de los modelos de
    # SQLAlchemy - el índice único parcial y los triggers que evitan
    # sobreturnos por condiciones de carrera hay que crearlos aparte.
    crear_restricciones_concurrencia(db.engine)
    print("Restricciones de concurrencia (índice + triggers de cupo) verificadas/creadas.")

    # Evitamos crear un admin duplicado si el script se corre más de una vez
    email_admin = "admin@estudio.com"
    if not Usuario.query.filter_by(email=email_admin).first():
        admin = Usuario(
            nombre="Admin",
            apellido="Estudio",
            email=email_admin,
            rol="admin",
        )
        admin.set_password("cambiar123")  # ⚠️ cambiar esta contraseña apenas entres
        db.session.add(admin)
        print(f"Usuario admin creado -> email: {email_admin} / contraseña: cambiar123")
    else:
        print("El usuario admin ya existía, no se creó de nuevo.")

    # Los 4 planes del estudio: 4, 8, 12 y 16 clases por mes.
    if not Plan.query.first():
        db.session.add_all([
            Plan(nombre="4 clases por mes", clases_por_mes=4),
            Plan(nombre="8 clases por mes", clases_por_mes=8),
            Plan(nombre="12 clases por mes", clases_por_mes=12),
            Plan(nombre="16 clases por mes", clases_por_mes=16),
        ])
        print("Planes creados: 4, 8, 12 y 16 clases por mes.")

    db.session.commit()
    print("Listo. Ya podés correr: python run.py")
