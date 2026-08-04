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
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Horario, Clase, InscripcionFija, Reserva, Usuario
from app.utils import ahora_estudio, hoy_estudio


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
    hoy = hoy_estudio()
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
    ahora = ahora_estudio()
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

    Cada intento de reserva va envuelto en su propio SAVEPOINT
    (db.session.begin_nested()). Esta función corre dentro de un lote
    más grande (ver _reservar_fijos_del_mes, que reserva a TODOS los
    alumnos fijos de TODAS las clases del mes en una sola transacción
    final). Si un alumno puntual choca contra el índice único parcial
    o el trigger de cupo de app/db_constraints.py - por ejemplo,
    alguien reservó ese mismo lugar a mano justo en este instante -,
    sin el SAVEPOINT ese error tiraría abajo el commit de TODO el lote
    (perdiendo también las reservas de los demás alumnos que sí
    estaban bien). Con el SAVEPOINT, solo se deshace ese intento
    puntual (incluido el crédito que ya le había descontado
    consumir_clase, para que no pierda saldo por una reserva que nunca
    se concretó) y se sigue con el resto de la lista.
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
            with db.session.begin_nested():
                es_recuperacion = usuario.consumir_clase()
                db.session.add(Reserva(
                    usuario_id=usuario.id,
                    clase_id=clase.id,
                    estado="reservada",
                    es_recuperacion=es_recuperacion,
                ))
        except ValueError:
            continue
        except IntegrityError:
            continue


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

    hoy = hoy_estudio()
    ahora = ahora_estudio()
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
        # Cada intento va en su propio SAVEPOINT: si choca contra el
        # índice único parcial o el trigger de cupo de
        # app/db_constraints.py (alguien reservó este mismo lugar a
        # mano justo ahora), se deshace solo ESE intento -y el crédito
        # que ya le había descontado consumir_clase()- en vez de tirar
        # abajo el commit final con TODAS las clases de este alumno.
        try:
            with db.session.begin_nested():
                es_recuperacion = usuario.consumir_clase()
                db.session.add(Reserva(
                    usuario_id=usuario.id, clase_id=clase.id,
                    estado="reservada", es_recuperacion=es_recuperacion,
                ))
        except ValueError:
            saltadas_por_saldo += 1
            continue
        except IntegrityError:
            saltadas_por_saldo += 1
            continue
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
    hoy = hoy_estudio()
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
        reserva.fecha_cancelacion = ahora_estudio()

    db.session.delete(inscripcion)
    db.session.commit()


def _cancelar_reserva_y_acreditar(reserva, ahora):
    """
    Cancela UNA Reserva de forma atómica (con UPDATE ... WHERE
    estado='reservada', igual que en alumno.services.cancelar_reserva
    y Usuario.consumir_clase - ver esas dos para la explicación
    completa) y le acredita al alumno una clase para recuperar. Se usa
    desde desactivar_horario y cancelar_clase, que son acciones del
    ADMIN que pueden coincidir en el tiempo con que el propio alumno
    cancele esa misma reserva por su cuenta: sin el WHERE, ambas
    "cancelaciones" pasarían y el alumno terminaría acreditado dos
    veces por una sola clase perdida.

    Devuelve True si esta llamada fue la que efectivamente la canceló,
    False si ya estaba cancelada de antes (en cuyo caso no se acredita
    de nuevo).
    """
    tabla_reserva = Reserva.__table__
    resultado = db.session.execute(
        update(tabla_reserva)
        .where(tabla_reserva.c.id == reserva.id, tabla_reserva.c.estado == "reservada")
        .values(estado="cancelada", fecha_cancelacion=ahora, cancelacion_a_tiempo=True)
    )
    if not resultado.rowcount:
        return False

    db.session.execute(
        update(Usuario.__table__)
        .where(Usuario.__table__.c.id == reserva.usuario_id)
        .values(clases_recuperables=Usuario.__table__.c.clases_recuperables + 1)
    )
    db.session.expire(reserva, ["estado", "fecha_cancelacion", "cancelacion_a_tiempo"])
    return True


