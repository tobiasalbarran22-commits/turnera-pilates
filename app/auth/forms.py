"""
Usamos Flask-WTF para los formularios porque nos da, gratis:
- Protección CSRF (evita que una página maliciosa mande formularios
  en nombre del usuario sin que se dé cuenta).
- Validación de datos del lado del servidor (nunca hay que confiar
  solo en la validación del navegador).
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(message="Ingresá un email válido")])
    password = PasswordField("Contraseña", validators=[DataRequired()])
    recordarme = BooleanField("Mantenerme conectado")
    submit = SubmitField("Ingresar")


class CambiarPasswordForm(FlaskForm):
    """
    La usa cualquier usuario logueado (alumno o admin) para cambiar
    su PROPIA contraseña, por eso pide la actual: sirve para
    confirmar que es la misma persona la que está frente a la
    pantalla, no alguien que encontró la sesión abierta.
    """
    password_actual = PasswordField("Contraseña actual", validators=[DataRequired()])
    password_nueva = PasswordField(
        "Contraseña nueva",
        validators=[DataRequired(), Length(min=6, message="Tiene que tener al menos 6 caracteres.")],
    )
    password_nueva_confirmar = PasswordField(
        "Confirmar contraseña nueva",
        validators=[DataRequired(), EqualTo("password_nueva", message="Las contraseñas no coinciden.")],
    )
    submit = SubmitField("Actualizar contraseña")
