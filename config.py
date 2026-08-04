import os
from datetime import timedelta

from dotenv import load_dotenv

# BASE_DIR apunta a la carpeta raíz del proyecto.
# Lo usamos para que la base de datos SQLite se guarde siempre en el mismo
# lugar sin importar desde dónde se ejecute el programa.
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Cargamos las variables de entorno desde un archivo .env en la raíz
# del proyecto (si existe). Así, en vez de tener que escribir
# `$env:MAIL_USUARIO = "..."` en cada sesión de PowerShell, las
# credenciales quedan guardadas en un archivo local (que NUNCA se
# sube al repo: ya está en .gitignore).
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    """
    Configuración base de la app. Todo lo que ponemos acá se puede
    sobreescribir con variables de entorno (más seguro para producción,
    donde NO queremos que la SECRET_KEY quede escrita en el código).
    """

    # SECRET_KEY: la usa Flask para firmar las cookies de sesión y
    # proteger los formularios contra ataques CSRF. En producción esto
    # SIEMPRE debe venir de una variable de entorno, nunca hardcodeado.
    SECRET_KEY = os.environ.get("SECRET_KEY", "clave-de-desarrollo-cambiar-en-produccion")

    # Ubicación de la base de datos SQLite. SQLite guarda todo en un
    # único archivo (instance/turnera.db), no necesita un servidor
    # aparte, y no cuesta nada -> ideal para arrancar el proyecto.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'turnera.db')}"
    )

    # Desactivamos el sistema de tracking de modificaciones de SQLAlchemy:
    # consume memoria extra y no lo necesitamos.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Reglas de negocio del estudio de pilates ---
    # Las dejamos acá, como configuración, en vez de "hardcodeadas" en el
    # código, para que el día de mañana sea fácil cambiarlas sin tocar
    # la lógica interna.

    CUPO_MAXIMO_POR_CLASE = 5          # alumnos máximo por clase
    DURACION_CLASE_MINUTOS = 60        # duración de cada clase
    HORAS_MINIMAS_PARA_CANCELAR = 4    # para poder recuperar la clase
    MAX_CLASES_RECUPERABLES = 3        # tope de clases acumulables
    DIAS_A_FUTURO_RESERVA = 31         # el alumno reserva "dentro del mismo mes"

    # --- Integración con Google Calendar ---
    # Usamos una "cuenta de servicio" de Google (Service Account), NO
    # el login personal de nadie. Es un usuario "robot" que Google te
    # da gratis, al que le compartís el calendario del estudio, y así
    # el sistema puede crear/borrar eventos sin que ningún alumno ni
    # admin tenga que "iniciar sesión con Google" nunca.
    #
    # GOOGLE_CALENDAR_ID: el email/ID del calendario del estudio
    # (lo sacás desde la configuración de ese calendario en Google
    # Calendar > "Integrar calendario" > "ID de calendario").
    GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "")

    # Ruta al archivo .json con las credenciales de la cuenta de
    # servicio (se descarga una sola vez desde Google Cloud Console).
    # Ver el README para el paso a paso completo.
    GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_FILE", os.path.join(BASE_DIR, "google-credentials.json")
    )

    # Si no hay calendario configurado, el sistema sigue funcionando
    # igual (con el calendario propio), simplemente sin sincronizar
    # a Google. Así no depende de que Google Calendar esté armado
    # para poder seguir probando el resto del sistema.
    GOOGLE_CALENDAR_HABILITADO = bool(GOOGLE_CALENDAR_ID) and os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE)

    # --- Envío de emails (confirmación de reserva, recordatorio del
    # día anterior, aviso de "se liberó un cupo") ---
    # Usamos SMTP simple: sirve con Gmail, Outlook o el SMTP que ya
    # tenga el estudio. Si no está configurado, el sistema sigue
    # funcionando igual, simplemente sin mandar mails (mismo criterio
    # que la integración con Google Calendar).
    MAIL_SERVIDOR = os.environ.get("MAIL_SERVIDOR", "smtp.gmail.com")
    MAIL_PUERTO = int(os.environ.get("MAIL_PUERTO", 587))
    MAIL_USUARIO = os.environ.get("MAIL_USUARIO", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_REMITENTE = os.environ.get("MAIL_REMITENTE", MAIL_USUARIO)
    MAIL_HABILITADO = bool(MAIL_USUARIO and MAIL_PASSWORD)

    # --- Redes y contacto del estudio (landing page) ---
    # WHATSAPP_NUMERO: formato wa.me, sin "+" ni espacios (código de
    # país + código de área sin el 0 + número sin el 15).
    WHATSAPP_NUMERO = os.environ.get("WHATSAPP_NUMERO", "5491137723875")
    INSTAGRAM_URL = os.environ.get("INSTAGRAM_URL", "https://www.instagram.com/benincasapilates/")
    DIRECCION_ESTUDIO = os.environ.get(
        "DIRECCION_ESTUDIO", "Campana 1495, Villa Santa Rita, CABA, Argentina"
    )


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # En producción, SECRET_KEY y DATABASE_URL DEBEN venir de variables
    # de entorno del servidor (Render, Railway, PythonAnywhere, etc.)


config_por_nombre = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
