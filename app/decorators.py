"""
@login_required (de Flask-Login) solo verifica que el usuario esté
logueado, pero NO distingue roles. Con este decorador propio,
admin_required, nos aseguramos de que además sea administrador.

Esto es importante por seguridad: aunque en el frontend "ocultemos"
los botones de admin a un alumno, si no protegemos también la RUTA
en el backend, un alumno mal intencionado podría escribir la URL de
admin directamente en el navegador y acceder igual. La validación
real de permisos SIEMPRE tiene que estar en el servidor.
"""

from functools import wraps
from flask import abort
from flask_login import current_user


def admin_required(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.es_admin:
            abort(403)  # "Prohibido" - el usuario no tiene permiso para ver esto
        return f(*args, **kwargs)
    return decorador
