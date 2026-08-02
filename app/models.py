"""
MODELOS DE LA BASE DE DATOS
===========================
Cada clase de acá abajo representa una TABLA en la base de datos.
Cada atributo de la clase (db.Column(...)) representa una COLUMNA.
SQLAlchemy se encarga de traducir esto a SQL por nosotros.

Tablas:
- Usuario: administradores y alumnos (usamos el mismo modelo con un
  campo "rol" para diferenciarlos, así no duplicamos lógica de login).
- Plan: los planes que puede tener un alumno (ej: "4 clases por mes").
- Horario: la "grilla" de días/horarios que el admin habilita
  (ej: Lunes 9:00, Lunes 10:00, Miércoles 18:00, etc.) Esto es la
  PLANTILLA semanal, no un día puntual del calendario.
- Clase: una clase CONCRETA en una fecha puntual (ej: "Lunes 11 de
  agosto, 9:00hs"). Se genera a partir de un Horario habilitado.
- Reserva: el "turno" que un alumno saca para una Clase puntual.
- InscripcionFija: la asignación de un alumno "de día y horario fijo"
  a un Horario semanal (lo carga el admin). A partir de acá, el
  alumno queda reservado automáticamente cada vez que se generan las
  clases de ese horario.
- AvisoCupo: la "campanita" - un alumno pide que le avisen por mail
  si se libera un lugar en una Clase que estaba llena.
"""

from datetime import datetime
from flask_login import UserMixin
from app.extensions import db


class Usuario(UserMixin, db.Model):
    """
    UserMixin le agrega a esta clase los métodos que Flask-Login
    necesita para manejar la sesión (is_authenticated, is_active,
    get_id, etc.) sin que tengamos que escribirlos nosotros.
    """
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False)
    apellido = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)

    # "admin" o "alumno". Con esto decidimos qué puede ver/hacer cada uno.
    rol = db.Column(db.String(20), nullable=False, default="alumno")

    # Un alumno tiene un plan asignado (ej: 4 clases/mes). Un admin no.
    plan_id = db.Column(db.Integer, db.ForeignKey("planes.id"), nullable=True)
    plan = db.relationship("Plan", backref="alumnos")

    # "fijo": el admin le asignó día(s) y horario(s) fijos (ver
    # InscripcionFija) y queda reservado automáticamente cada mes,
    # PERO cada una de esas reservas automáticas sigue descontando
    # del mismo saldo mensual que un alumno "libre" (ver
    # admin/services.py: _reservar_fijos_de_horario). Un Horario es
    # una plantilla semanal y un mismo día puede caer 4 o 5 veces en
    # el mes, así que sin este descuento un alumno fijo terminaría
    # yendo más veces de las que su plan permite.
    # "libre": no tiene clases fijas, reserva la que quiera dentro
    # del cupo mensual que le carga el admin (clases_disponibles).
    modalidad = db.Column(db.String(20), nullable=False, default="libre")

    # Saldo de clases del plan que le quedan disponibles ESTE mes.
    # Se resetea todos los meses según el plan (lo hace una función
    # aparte, no automáticamente, para que el admin tenga control).
    # Un alumno "fijo" también consume de acá con cada reserva
    # automática de su horario fijo (ver modalidad, arriba).
    clases_disponibles = db.Column(db.Integer, default=0)

    # Saldo de clases "de recuperación" acumuladas por cancelar con
    # anticipación. Tope definido en config.py (MAX_CLASES_RECUPERABLES).
    clases_recuperables = db.Column(db.Integer, default=0)

    activo = db.Column(db.Boolean, default=True)  # para "desactivar" en vez de borrar usuarios
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Una vez que un alumno reserva turnos, acá quedan todas sus reservas
    reservas = db.relationship("Reserva", backref="usuario", lazy="dynamic")

    def set_password(self, password_plano):
        """Convierte la contraseña en texto plano a un hash seguro (bcrypt)."""
        from app.extensions import bcrypt
        self.password_hash = bcrypt.generate_password_hash(password_plano).decode("utf-8")

    def check_password(self, password_plano):
        """Compara una contraseña ingresada contra el hash guardado."""
        from app.extensions import bcrypt
        return bcrypt.check_password_hash(self.password_hash, password_plano)

    def consumir_clase(self):
        """
        Descuenta un crédito del saldo del alumno: primero el saldo
        normal del plan (clases_disponibles), y si ya no queda, el de
        recuperación (clases_recuperables). Se usa cuando el alumno
        reserva una clase por su cuenta (ver reservar_clase).

        Devuelve True si se usó un crédito de recuperación, False si
        se usó el saldo normal. Lanza ValueError si no queda saldo de
        ningún tipo.
        """
        if self.clases_disponibles > 0:
            self.clases_disponibles -= 1
            return False
        elif self.clases_recuperables > 0:
            self.clases_recuperables -= 1
            return True
        raise ValueError("No te quedan clases disponibles ni clases para recuperar este mes.")

    @property
    def es_admin(self):
        return self.rol == "admin"

    @property
    def es_fijo(self):
        return self.modalidad == "fijo"

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    def __repr__(self):
        return f"<Usuario {self.email} ({self.rol})>"


