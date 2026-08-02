"""
INTEGRACIÓN CON GOOGLE CALENDAR
================================
Cómo funciona (en criollo): cuando un alumno reserva un turno, además
de guardarlo en NUESTRA base de datos, creamos un evento en el
calendario de Google del estudio. Si cancela, borramos ese evento.

Usamos una "cuenta de servicio" (Service Account) en vez del login
personal de un usuario. Es la forma correcta de hacer esto para una
app que corre sola en un servidor, sin que haya una persona logueada
del otro lado aprobando el acceso cada vez. Ver el README para cómo
configurarla paso a paso (son ~10 minutos, todo gratis).

DISEÑO IMPORTANTE: si Google Calendar todavía no está configurado (o
falla por lo que sea: sin internet, credenciales vencidas, etc.), la
turnera tiene que seguir funcionando igual con el calendario propio.
Por eso todas las funciones acá abajo "fallan en silencio": si algo
sale mal, devuelven None y guardan un aviso en el log, en vez de
romper la reserva del alumno.
"""

from datetime import datetime, timedelta

from flask import current_app


def _obtener_servicio():
    """
    Arma el cliente de la API de Google Calendar autenticado con la
    cuenta de servicio. Devuelve None si la integración no está
    configurada o si algo falla al armar las credenciales.
    """
    if not current_app.config.get("GOOGLE_CALENDAR_HABILITADO"):
        return None

    try:
        # Importamos acá adentro (no arriba del archivo) para que el
        # resto de la app funcione perfecto aunque estas librerías
        # todavía no estén instaladas mientras se prueba el resto.
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credenciales = service_account.Credentials.from_service_account_file(
            current_app.config["GOOGLE_SERVICE_ACCOUNT_FILE"],
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        return build("calendar", "v3", credentials=credenciales, cache_discovery=False)
    except Exception as error:
        current_app.logger.warning(f"No se pudo inicializar Google Calendar: {error}")
        return None


def crear_evento_para_reserva(reserva):
    """
    Crea un evento en el calendario de Google para una Reserva ya
    guardada en nuestra base de datos. Devuelve el ID del evento
    creado (para poder borrarlo después) o None si no se pudo crear.
    """
    servicio = _obtener_servicio()
    if servicio is None:
        return None

    clase = reserva.clase
    usuario = reserva.usuario

    inicio = datetime.combine(clase.fecha, clase.hora_inicio)
    fin = inicio + timedelta(minutes=current_app.config["DURACION_CLASE_MINUTOS"])

    evento = {
        "summary": f"Pilates — {usuario.nombre_completo}",
        "description": (
            f"Turno reservado por {usuario.nombre_completo} ({usuario.email}).\n"
            f"{'Clase de recuperación.' if reserva.es_recuperacion else ''}"
        ),
        "start": {"dateTime": inicio.isoformat(), "timeZone": "America/Argentina/Buenos_Aires"},
        "end": {"dateTime": fin.isoformat(), "timeZone": "America/Argentina/Buenos_Aires"},
    }

    try:
        resultado = servicio.events().insert(
            calendarId=current_app.config["GOOGLE_CALENDAR_ID"], body=evento
        ).execute()
        return resultado.get("id")
    except Exception as error:
        current_app.logger.warning(f"No se pudo crear el evento en Google Calendar: {error}")
        return None


def eliminar_evento(google_event_id):
    """
    Borra un evento del calendario de Google (cuando el alumno
    cancela un turno). Si falla, no rompemos la cancelación en
    nuestro sistema: la reserva se cancela igual, el evento en
    Google puede quedar huérfano y el admin lo borra a mano si hace
    falta - preferimos eso a que la cancelación falle por completo.
    """
    if not google_event_id:
        return

    servicio = _obtener_servicio()
    if servicio is None:
        return

    try:
        servicio.events().delete(
            calendarId=current_app.config["GOOGLE_CALENDAR_ID"], eventId=google_event_id
        ).execute()
    except Exception as error:
        current_app.logger.warning(f"No se pudo borrar el evento {google_event_id} de Google Calendar: {error}")
