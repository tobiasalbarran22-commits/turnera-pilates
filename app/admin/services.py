"""
Acá separamos la LÓGICA DE NEGOCIO de las rutas (que solo deberían
encargarse de recibir el request y devolver una respuesta). Esto hace
que la lógica sea más fácil de testear y reutilizar - por ejemplo,
el panel del alumno también va a necesitar "asegurarse de que las
clases del mes ya estén generadas" antes de mostrar el calendario.
"""

from calendar import monthrange
from datetime import date, datetime, timedelta

from flask import current_app

from app.extensions import db
from app.models import Horario, Clase, InscripcionFija, Reserva


def generar_clases_para_mes(anio, mes):
    """
    Recorre día por día el mes indicado. Por cada día, revisa qué
    Horarios activos "caen" en ese día de la semana, y crea una Clase
    concreta para esa fecha exacta - si todavía no existe (así se
    puede llamar esta función más de una vez sin generar duplicados,
    por ejemplo si un alumno entra al calendario y el admin también
    generó las clases a mano).

    Devuelve la cantidad de clases NUEVAS que se crearon.
    """
    horarios_activos = Horario.query.filter_by(activo=True).all()
    if not horarios_activos:
        return 0

    primer_dia = date(anio, mes, 1)
    ultimo_dia_num = monthrange(anio, mes)[1]  # cantidad de días que tiene ese mes
    ultimo_dia = date(anio, mes, ultimo_dia_num)

    cupo_default = current_app.config["CUPO_MAXIMO_POR_CLASE"]

    # Para no hacer una consulta a la base de datos por cada combinación
    # día+horario (sería lento), traemos de una sola vez todas las
    # clases que ya existen en ese rango de fechas y las guardamos en
    # un set para chequear pertenencia en memoria.
    clases_existentes = Clase.query.filter(
        Clase.fecha >= primer_dia, Clase.fecha <= ultimo_dia
    ).all()
    claves_existentes = {(c.fecha, c.hora_inicio, c.horario_id) for c in clases_existentes}

    creadas = 0
    dia_actual = primer_dia
    while dia_actual <= ultimo_dia:
        for horario in horarios_activos:
            if horario.dia_semana == dia_actual.weekday():
                clave = (dia_actual, horario.hora, horario.id)
                if clave not in claves_existentes:
                    nueva = Clase(
                        fecha=dia_actual,
                        hora_inicio=horario.hora,
                        cupo_maximo=cupo_default,
                        horario_id=horario.id,
                    )
                    db.session.add(nueva)
                    creadas += 1
        dia_actual += timedelta(days=1)

    db.session.commit()

    # Los alumnos "fijos" se reservan automáticamente SOLO para el mes
    # ACTUAL, nunca para un mes futuro que se haya generado por
    # adelantado (el admin puede generar varios meses de una vez desde
    # /horarios). clases_disponibles es un saldo MENSUAL: si
    # reserváramos ya mismo las clases de un mes que todavía no
    # empezó, gastaríamos de una sola vez el saldo de ESTE mes en
    # turnos de otro mes. Cuando ese mes futuro efectivamente llegue,
    # esta misma función se vuelve a llamar (automáticamente, cuando
    # un alumno entra a su calendario) y ahí sí se reservan los fijos
    # - sin importar si esas clases ya estaban generadas de antes o
    # se acaban de crear recién ahora (ver _reservar_fijos_del_mes).
    hoy = date.today()
    if anio == hoy.year and mes == hoy.month:
        _reservar_fijos_del_mes(primer_dia, ultimo_dia, horarios_activos)

    return creadas


