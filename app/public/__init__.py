from flask import Blueprint

# Sin url_prefix: estas rutas viven en la raíz del sitio (/, /nosotros,
# /contacto, etc. el día que se agreguen) - son las páginas públicas,
# sin login, pensadas para que las indexe Google.
bp = Blueprint("public", __name__, template_folder="../templates/public")

from app.public import routes  # noqa: E402,F401
