"""
Manda por mail el recordatorio de "mañana tenés clase" a todos los
alumnos con una reserva activa para el día siguiente.

El sistema NO lo hace solo: hay que programar este script para que se
corra UNA vez por día (por ejemplo a las 20:00), usando el Programador
de tareas de Windows o un cron job si el estudio despliega en Linux.

    python enviar_recordatorios.py

Requiere tener configurado el envío de mails (variables de entorno
MAIL_USUARIO / MAIL_PASSWORD, ver README). Si no está configurado, el
script corre igual pero no manda nada (0 recordatorios enviados).
"""

from app import create_app
from app.alumno.services import enviar_recordatorios_del_dia_siguiente

app = create_app()

with app.app_context():
    cantidad = enviar_recordatorios_del_dia_siguiente()
    print(f"Recordatorios enviados: {cantidad}")