def _reservar_fijos_del_mes(primer_dia, ultimo_dia, horarios_activos):
    """
    Reserva a los alumnos "fijos" (InscripcionFija) en las clases del
    mes [primer_dia, ultimo_dia] que les correspondan según su horario,
    sin importar si esas clases se acaban de crear ahora o ya existían
    de antes (ej: generadas por adelantado el mes pasado). Se procesan
    en orden cronológico para que, si el saldo no alcanza para todas,
    se respeten primero las clases más próximas del mes. Es idempotente
    (no vuelve a reservar ni a descontar saldo de una clase ya
    reservada), así que se puede llamar una vez por cada visita al
    calendario sin efectos raros. Tampoco reserva clases cuyo horario
    ya pasó (ej: si hoy es 15 y el horario nunca se había generado
    antes, no tiene sentido reservar automáticamente los días 1 al 14).
    """
    ahora = datetime.now()
    horarios_por_id = {h.id: h for h in horarios_activos}
    clases_del_mes = (
        Clase.query.filter(
            Clase.fecha >= primer_dia,
            Clase.fecha <= ultimo_dia,
            Clase.horario_id.in_(horarios_por_id.keys()),
            Clase.cancelada.is_(False),
        )
        .order_by(Clase.fecha, Clase.hora_inicio)
        .all()
    )
    for clase in clases_del_mes:
        if datetime.combine(clase.fecha, clase.hora_inicio) <= ahora:
            continue
        _reservar_fijos_de_horario(clase, horarios_por_id[clase.horario_id])
    db.session.commit()


def _reservar_fijos_de_horario(clase, horario):
    """
    Reserva automáticamente en `clase` a todos los alumnos de modalidad
    "fijo" que el admin haya asignado a ese Horario (InscripcionFija).
    Así no dependen de entrar a elegir el día cada mes: ya están
    "designadas/os" a ese día y horario.

    Igual que si el alumno reservara la clase por su cuenta, cada
    reserva automática descuenta un crédito real (clases_disponibles
    primero, clases_recuperables después - ver Usuario.consumir_clase).
    Esto es necesario porque un Horario es una plantilla SEMANAL, pero
    el plan del alumno es MENSUAL: según el mes, un mismo día de la
    semana puede caer 4 o 5 veces, así que no alcanza con "reservarlo
    siempre" - hay que respetar el tope mensual igual que a un alumno
    "libre". Si ya no le queda saldo de ningún tipo, se lo salta: ese
    lugar queda libre para otro alumno en vez de dárselo igual.
    """
    inscripciones = InscripcionFija.query.filter_by(horario_id=horario.id, activo=True).all()
    for inscripcion in inscripciones:
        usuario = inscripcion.usuario
        if not usuario.activo:
            continue
        # Idempotencia: esta función se puede volver a llamar sobre la
        # misma Clase (ver _reservar_fijos_del_mes), así que si el
        # alumno ya está reservado acá no hay que tocar nada de nuevo.
        ya_reservada = Reserva.query.filter_by(
            usuario_id=usuario.id, clase_id=clase.id, estado="reservada"
        ).first()
        if ya_reservada:
            continue
        if clase.cupos_ocupados >= clase.cupo_maximo:
            break
        try:
            es_recuperacion = usuario.consumir_clase()
        except ValueError:
            continue
        db.session.add(Reserva(
            usuario_id=usuario.id,
            clase_id=clase.id,
            estado="reservada",
            es_recuperacion=es_recuperacion,
        ))


