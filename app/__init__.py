"""
Acá usamos el patrón "Application Factory": en vez de crear la app de
Flask como una variable global, la creamos DENTRO de una función
(create_app). Esto tiene dos ventajas grandes:
1. Podemos crear varias instancias de la app con configuraciones
   distintas (ej: una para testing, otra para producción).
2. Evita los imports circulares que mencionamos en extensions.py.
"""

import os
from urllib.parse import urlparse

from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from config import config_por_nombre, SECRET_KEY_DEV_DEFAULT
from app.extensions import db, login_manager, bcrypt, csrf


def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=True)

    # Render (donde se despliega esta app) termina el HTTPS en su propio
    # proxy y nos reenvía la request como HTTP simple, con un header
    # "X-Forwarded-Proto: https" avisando cuál era el protocolo real. Sin
    # este middleware, Flask no confía en ese header y cree que TODAS las
    # requests son HTTP - lo cual rompería el chequeo de HSTS de más
    # abajo y cualquier otra lógica que dependa de saber si la conexión
    # es segura. No agrega una dependencia nueva: ProxyFix ya viene con
    # Werkzeug (que Flask ya usa por dentro).
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # Si no se especifica, usamos la variable de entorno FLASK_ENV,
    # y si tampoco existe, "default" (desarrollo).
    config_name = config_name or os.environ.get("FLASK_ENV", "default")
    app.config.from_object(config_por_nombre[config_name])

    # En producción, jamás tiene que arrancar la app firmando
    # cookies/CSRF con el SECRET_KEY de desarrollo (hardcodeado en
    # config.py para que sea cómodo arrancar en local) - mejor que ni
    # arranque a que quede corriendo con una clave conocida. Este
    # chequeo va ACÁ (no en el cuerpo de ProductionConfig) porque el
    # cuerpo de una clase se ejecuta al importar el módulo sin importar
    # qué config se vaya a usar en definitiva - hacerlo ahí tiraría
    # abajo también el arranque en desarrollo. En Render esto no
    # cambia nada: render.yaml ya genera un SECRET_KEY real
    # automáticamente (generateValue: true), la variable de entorno
    # siempre está presente ahí.
    if config_name == "production" and app.config["SECRET_KEY"] == SECRET_KEY_DEV_DEFAULT:
        raise RuntimeError("SECRET_KEY debe estar definida por variable de entorno en producción.")

    # Nos aseguramos de que exista la carpeta "instance" (ahí vive
    # el archivo turnera.db de SQLite).
    os.makedirs(app.instance_path, exist_ok=True)

    # Conectamos cada extensión con esta app en particular
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)

    # Configuración de Flask-Login: a qué ruta mandar a alguien que
    # intenta entrar a una página protegida sin estar logueado.
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Iniciá sesión para continuar."
    login_manager.login_message_category = "info"

    # Filtros de Jinja para mostrar fechas en español (ver app/utils.py:
    # no confiamos en el locale del sistema para esto).
    from app.utils import nombre_mes, nombre_dia_semana
    app.jinja_env.filters["mes_es"] = nombre_mes
    app.jinja_env.filters["dia_semana_es"] = nombre_dia_semana

    @login_manager.user_loader
    def load_user(user_id):
        # Flask-Login llama a esta función en cada request para saber
        # qué usuario corresponde a la sesión activa.
        from app.models import Usuario
        return Usuario.query.get(int(user_id))

    # Registramos cada módulo (blueprint) de la app
    from app.auth import bp as auth_bp
    from app.admin import bp as admin_bp
    from app.alumno import bp as alumno_bp
    from app.public import bp as public_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(alumno_bp)
    # public: landing (/), robots.txt, sitemap.xml y, a futuro,
    # cualquier otra página sin login (/nosotros, /contacto, etc.) -
    # ver app/public/routes.py para cómo agregar una nueva.
    app.register_blueprint(public_bp)

    @app.before_request
    def _redirigir_al_dominio_canonico():
        # Un mismo sitio accesible por dos dominios (el .onrender.com y
        # el propio, o con y sin "www") es contenido duplicado para
        # Google: en vez de sumar, parte la autoridad en dos y ninguna
        # de las dos versiones rankea tan bien como rankearía una sola.
        # Si SITIO_URL está configurado (ver config.py), mandamos todo
        # el tráfico al dominio elegido con un 301 permanente, que es
        # la señal que Google entiende como "esta es LA dirección".
        #
        # Solo para GET/HEAD: redirigir un POST con 301 haría que el
        # navegador reenvíe el pedido sin el cuerpo y se pierdan datos
        # de un formulario. Y nunca para la tarea programada, que la
        # llama un curl que no sigue redirecciones.
        from flask import request, redirect as _redirect
        sitio_url = app.config.get("SITIO_URL")
        if not sitio_url or request.method not in ("GET", "HEAD"):
            return None
        host_canonico = urlparse(sitio_url).netloc
        if not host_canonico or request.host == host_canonico:
            return None
        return _redirect(sitio_url + request.full_path.rstrip("?"), code=301)

    @app.after_request
    def _sin_cache_en_paginas_dinamicas(response):
        # El calendario, "mis turnos", etc. cambian todo el tiempo
        # (reservas, cancelaciones de otras/os alumnas/os). Sin este
        # header, el botón "atrás" del navegador (o el caché normal de
        # una página HTML) puede mostrar una versión vieja guardada en
        # vez de pedirle al servidor los datos actuales - se ve como
        # "no se actualiza en tiempo real" aunque el dato en la base
        # ya esté bien.
        #
        # Ojo: esto tiene que aplicar SOLO a las páginas con sesión
        # (admin/alumno/auth), no a las públicas (landing, robots.txt,
        # sitemap.xml) ni a los archivos estáticos. La landing es una
        # página de marketing que no cambia por request - dejar que el
        # navegador la cachee normalmente es bueno para SEO (velocidad
        # de carga en visitas repetidas es una señal de ranking), y
        # bloquear el caché de robots.txt/sitemap.xml no tiene ningún
        # sentido para un buscador.
        from flask import request
        if request.blueprint in ("admin", "alumno", "auth"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            # Refuerzo del <meta name="robots"> de templates/base.html:
            # el header vale aunque el buscador no llegue a parsear el
            # HTML (ej. una respuesta de redirección al login, o un
            # PDF/JSON servido desde acá el día de mañana). robots.txt
            # pide no RASTREAR estas rutas; esto además prohíbe
            # INDEXARLAS, que son dos cosas distintas: una URL que
            # robots.txt bloquea puede igual aparecer en resultados si
            # alguien la enlaza desde afuera.
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.after_request
    def _headers_de_seguridad(response):
        # Headers HTTP de seguridad, en todas las respuestas. Ninguno de
        # estos cambia nada visible ni de comportamiento: son
        # instrucciones para el NAVEGADOR sobre cómo tratar la
        # respuesta, no algo que la página use o dependa de.
        #
        # OJO: a propósito no incluye Content-Security-Policy. El sitio
        # usa bastante style="" y algunos <script> inline en las
        # plantillas - una CSP que restrinja eso rompería la página tal
        # como está, y una CSP que lo permita todo ("unsafe-inline") no
        # suma protección real. Se prioriza no romper nada.
        from flask import request
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # Páginas de error propias. Además de verse mucho mejor que la
    # pantalla blanca por defecto de Flask, importan para SEO: si
    # Google entra a una URL que no existe (un link viejo, un typo de
    # alguien que compartió la dirección) tiene que recibir un 404 con
    # una página que se entienda, no un error crudo. Todas llevan
    # noindex por el template, y devuelven el código HTTP correcto -
    # que es lo que Google realmente lee para saber si sacar esa URL
    # de su índice.
    @app.errorhandler(400)
    def _error_400(e):
        return render_template("errores/error.html", codigo=400,
                               titulo="Pedido inválido",
                               detalle="Algo del formulario que mandaste no se entendió. Probá de nuevo."), 400

    @app.errorhandler(403)
    def _error_403(e):
        return render_template("errores/error.html", codigo=403,
                               titulo="No tenés permiso para ver esto",
                               detalle="Esta parte del sistema es solo para el estudio."), 403

    @app.errorhandler(404)
    def _error_404(e):
        return render_template("errores/error.html", codigo=404,
                               titulo="No encontramos esta página",
                               detalle="Puede que el link esté viejo o mal escrito."), 404

    @app.errorhandler(500)
    def _error_500(e):
        # Un 500 casi siempre deja la sesión de base de datos en un
        # estado inservible (una transacción a medio hacer). Sin este
        # rollback, los requests siguientes de ese mismo worker pueden
        # fallar en cadena por un error que ya pasó.
        db.session.rollback()
        return render_template("errores/error.html", codigo=500,
                               titulo="Se nos rompió algo",
                               detalle="Ya quedó registrado. Probá de nuevo en un rato."), 500

    return app
