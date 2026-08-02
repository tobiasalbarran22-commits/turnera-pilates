"""
Un "Blueprint" en Flask es una forma de organizar la app en módulos
independientes (auth, admin, alumno) en vez de tener todas las rutas
mezcladas en un solo archivo gigante. Cada blueprint tiene sus propias
rutas y se "registra" en la app principal (ver app/__init__.py).
"""

from flask import Blueprint

bp = Blueprint("auth", __name__, template_folder="../templates/auth")

from app.auth import routes  # noqa: E402,F401  (import al final para evitar import circular)
