"""
ENVÍO DE EMAILS
================
Tres tipos de mail que manda el sistema:
1. Confirmación: "tu clase quedó reservada" (al momento de reservar).
2. Recordatorio: "mañana tenés clase" (un script aparte lo corre una
   vez por día, ver enviar_recordatorios.py en la raíz del proyecto).
3. Aviso de cupo liberado (la "campanita"): un alumno pidió que le
   avisen si se libera un lugar en una clase llena, y se liberó.

Usamos SMTP simple (smtplib, de la librería estándar de Python) en vez
de atar el proyecto a un proveedor en particular: sirve con Gmail,
Outlook, o cualquier SMTP que el estudio ya tenga contratado.

Mismo diseño que la integración con Google Calendar (ver
app/integrations/google_calendar.py): si el mail no está configurado,
o si falla el envío (sin internet, credenciales vencidas, etc.), el
sistema tiene que seguir funcionando igual. Una reserva o una
cancelación NUNCA deben fallar por un mail que no se pudo mandar.
"""

import smtplib
from email.mime.text import MIMEText

from flask import current_app


def _enviar(destinatario, asunto, cuerpo_html):
    if not current_app.config.get("MAIL_HABILITADO"):
        return False

    try:
        mensaje = MIMEText(cuerpo_html, "html", "utf-8")
        mensaje["Subject"] = asunto
        mensaje["From"] = current_app.config["MAIL_REMITENTE"]
        mensaje["To"] = destinatario

        with smtplib.SMTP(current_app.config["MAIL_SERVIDOR"], current_app.config["MAIL_PUERTO"], timeout=10) as servidor:
            servidor.starttls()
            servidor.login(current_app.config["MAIL_USUARIO"], current_app.config["MAIL_PASSWORD"])
            servidor.sendmail(current_app.config["MAIL_REMITENTE"], [destinatario], mensaje.as_string())
        return True
    except Exception as error:
        current_app.logger.warning(f"No se pudo enviar el email a {destinatario}: {error}")
        return False


def enviar_confirmacion_reserva(reserva):
    clase = reserva.clase
    usuario = reserva.usuario
    asunto = f"Reserva confirmada — {clase.fecha.strftime('%d/%m')} {clase.hora_inicio.strftime('%H:%M')}hs"
    cuerpo = f"""
        <p>Hola {usuario.nombre},</p>
        <p>Tu turno quedó reservado para el <strong>{clase.fecha.strftime('%d/%m/%Y')}</strong>
        a las <strong>{clase.hora_inicio.strftime('%H:%M')}hs</strong>.</p>
        <p>¡Te esperamos!</p>
    """
    return _enviar(usuario.email, asunto, cuerpo)


def enviar_recordatorio_clase(reserva):
    clase = reserva.clase
    usuario = reserva.usuario
    asunto = f"Recordatorio — mañana tenés clase a las {clase.hora_inicio.strftime('%H:%M')}hs"
    cuerpo = f"""
        <p>Hola {usuario.nombre},</p>
        <p>Te recordamos que <strong>mañana {clase.fecha.strftime('%d/%m/%Y')}</strong>
        tenés clase a las <strong>{clase.hora_inicio.strftime('%H:%M')}hs</strong>.</p>
    """
    return _enviar(usuario.email, asunto, cuerpo)


def enviar_aviso_cupo_liberado(aviso):
    clase = aviso.clase
    usuario = aviso.usuario
    asunto = f"¡Se liberó un lugar! — {clase.fecha.strftime('%d/%m')} {clase.hora_inicio.strftime('%H:%M')}hs"
    cuerpo = f"""
        <p>Hola {usuario.nombre},</p>
        <p>Se liberó un lugar en la clase del <strong>{clase.fecha.strftime('%d/%m/%Y')}</strong>
        a las <strong>{clase.hora_inicio.strftime('%H:%M')}hs</strong> que estabas esperando.</p>
        <p>Entrá a la turnera y reservalo antes de que se ocupe de nuevo.</p>
    """
    return _enviar(usuario.email, asunto, cuerpo)
