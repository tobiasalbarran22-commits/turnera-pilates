from flask import Blueprint

bp = Blueprint("alumno", __name__, template_folder="../templates/alumno", url_prefix="/alumno")

from app.alumno import routes  # noqa: E402,F401
