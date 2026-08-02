"""
Dos formularios:
- UsuarioForm: se usa tanto para CREAR como para EDITAR un usuario
  (reutilizamos el mismo formulario para no duplicar código).
- La contraseña es obligatoria al crear, pero OPCIONAL al editar
  (si el admin la deja vacía, no se cambia). Esto lo resolvemos
  a mano en la ruta, no en el formulario, para no complicar la
  validación de WTForms.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, IntegerField, SubmitField
from wtforms.fields import TimeField
from wtforms.validators import DataRequired, InputRequired, Email, Optional, NumberRange, ValidationError

from app.models import Usuario


# Los usamos tanto en el formulario como en la plantilla, para no
# repetir la lista de días en dos lugares distintos.
DIAS_SEMANA = [
    (0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"),
    (4, "Viernes"), (5, "Sábado"), (6, "Domingo"),
]


class UsuarioForm(FlaskForm):
    nombre = StringField("Nombre", validators=[DataRequired()])
    apellido = StringField("Apellido", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email(message="Ingresá un email válido")])

    # Optional() acá porque en la edición puede quedar vacía
    password = PasswordField("Contraseña", validators=[Optional()])

    rol = SelectField("Rol", choices=[("alumno", "Alumno"), ("admin", "Administrador")], validators=[DataRequired()])

    # "libre": reserva la clase que quiera con su saldo mensual.
    # "fijo": el admin le asigna día(s)/horario(s) fijos aparte (ver
    # admin.usuario_horarios_fijos) y queda reservada/o automáticamente.
    modalidad = SelectField(
        "Modalidad",
        choices=[("libre", "Clases libres (usa saldo mensual)"), ("fijo", "Día y horario fijo")],
        default="libre",
        validators=[DataRequired()],
    )

    # choices se completa dinámicamente en la ruta (depende de los
    # planes que existan en la base de datos en ese momento)
    plan_id = SelectField("Plan", coerce=int, validators=[Optional()])

    clases_disponibles = IntegerField(
        "Clases disponibles este mes",
        validators=[Optional(), NumberRange(min=0, message="No puede ser negativo")],
        default=0,
    )

    submit = SubmitField("Guardar")

    def __init__(self, usuario_actual=None, *args, **kwargs):
        """
        usuario_actual: si estamos EDITANDO, acá recibimos el usuario
        que se está editando, para poder excluirlo a sí mismo de la
        validación de "email duplicado" (si no, el form rechazaría
        guardar el usuario porque "ya existe alguien con ese email"...
        ¡siendo él mismo!).
        """
        super().__init__(*args, **kwargs)
        self.usuario_actual = usuario_actual

    def validate_email(self, field):
        # Validador personalizado: chequea que el email no esté ya
        # usado por OTRO usuario.
        usuario_existente = Usuario.query.filter_by(email=field.data.lower().strip()).first()
        if usuario_existente and (self.usuario_actual is None or usuario_existente.id != self.usuario_actual.id):
            raise ValidationError("Ya existe un usuario con ese email.")


class HorarioForm(FlaskForm):
    """
    Formulario para agregar un horario a la grilla semanal.
    dia_semana usa coerce=int porque los SelectField de WTForms
    devuelven strings por defecto, y nosotros lo queremos como número
    (0-6) para que coincida con date.weekday().
    """
    # OJO: usamos InputRequired en vez de DataRequired. DataRequired
    # chequea si el VALOR ya convertido (coerce=int) es "verdadero" en
    # Python - y 0 (Lunes) es falsy, así que DataRequired lo rechazaría
    # como si estuviera vacío. InputRequired en cambio chequea que se
    # haya mandado ALGO en el request, sin importar si ese valor es 0.
    dia_semana = SelectField("Día", choices=DIAS_SEMANA, coerce=int, validators=[InputRequired()])
    hora = TimeField("Hora", validators=[DataRequired()], format="%H:%M")
    submit = SubmitField("Guardar")
