"""
Acá inicializamos las "extensiones" de Flask SIN todavía conectarlas a
una aplicación concreta. Esto es un patrón muy común en Flask (se llama
"application factory pattern") que sirve para evitar imports circulares:
- models.py necesita `db`
- app/__init__.py necesita `models`
- si todo estuviera en un solo archivo, se pisarían los imports

Entonces: acá declaramos los objetos "vacíos", y en app/__init__.py
los conectamos a la app real con `.init_app(app)`.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf import CSRFProtect

db = SQLAlchemy()          # ORM: nos permite trabajar con la base de datos usando clases de Python en vez de SQL
login_manager = LoginManager()   # maneja las sesiones de usuario logueado
bcrypt = Bcrypt()          # para hashear (encriptar) contraseñas, nunca se guardan en texto plano

# CSRFProtect a nivel global: sin esto, un FlaskForm (como el login)
# valida su propio token CSRF, pero los formularios HTML simples
# (como los botones de "dar de baja" o "eliminar") quedarían
# DESPROTEGIDOS. Con esto, TODO POST/PUT/DELETE de la app exige un
# token CSRF válido, sin excepción.
csrf = CSRFProtect()
