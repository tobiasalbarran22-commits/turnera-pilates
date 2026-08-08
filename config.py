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

# Valor de SECRET_KEY solo para desarrollo local, cuando no hay
# variable de entorno definida. Queda como constante aparte (no
# escrita directo adentro de Config) para que app/__init__.py pueda
# comparar contra este mismo valor exacto y detectar si en producción
# se coló este default en vez de una clave real - ver el chequeo en
# create_app().
SECRET_KEY_DEV_DEFAULT = "clave-de-desarrollo-cambiar-en-produccion"


class Config:
    """
    Configuración base de la app. Todo lo que ponemos acá se puede
    sobreescribir con variables de entorno (más seguro para producción,
    donde NO queremos que la SECRET_KEY quede escrita en el código).
    """

    # SECRET_KEY: la usa Flask para firmar las cookies de sesión y
    # proteger los formularios contra ataques CSRF. En producción esto
    # SIEMPRE debe venir de una variable de entorno, nunca hardcodeado.
    SECRET_KEY = os.environ.get("SECRET_KEY", SECRET_KEY_DEV_DEFAULT)

    # Ubicación de la base de datos SQLite. SQLite guarda todo en un
    # único archivo (instance/turnera.db), no necesita un servidor
    # aparte, y no cuesta nada -> ideal para arrancar el proyecto.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'turnera.db')}"
    )

    # Desactivamos el sistema de tracking de modificaciones de SQLAlchemy:
    # consume memoria extra y no lo necesitamos.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Cookies de sesión: banderas de seguridad ---
    # HttpOnly ya es el default de Flask (JS del navegador no puede leer
    # la cookie ni aunque hubiera un XSS) y SameSite=Lax ya es el
    # default de los navegadores modernos desde 2020 - las dejamos acá
    # de forma explícita en vez de confiar en el default silencioso.
    # "Lax" (no "Strict") para que un link externo (WhatsApp, Instagram,
    # un favorito guardado) que lleve directo a una página con sesión
    # siga funcionando sin desloguear a nadie.
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SAMESITE = "Lax"

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
    # La cuenta de Gmail del estudio: todos los mails del sistema salen
    # desde acá. MAIL_USUARIO es la cuenta que se autentica contra el
    # servidor SMTP de Gmail - por eso también es el remitente por
    # default (Gmail no deja mandar con un "From" distinto al de la
    # cuenta autenticada, salvo que se configure un alias). La
    # contraseña NUNCA tiene un default: tiene que venir sí o sí de la
    # variable de entorno MAIL_PASSWORD, usando una "contraseña de
    # aplicación" de Google (ver README).
    MAIL_SERVIDOR = os.environ.get("MAIL_SERVIDOR", "smtp.gmail.com")
    MAIL_PUERTO = int(os.environ.get("MAIL_PUERTO", 587))
    MAIL_USUARIO = os.environ.get("MAIL_USUARIO", "benincasapilates@gmail.com")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_REMITENTE = os.environ.get("MAIL_REMITENTE", MAIL_USUARIO)
    MAIL_HABILITADO = bool(MAIL_USUARIO and MAIL_PASSWORD)

    # --- Tarea programada: recordatorio diario ---
    # Token compartido que valida las llamadas a /tareas/recordatorios
    # (ver app/public/routes.py). Sin default: si no está configurado,
    # esa ruta rechaza cualquier llamada (ver el chequeo "if not
    # token_esperado" en la ruta) en vez de quedar abierta por error.
    TAREAS_SECRETO = os.environ.get("TAREAS_SECRETO", "")

    # --- Redes y contacto del estudio (landing page) ---
    # WHATSAPP_NUMERO: formato wa.me, sin "+" ni espacios (código de
    # país + código de área sin el 0 + número sin el 15).
    WHATSAPP_NUMERO = os.environ.get("WHATSAPP_NUMERO", "5491137723875")
    INSTAGRAM_URL = os.environ.get("INSTAGRAM_URL", "https://www.instagram.com/benincasapilates/")
    DIRECCION_ESTUDIO = os.environ.get(
        "DIRECCION_ESTUDIO", "Campana 1495, Villa Santa Rita, CABA, Argentina"
    )

    # --- SEO ---
    # SITIO_URL: la dirección DEFINITIVA del sitio, sin barra final
    # (ej: "https://www.benincasapilates.com.ar"). Importa más de lo
    # que parece: si el mismo contenido se puede abrir en dos dominios
    # distintos (el .onrender.com y el propio, o con y sin "www"),
    # Google lo ve como dos sitios con contenido duplicado y reparte
    # entre los dos la autoridad que debería concentrarse en uno solo.
    # Con esto definido, la app arma SIEMPRE los links absolutos
    # (canonical, sitemap, Open Graph, JSON-LD) apuntando a esta
    # dirección y redirige con 301 cualquier otro dominio hacia ella
    # (ver app/__init__.py). Si queda vacío, cada URL absoluta se arma
    # con el dominio por el que entró la visita, que es lo que hacía
    # antes: funciona, pero no protege contra el duplicado.
    SITIO_URL = os.environ.get("SITIO_URL", "").rstrip("/")

    # Coordenadas exactas del estudio, para los datos estructurados
    # (schema.org GeoCoordinates). Google las usa para el "local pack"
    # (el mapita con los 3 negocios que aparece arriba de todo en
    # búsquedas como "pilates villa santa rita"). Se sacan abriendo el
    # estudio en Google Maps, click derecho sobre el punto exacto: el
    # primer número que aparece es la latitud y el segundo la longitud.
    # Se dejan VACÍAS a propósito: un par de coordenadas inventadas o
    # aproximadas es peor que ninguna (le diría a Google que el estudio
    # está en una cuadra donde no está). Si están vacías, el bloque
    # "geo" simplemente no se incluye.
    ESTUDIO_LATITUD = os.environ.get("ESTUDIO_LATITUD", "")
    ESTUDIO_LONGITUD = os.environ.get("ESTUDIO_LONGITUD", "")

    # Horarios de atención, para el mismo bloque de datos
    # estructurados (Google puede mostrar "Abierto ahora / Cierra a las
    # X" en los resultados). Formato: cada línea es
    # "Dia[,Dia...] HH:MM-HH:MM", con los días en inglés porque es lo
    # que espera schema.org (Monday, Tuesday, Wednesday, Thursday,
    # Friday, Saturday, Sunday). Ejemplo de un valor real:
    #     "Monday,Tuesday,Wednesday,Thursday,Friday 08:00-21:00|Saturday 09:00-13:00"
    # Vacío por defecto, por la misma razón que las coordenadas: no
    # inventamos horarios que el estudio no confirmó.
    HORARIOS_ATENCION = os.environ.get("HORARIOS_ATENCION", "")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # En producción, SECRET_KEY y DATABASE_URL DEBEN venir de variables
    # de entorno del servidor (Render, Railway, PythonAnywhere, etc.)
    # - ver el chequeo en app/__init__.py:create_app() que hace fallar
    # el arranque si en producción se coló el default inseguro de acá
    # abajo (NO se puede chequear en el cuerpo de esta clase: el cuerpo
    # de una clase se ejecuta al importar el módulo, sin importar cuál
    # config vaya a usarse en definitiva - un "raise" acá adentro
    # tiraría abajo hasta el arranque en desarrollo).

    # Cookie "Secure": el navegador nunca la manda por HTTP, solo por
    # HTTPS. Va SOLO acá (no en Config, la clase base) porque en
    # desarrollo local se corre por http://127.0.0.1 sin HTTPS - si
    # esta bandera estuviera activa ahí, el navegador directamente no
    # guardaría la cookie y el login dejaría de funcionar en local.
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


config_por_nombre = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