class Plan(db.Model):
    """
    Ej: "Plan 2 clases semanales", "Plan libre", etc.
    clases_por_mes define cuántas clases se le cargan al alumno
    cada vez que se resetea el mes.
    """
    __tablename__ = "planes"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False)
    clases_por_mes = db.Column(db.Integer, nullable=False)
    activo = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<Plan {self.nombre}>"


class Horario(db.Model):
    """
    Esta es la PLANTILLA semanal que arma el administrador.
    Por ejemplo: "Todos los Lunes a las 9:00hs hay clase".
    A partir de esta plantilla es que se generan las Clases concretas
    en el calendario (día por día).

    dia_semana: 0=Lunes, 1=Martes, ..., 6=Domingo (estándar de Python,
    así coincide directo con date.weekday()).
    """
    __tablename__ = "horarios"

    id = db.Column(db.Integer, primary_key=True)
    dia_semana = db.Column(db.Integer, nullable=False)  # 0-6
    hora = db.Column(db.Time, nullable=False)
    activo = db.Column(db.Boolean, default=True)  # el admin puede desactivarlo sin borrar el historial

    def __repr__(self):
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        return f"<Horario {dias[self.dia_semana]} {self.hora}>"


class Clase(db.Model):
    """
    Una clase CONCRETA: fecha puntual + horario puntual.
    Ejemplo: Clase(fecha=11/08/2026, hora_inicio=09:00).

    Se genera automáticamente a partir de los Horarios activos (ver
    app/admin/services.py más adelante), pero queda como registro
    propio para poder, por ejemplo, cancelar una clase puntual sin
    afectar el resto del horario semanal.
    """
    __tablename__ = "clases"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    hora_inicio = db.Column(db.Time, nullable=False)
    cupo_maximo = db.Column(db.Integer, nullable=False, default=5)

    # De qué plantilla semanal salió esta clase (puede ser null si en
    # el futuro se crea una clase "suelta" manualmente).
    horario_id = db.Column(db.Integer, db.ForeignKey("horarios.id"), nullable=True)
    horario = db.relationship("Horario", backref="clases_generadas")

    cancelada = db.Column(db.Boolean, default=False)  # si el admin cancela la clase entera (ej: feriado)

    reservas = db.relationship("Reserva", backref="clase", lazy="dynamic")

    @property
    def cupos_ocupados(self):
        # Contamos solo las reservas activas (no las canceladas)
        return self.reservas.filter_by(estado="reservada").count()

    @property
    def cupos_disponibles(self):
        return self.cupo_maximo - self.cupos_ocupados

    @property
    def tiene_cupo(self):
        return self.cupos_disponibles > 0 and not self.cancelada

    def __repr__(self):
        return f"<Clase {self.fecha} {self.hora_inicio}>"


