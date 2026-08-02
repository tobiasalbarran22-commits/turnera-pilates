"""
Acá vive la lógica de reservar y cancelar turnos. La separamos de las
rutas por la misma razón que en app/admin/services.py: rutas más
simples, lógica más fácil de testear.

Estas funciones NO hacen db.session.commit() - solo dejan los cambios
"preparados" en la sesión. El commit final lo hace la ruta que las
llama. Así, si algo falla a mitad de camino, no queda nada a medio
guardar.
"""

from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import update

from app.extensions import db
from app.models import Reserva, Clase, AvisoCupo, Usuario
from app.integrations.email import enviar_recordatorio_clase, enviar_aviso_cupo_liberado
from app.utils import ahora_estudio, hoy_estudio


def reservar_clase(usuario, clase):
    """
    Intenta reservar un turno para `usuario` en `clase`.
    Si algo no se puede hacer, levanta ValueError con un mensaje
    entendible para mostrarle directo al alumno.

    Regla de qué saldo se usa primero: el saldo del PLAN normal
    (clases_disponibles) se gasta antes que el saldo de RECUPERACIÓN
    (clases_recuperables). Tiene sentido: las clases de recuperación
    vencen a fin de mes, así que conviene gastarlas al final, no antes
    que las del plan.
    """
    ahora = ahora_estudio()
    inicio_clase = datetime.combine(clase.fecha, clase.hora_inicio)

    if inicio_clase <= ahora:
        raise ValueError("No podés reservar una clase que ya pasó.")

    if clase.cancelada:
        raise ValueError("Esta clase fue cancelada por el estudio.")

    if not clase.tiene_cupo:
        raise ValueError("No quedan cupos disponibles para esta clase.")

    ya_reservada = Reserva.query.filter_by(
        usuario_id=usuario.id, clase_id=clase.id, estado="reservada"
    ).first()
    if ya_reservada:
        raise ValueError("Ya tenés un turno reservado para esta clase.")

    es_recuperacion = usuario.consumir_clase()

    nueva_reserva = Reserva(
        usuario_id=usuario.id,
        clase_id=clase.id,
        estado="reservada",
        es_recuperacion=es_recuperacion,
    )
    db.session.add(nueva_reserva)
    return nueva_reserva


def cancelar_reserva(reserva, usuario):
    """
    Cancela una reserva ya hecha. Acá vive la regla del sistema de
    recuperación: si se cancela con HORAS_MINIMAS_PARA_CANCELAR
    (4hs por defecto) o más de anticipación, se le acredita al
    alumno una clase para recuperar dentro del mismo mes (con un
    tope de MAX_CLASES_RECUPERABLES, 3 por defecto). Si cancela más
    tarde (o directamente no aparece), pierde la clase sin crédito.

    OJO con la implementación: igual que en Usuario.consumir_clase(),
    tanto el paso "reservada" -> "cancelada" como el acreditado de
    clases_recuperables se hacen con un UPDATE ... WHERE atómico, no
    con "leer el valor actual en Python y después guardarlo". Sin
    esto, dos cancelaciones casi simultáneas de la MISMA reserva
    (ej: doble clic, o la pestaña de "Mis turnos" abierta en dos
    lugares) podrían pasar las dos el chequeo de "¿todavía está
    reservada?" antes de que ninguna guarde, y acreditar el crédito de
    recuperación DOS veces por una sola cancelación real. Con el
    UPDATE ... WHERE estado='reservada', la base de datos serializa
    esos dos requests: al segundo que se ejecute, el WHERE ya no
    matchea (el estado ya cambió) y no actualiza nada - ahí es cuando
    avisamos que "ya estaba cancelada" en vez de acreditar de más.
    Lo mismo para clases_recuperables, si el alumno cancela dos
    reservas DISTINTAS al mismo tiempo.
    """
    clase = reserva.clase

    # Combinamos fecha + hora de la clase en un único datetime para
    # poder calcular cuántas horas faltan hasta que empiece.
    inicio_clase = datetime.combine(clase.fecha, clase.hora_inicio)
    horas_de_anticipacion = (inicio_clase - ahora_estudio()).total_seconds() / 3600

    minimo_horas = current_app.config["HORAS_MINIMAS_PARA_CANCELAR"]
    cancelacion_a_tiempo = horas_de_anticipacion >= minimo_horas

    tabla_reserva = Reserva.__table__
    resultado = db.session.execute(
        update(tabla_reserva)
        .where(tabla_reserva.c.id == reserva.id, tabla_reserva.c.estado == "reservada")
        .values(
            estado="cancelada",
            fecha_cancelacion=ahora_estudio(),
            cancelacion_a_tiempo=cancelacion_a_tiempo,
        )
    )
    if not resultado.rowcount:
        raise ValueError("Esta reserva ya estaba cancelada.")
    db.session.expire(reserva, ["estado", "fecha_cancelacion", "cancelacion_a_tiempo"])

    if cancelacion_a_tiempo:
        tope = current_app.config["MAX_CLASES_RECUPERABLES"]
        tabla_usuario = Usuario.__table__
        db.session.execute(
            update(tabla_usuario)
            .where(tabla_usuario.c.id == usuario.id, tabla_usuario.c.clases_recuperables < tope)
            .values(clases_recuperables=tabla_usuario.c.clases_recuperables + 1)
        )
        # Si ya está en el tope, el WHERE no matchea y no se suma más
        # - la clase se pierde igual, la anticipación con la que avisó
        # no alcanza para "acumular" por encima del máximo permitido.
        db.session.expire(usuario, ["clases_recuperables"])

    return cancelacion_a_tiempo


def notificar_cupo_liberado(clase):
    """
    La "campanita": cuando se cancela una reserva y la Clase vuelve a
    tener cupo, les avisamos por mail a quienes hayan pedido que los
    avisen (AvisoCupo) y todavía no fueron notificados. Se les avisa a
    todos los que estén esperando (no solo al primero): quien reserve
    primero se queda con el lugar.
    """
    if not clase.tiene_cupo:
        return

    pendientes = AvisoCupo.query.filter_by(clase_id=clase.id, notificado=False).all()
    for aviso in pendientes:
        if enviar_aviso_cupo_liberado(aviso):
            aviso.notificado = True
            aviso.fecha_notificado = ahora_estudio()


def enviar_recordatorios_del_dia_siguiente():
    """
    Manda el mail de "mañana tenés clase" a todas las reservas activas
    de clases que son mañana y todavía no recibieron ese recordatorio.

    Pensado para correrse UNA vez por día desde un script aparte (ver
    enviar_recordatorios.py en la raíz), programado con el
    Programador de tareas de Windows (o cron en Linux/Mac). El sistema
    NO lo hace solo: necesita que algo externo lo dispare una vez al día.
    """
    manana = hoy_estudio() + timedelta(days=1)

    reservas = (
        Reserva.query.join(Clase)
        .filter(
            Reserva.estado == "reservada",
            Reserva.recordatorio_enviado.is_(False),
            Clase.fecha == manana,
        )
        .all()
    )

    enviados = 0
    for reserva in reservas:
        if enviar_recordatorio_clase(reserva):
            reserva.recordatorio_enviado = True
            enviados += 1

    db.session.commit()
    return enviados