def cancelar_clase(clase):
    """
    Cancela una Clase puntual completa (ej: feriado, el estudio no
    abre ese día). A diferencia de quitar_horario_fijo -que solo deja
    de reservar automáticamente hacia ADELANTE a los alumnos fijos de
    un Horario, sin tocar clases ya generadas- esto cancela UNA fecha
    concreta que ya existe en el calendario.

    Cancela todas las Reservas activas de esa Clase y le acredita a
    cada alumno afectado una clase para recuperar dentro de este mes,
    para que pueda elegir otro día/horario. A propósito NO respeta acá
    el tope de MAX_CLASES_RECUPERABLES que sí aplica cuando un ALUMNO
    cancela tarde (ver cancelar_reserva en app/alumno/services.py):
    ese tope existe para desalentar cancelaciones tardías del propio
    alumno, no para limitar cuánto se le compensa cuando es el
    ESTUDIO el que cancela. El alumno no debería perder valor por una
    decisión que no tomó él.

    Devuelve la lista de Reservas que se cancelaron (para que la ruta
    pueda avisar por mail a cada alumno y borrar el evento de Google
    Calendar si tenían uno, después del commit). Si la Clase ya estaba
    cancelada, no hace nada y devuelve una lista vacía.
    """
    if clase.cancelada:
        return []

    ahora = ahora_estudio()
    reservas_activas = Reserva.query.filter_by(clase_id=clase.id, estado="reservada").all()

    reservas_canceladas = []
    for reserva in reservas_activas:
        if _cancelar_reserva_y_acreditar(reserva, ahora):
            reservas_canceladas.append(reserva)

    clase.cancelada = True
    db.session.commit()
    return reservas_canceladas


def cancelar_clases_del_dia(fecha):
    """
    Cancela TODAS las clases (de cualquier horario) de una fecha
    puntual - pensado para un feriado o un día que el estudio no abre,
    sin tener que cancelar clase por clase ni dar de baja ningún
    Horario semanal entero. Por dentro llama a cancelar_clase() por
    cada Clase del día, así que cada alumno afectado recibe el mismo
    trato (turno cancelado, crédito de recuperación, aviso por mail).

    Devuelve la lista de Reservas que se cancelaron, juntando las de
    todas las clases del día.
    """
    clases_del_dia = Clase.query.filter_by(fecha=fecha, cancelada=False).all()
    reservas_canceladas = []
    for clase in clases_del_dia:
        reservas_canceladas.extend(cancelar_clase(clase))
    return reservas_canceladas


def reactivar_clase(clase):
    """
    Reactiva una Clase que se había cancelado por error (ver
    cancelar_clase): la vuelve a dejar disponible para reservar.

    Para optimizar el saldo de los alumnos al máximo, le recupera a
    cada afectado el crédito de recuperación que se le había
    acreditado por la cancelación - pero SOLO si todavía lo tiene sin
    gastar (con el mismo UPDATE ... WHERE clases_recuperables > 0
    atómico que se usa en el resto del sistema). Si ya lo usó para
    reservar otra clase mientras tanto, no se lo podemos sacar sin
    romper esa otra reserva, así que se lo dejamos - no hay forma de
    "deshacer" un crédito que ya se gastó sin cancelar lo que se
    reservó con él.

    OJO: esto NO vuelve a reservar automáticamente a quienes tenían un
    turno ahí antes de la cancelación - la clase queda abierta para
    que la reserven de nuevo (por su cuenta, o el admin se los puede
    volver a asignar a mano), en vez de asumir que todos siguen
    queriendo/pudiendo ir después de un tiempo indeterminado.

    Solo se intenta recuperar el crédito de Reservas con
    cancelacion_a_tiempo=True: es la marca que deja
    _cancelar_reserva_y_acreditar (usada por cancelar_clase) en toda
    reserva a la que efectivamente le acreditó un crédito. Si un
    alumno había cancelado su propio turno tarde (sin acreditar nada)
    ANTES de que el admin cancelara toda la clase, esa Reserva queda
    con cancelacion_a_tiempo=False y no se toca acá - si la
    incluyéramos, podríamos terminar restándole a ese alumno un
    crédito de recuperación real que tenía guardado de otra cancelación
    sin relación con esta clase.

    Devuelve cuántos créditos se pudieron recuperar efectivamente.
    """
    if not clase.cancelada:
        return 0

    reservas_canceladas = Reserva.query.filter_by(
        clase_id=clase.id, estado="cancelada", cancelacion_a_tiempo=True
    ).all()
    tabla_usuario = Usuario.__table__
    recuperados = 0
    for reserva in reservas_canceladas:
        resultado = db.session.execute(
            update(tabla_usuario)
            .where(tabla_usuario.c.id == reserva.usuario_id, tabla_usuario.c.clases_recuperables > 0)
            .values(clases_recuperables=tabla_usuario.c.clases_recuperables - 1)
        )
        if resultado.rowcount:
            recuperados += 1

    clase.cancelada = False
    db.session.commit()
    return recuperados
