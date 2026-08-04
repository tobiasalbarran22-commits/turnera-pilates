"""
Acá usamos el patrón "Application Factory": en vez de crear la app de
Flask como una variable global, la creamos DENTRO de una función
(create_app). Esto tiene dos ventajas grandes:
1. Podemos crear varias instancias de la app con configuraciones
   distintas (ej: una para testing, otra para producción).
2. Evita los imports circulares que mencionamos en extensions.py.
"""

import os
from flask import Flask

from config import config_por_nombre
from app.extensions import db, login_manager, bcrypt, csrf


def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=True)

    # Si no se especifica, usamos la variable de entorno FLASK_ENV,
    # y si tampoco existe, "default" (desarrollo).
    config_name = config_name or os.environ.get("FLASK_ENV", "default")
    app.config.from_object(config_por_nombre[config_name])

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
        return response

    return app