def dias_fijos_permitidos(usuario):
    """
    Cantidad máxima de DÍAS DISTINTOS por semana que un alumno puede
    tener como horario fijo, según cuántas clases por mes tiene su
    plan (asumiendo ~4 semanas por mes: 4 clases/mes -> 1 día/semana,
    8 -> 2, 12 -> 3, 16 -> 4). Evita que el admin cargue, por error,
    más días fijos de los que el plan alcanza a cubrir - algo que
    hoy fallaba en silencio (ver asignar_horario_fijo más abajo).

    Devuelve None si el alumno no tiene plan asignado (no restringimos:
    es una situación rara que el admin debería resolver aparte).
    """
    if not usuario.plan:
        return None
    return max(usuario.plan.clases_por_mes // 4, 1)


def asignar_horario_fijo(usuario, horario):
    """
    Da de alta (o reactiva) una InscripcionFija: el alumno queda
    "designado" a ese día y horario fijo. De paso, lo reserva ya mismo
    en las Clases de ese Horario que ya estén generadas, tengan cupo,
    y caigan dentro de lo que queda del MES ACTUAL - no tocamos meses
    futuros aunque ya tengan clases generadas (ver más abajo por qué).
    Igual que en _reservar_fijos_de_horario, cada una de estas reservas
    descuenta un crédito real del alumno - si se queda sin saldo a
    mitad de camino, deja de reservarlo en las que falten.

    Por qué el tope de mes actual: clases_disponibles es un saldo
    MENSUAL. Si el admin ya generó clases de varios meses por
    adelantado y esta función reservara todas las que encuentre sin
    límite de fecha, gastaría de una sola vez el saldo de ESTE mes en
    clases de meses que ni siquiera empezaron - dejando al alumno con
    reservas "fantasma" en el futuro y sin saldo para lo que resta del
    mes actual. Los meses siguientes se reservan solos, con su propio
    saldo, cuando llegan (ver _reservar_fijos_del_mes, llamada desde
    generar_clases_para_mes).

    Devuelve (inscripcion, reservadas, saltadas_por_saldo) para que la
    ruta pueda avisarle al admin si algo no se pudo reservar en vez de
    fallar en silencio: antes, si el alumno tenía 0 de saldo en el
    momento de la asignación, quedaba "asignado/a" en la grilla pero
    sin ningún turno real, y el admin no se enteraba hasta que el
    alumno se quejaba de no ver nada en "Mis turnos".

    Levanta ValueError si asignar este horario haría que el alumno
    supere el máximo de días fijos por semana que permite su plan
    (ver dias_fijos_permitidos).
    """
    inscripcion = InscripcionFija.query.filter_by(usuario_id=usuario.id, horario_id=horario.id).first()
    ya_activa = inscripcion is not None and inscripcion.activo

    if not ya_activa:
        dias_actuales = {
            i.horario.dia_semana for i in usuario.inscripciones_fijas
            if i.activo and i.horario_id != horario.id
        }
        limite = dias_fijos_permitidos(usuario)
        if limite is not None and horario.dia_semana not in dias_actuales and len(dias_actuales) >= limite:
            raise ValueError(
                f"{usuario.nombre_completo} ya tiene {limite} día(s) fijo(s) por semana asignado(s), "
                f"el máximo que permite su plan \"{usuario.plan.nombre}\". Quitale un horario fijo antes "
                "de agregar uno nuevo, o asignale un plan con más clases por mes."
            )

    if inscripcion:
        inscripcion.activo = True
    else:
        inscripcion = InscripcionFija(usuario_id=usuario.id, horario_id=horario.id)
        db.session.add(inscripcion)

    hoy = date.today()
    ahora = datetime.now()
    fin_de_mes_actual = date(hoy.year, hoy.month, monthrange(hoy.year, hoy.month)[1])
    clases_del_mes = Clase.query.filter(
        Clase.horario_id == horario.id,
        Clase.fecha >= hoy,
        Clase.fecha <= fin_de_mes_actual,
        Clase.cancelada.is_(False),
    ).all()
    reservadas = 0
    saltadas_por_saldo = 0
    for clase in clases_del_mes:
        if datetime.combine(clase.fecha, clase.hora_inicio) <= ahora:
            continue
        ya_reservada = Reserva.query.filter_by(
            usuario_id=usuario.id, clase_id=clase.id, estado="reservada"
        ).first()
        if ya_reservada or not clase.tiene_cupo:
            continue
        try:
            es_recuperacion = usuario.consumir_clase()
        except ValueError:
            saltadas_por_saldo += 1
            continue
        db.session.add(Reserva(usuario_id=usuario.id, clase_id=clase.id, estado="reservada", es_recuperacion=es_recuperacion))
        reservadas += 1

    db.session.commit()
    return inscripcion, reservadas, saltadas_por_saldo


def quitar_horario_fijo(inscripcion):
    """
    Da de baja una InscripcionFija. Las Reservas futuras que venían de
    esa asignación fija se cancelan (sin acreditar clase de
    recuperación: fue una decisión del admin, no una cancelación del
    alumno con anticipación).
    """
    hoy = date.today()
    reservas_futuras = (
        Reserva.query.join(Clase)
        .filter(
            Reserva.usuario_id == inscripcion.usuario_id,
            Clase.horario_id == inscripcion.horario_id,
            Clase.fecha >= hoy,
            Reserva.estado == "reservada",
        )
        .all()
    )
    for reserva in reservas_futuras:
        reserva.estado = "cancelada"
        reserva.fecha_cancelacion = datetime.utcnow()

    db.session.delete(inscripcion)
    db.session.commit()