class Reserva(db.Model):
    """
    El "turno" en sí: un alumno reservó un lugar en una Clase puntual.

    estado puede ser:
      - "reservada": el turno está activo, el alumno va a ir.
      - "cancelada": el alumno canceló (a tiempo o no, ver es_tardia).
      - "asistio": el admin marcó que el alumno vino.
      - "ausente": el admin marcó que el alumno faltó sin avisar.

    es_recuperacion: True si este turno se pagó con un crédito de
    recuperación en vez de con el saldo normal del plan.
    """
    __tablename__ = "reservas"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    clase_id = db.Column(db.Integer, db.ForeignKey("clases.id"), nullable=False)

    estado = db.Column(db.String(20), nullable=False, default="reservada")
    es_recuperacion = db.Column(db.Boolean, default=False)

    fecha_reserva = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_cancelacion = db.Column(db.DateTime, nullable=True)

    # Si se canceló con >= HORAS_MINIMAS_PARA_CANCELAR de anticipación,
    # esto queda en True y es lo que genera el crédito de recuperación.
    cancelacion_a_tiempo = db.Column(db.Boolean, nullable=True)

    # Si esta reserva tiene un evento creado en Google Calendar,
    # guardamos su ID acá. Lo necesitamos para poder BORRAR ese
    # evento puntual el día de mañana si el alumno cancela el turno.
    # Nullable porque puede no haber integración con Google configurada.
    google_event_id = db.Column(db.String(255), nullable=True)

    # Para no mandar el recordatorio "mañana tenés clase" más de una
    # vez por reserva (el script que lo manda corre todos los días).
    recordatorio_enviado = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<Reserva usuario={self.usuario_id} clase={self.clase_id} estado={self.estado}>"


class InscripcionFija(db.Model):
    """
    Asigna a un alumno de modalidad "fijo" a un Horario semanal fijo
    (ej: "Tobi va todos los Lunes a las 10hs"). Esto lo carga el admin
    a mano (ver admin/services.py: asignar_horario_fijo). A partir de
    acá, cada vez que se generan las Clases concretas de ese Horario,
    el alumno queda reservado automáticamente sin tener que entrar a
    elegir el día cada mes (mientras le quede saldo mensual: ver
    Usuario.clases_disponibles).
    """
    __tablename__ = "inscripciones_fijas"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    horario_id = db.Column(db.Integer, db.ForeignKey("horarios.id"), nullable=False)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    usuario = db.relationship("Usuario", backref="inscripciones_fijas")
    horario = db.relationship("Horario", backref="inscripciones_fijas")

    __table_args__ = (db.UniqueConstraint("usuario_id", "horario_id", name="uq_inscripcion_fija"),)

    def __repr__(self):
        return f"<InscripcionFija usuario={self.usuario_id} horario={self.horario_id}>"


class AvisoCupo(db.Model):
    """
    La "campanita": un alumno pide que le avisen por mail si se libera
    un lugar en una Clase que en ese momento está llena. Se crea un
    registro por (usuario, clase). Cuando alguien cancela un turno de
    esa Clase y se libera un lugar, se les manda el mail a todos los
    que estén esperando y se marcan como notificados.
    """
    __tablename__ = "avisos_cupo"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    clase_id = db.Column(db.Integer, db.ForeignKey("clases.id"), nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    notificado = db.Column(db.Boolean, default=False)
    fecha_notificado = db.Column(db.DateTime, nullable=True)

    usuario = db.relationship("Usuario", backref="avisos_cupo")
    clase = db.relationship("Clase", backref="avisos_cupo")

    __table_args__ = (db.UniqueConstraint("usuario_id", "clase_id", name="uq_aviso_cupo"),)

    def __repr__(self):
        return f"<AvisoCupo usuario={self.usuario_id} clase={self.clase_id} notificado={self.notificado}>"
