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

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(alumno_bp)

    @app.after_request
    def _sin_cache_en_paginas_dinamicas(response):
        # El calendario, "mis turnos", etc. cambian todo el tiempo
        # (reservas, cancelaciones de otras/os alumnas/os). Sin este
        # header, el botón "atrás" del navegador (o el caché normal de
        # una página HTML) puede mostrar una versión vieja guardada en
        # vez de pedirle al servidor los datos actuales - se ve como
        # "no se actualiza en tiempo real" aunque el dato en la base
        # ya esté bien. Los archivos estáticos (CSS/JS/imágenes) sí
        # queremos que se cacheen, así que los dejamos afuera.
        from flask import request
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

    def _renderizar_landing():
        from urllib.parse import quote
        from flask import render_template, current_app, url_for

        mensaje_whatsapp = quote("¡Hola! Quiero consultar por las clases de pilates.")
        whatsapp_numero = current_app.config["WHATSAPP_NUMERO"]
        whatsapp_url = f"https://wa.me/{whatsapp_numero}?text={mensaje_whatsapp}"

        direccion = current_app.config["DIRECCION_ESTUDIO"]
        consulta_mapa = quote(f"Benincasa Pilates, {direccion}")
        # Embed sin API key (el "output=embed" clásico de Google Maps,
        # gratis y sin necesidad de una cuenta de Google Cloud) para el
        # iframe, y un link normal de búsqueda para "Cómo llegar" /
        # "Ver en Google Maps".
        mapa_embed_url = f"https://www.google.com/maps?q={consulta_mapa}&output=embed"
        mapa_url = f"https://www.google.com/maps/search/?api=1&query={consulta_mapa}"

        return render_template(
            "landing.html",
            whatsapp_url=whatsapp_url,
            whatsapp_numero=whatsapp_numero,
            instagram_url=current_app.config["INSTAGRAM_URL"],
            direccion=direccion,
            mapa_embed_url=mapa_embed_url,
            mapa_url=mapa_url,
            # _external=True arma la URL completa (con dominio) en vez de
            # una ruta relativa - las etiquetas SEO (canonical, Open
            # Graph, JSON-LD) tienen que llevar la URL completa. Al
            # calcularla con url_for en vez de escribirla a mano, se
            # arma sola con el dominio real donde esté corriendo la app
            # en cada momento (localhost en desarrollo, el dominio real
            # una vez publicada), sin tener que hardcodear ninguno.
            canonical_url=url_for("index", _external=True),
            og_image_url=url_for("static", filename="img/estudio-interior.jpg", _external=True),
        )

    # Ruta raíz: siempre muestra la landing pública, sin excepción -
    # así es como quien entra al sitio (link de Instagram, WhatsApp,
    # buscador, etc.) siempre cae primero en la página de presentación
    # del estudio. La única excepción es alguien que YA tiene una
    # sesión iniciada: a esa persona la mandamos directo a su panel,
    # no tendría sentido mostrarle la landing de nuevo cada vez que
    # entra a la app estando logueada.
    @app.route("/")
    def index():
        from flask import redirect, url_for
        from flask_login import current_user

        if current_user.is_authenticated:
            return redirect(url_for("auth.redirigir_segun_rol"))
        return _renderizar_landing()

    # robots.txt y sitemap.xml: le dicen a Google qué puede rastrear e
    # indexar (la landing) y qué NO (todo lo que requiere login - no
    # tiene sentido para un buscador, y así tampoco aparece por error
    # en resultados de búsqueda). Se arman con url_for para que las
    # URLs sean siempre las reales, sin hardcodear un dominio.
    @app.route("/robots.txt")
    def robots_txt():
        from flask import Response, url_for
        contenido = (
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /admin/\n"
            "Disallow: /alumno/\n"
            "Disallow: /login\n"
            "Disallow: /cambiar-password\n"
            f"\nSitemap: {url_for('sitemap_xml', _external=True)}\n"
        )
        return Response(contenido, mimetype="text/plain")

    @app.route("/sitemap.xml")
    def sitemap_xml():
        from flask import Response, url_for
        contenido = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            "  <url>\n"
            f"    <loc>{url_for('index', _external=True)}</loc>\n"
            "    <changefreq>monthly</changefreq>\n"
            "    <priority>1.0</priority>\n"
            "  </url>\n"
            "</urlset>\n"
        )
        return Response(contenido, mimetype="application/xml")

    return app
