from datetime import date, datetime
from calendar import monthrange

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.alumno import bp
from app.extensions import db
from app.models import Clase, Reserva, AvisoCupo
from app.admin.services import generar_clases_para_mes
from app.alumno.services import reservar_clase, cancelar_reserva, notificar_cupo_liberado
from app.integrations.google_calendar import crear_evento_para_reserva, eliminar_evento
from app.integrations.email import enviar_confirmacion_reserva, enviar_aviso_ultima_clase
from app.utils import ahora_estudio, hoy_estudio


@bp.route("/")
@login_required
def dashboard():
    # El panel principal del alumno ES el calendario, así que
    # redirigimos directo ahí en vez de duplicar contenido.
    return redirect(url_for("alumno.calendario"))


@bp.route("/calendario")
@login_required
def calendario():
    hoy = hoy_estudio()

    # Nos aseguramos de que las clases del mes ya estén generadas en
    # el calendario, por si el admin todavía no apretó el botón de
    # "Generar clases del mes". Esta función es idempotente: no pasa
    # nada si ya estaban generadas.
    generar_clases_para_mes(hoy.year, hoy.month)

    ultimo_dia = monthrange(hoy.year, hoy.month)[1]

    # Armamos la info de cada día del mes para pintarla en el calendario.
    dias = []
    for numero_dia in range(1, ultimo_dia + 1):
        fecha_dia = date(hoy.year, hoy.month, numero_dia)
        clases_del_dia = Clase.query.filter_by(fecha=fecha_dia, cancelada=False).all()
        dias.append({
            "fecha": fecha_dia,
            "numero": numero_dia,
            "es_pasado": fecha_dia < hoy,
            "es_hoy": fecha_dia == hoy,
            "tiene_clases": len(clases_del_dia) > 0,
            "clases_con_cupo": sum(1 for c in clases_del_dia if c.tiene_cupo),
        })

    # Para dibujar la grilla semanal (Lunes a Domingo) alineada,
    # necesitamos saber en qué columna cae el día 1 del mes.
    primer_dia_semana = date(hoy.year, hoy.month, 1).weekday()  # 0=Lunes

    return render_template(
        "alumno/calendario.html",
        dias=dias,
        hoy=hoy,
        espacios_vacios=range(primer_dia_semana),
        clases_disponibles=current_user.clases_disponibles,
        clases_recuperables=current_user.clases_recuperables,
    )


@bp.route("/calendario/<fecha_str>")
@login_required
def horarios_del_dia(fecha_str):
    try:
        fecha_dia = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        abort(404)

    hoy = hoy_estudio()

    # Regla del negocio: el alumno reserva "dentro del mismo mes".
    if fecha_dia.year != hoy.year or fecha_dia.month != hoy.month:
        abort(404)

    clases_del_dia = Clase.query.filter_by(fecha=fecha_dia, cancelada=False).order_by(Clase.hora_inicio).all()

    # Para poder mostrar "Ya reservado" en vez del botón de reservar
    mis_reservas_ids = {r.clase_id for r in current_user.reservas.filter_by(estado="reservada")}

    # Para poder mostrar "🔔 te vamos a avisar" en vez del botón de campanita
    mis_avisos_ids = {a.clase_id for a in current_user.avisos_cupo if not a.notificado}

    # Si el día es HOY, algunos horarios puntuales pueden ya haber
    # pasado aunque el día no haya terminado (ej: son las 15hs y hay
    # una clase de las 09hs). Calculamos esto por clase, no solo por día.
    ahora = ahora_estudio()
    horarios_pasados_ids = {
        c.id for c in clases_del_dia if datetime.combine(c.fecha, c.hora_inicio) <= ahora
    }

    return render_template(
        "alumno/horarios_dia.html",
        fecha=fecha_dia,
        clases=clases_del_dia,
        mis_reservas_ids=mis_reservas_ids,
        mis_avisos_ids=mis_avisos_ids,
        horarios_pasados_ids=horarios_pasados_ids,
        clases_disponibles=current_user.clases_disponibles,
        clases_recuperables=current_user.clases_recuperables,
    )


@bp.route("/reservar/<int:clase_id>", methods=["POST"])
@login_required
def reservar(clase_id):
    clase = Clase.query.get_or_404(clase_id)
    try:
        nueva_reserva = reservar_clase(current_user, clase)
        db.session.commit()

        # Sincronizamos con Google Calendar DESPUÉS de guardar en
        # nuestra base (así, si Google falla, la reserva ya quedó
        # guardada de todos modos - Google es un "extra", no algo de
        # lo que dependa el funcionamiento del sistema).
        event_id = crear_evento_para_reserva(nueva_reserva)
        if event_id:
            nueva_reserva.google_event_id = event_id
            db.session.commit()

        # Aviso de "tu clase fue reservada" por mail (best-effort: si
        # no hay mail configurado o falla el envío, la reserva ya
        # quedó guardada de todos modos).
        enviar_confirmacion_reserva(nueva_reserva)

        # Si esta reserva gastó el saldo NORMAL del plan (no un
        # crédito de recuperación) y no le queda más, es la última
        # clase del mes: le recordamos que tiene que abonar para que
        # se le renueve. current_user.clases_disponibles se relee
        # solo de la base (SQLAlchemy expira los objetos después de
        # cada commit), así que ya refleja el descuento de esta reserva.
        if not nueva_reserva.es_recuperacion and current_user.clases_disponibles == 0:
            enviar_aviso_ultima_clase(current_user)

        flash(
            f"¡Turno reservado para el {clase.fecha.strftime('%d/%m')} a las "
            f"{clase.hora_inicio.strftime('%H:%M')}hs!", "success"
        )
    except ValueError as e:
        db.session.rollback()
        flash(str(e), "danger")
    except IntegrityError as e:
        # La reserva pasó los chequeos en Python (había cupo, no
        # estaba ya reservada) pero la base de datos la rechazó igual:
        # otro request (otro alumno reservando el último lugar, o el
        # mismo alumno con doble clic) le ganó de carrera por una
        # fracción de segundo. Esto es justamente lo que el índice
        # único parcial y el trigger de cupo de app/db_constraints.py
        # están para atajar - ver ese archivo para el detalle. Le
        # mostramos al alumno el mismo mensaje que vería si hubiera
        # llegado un poco más tarde, en vez de una pantalla de error.
        db.session.rollback()
        if "CUPO_LLENO" in str(e.orig):
            flash("No quedan cupos disponibles para esta clase.", "danger")
        else:
            flash("Ya tenés un turno reservado para esta clase.", "danger")
    return redirect(url_for("alumno.horarios_del_dia", fecha_str=clase.fecha.isoformat()))


@bp.route("/mis-turnos")
@login_required
def mis_turnos():
    reservas = (
        Reserva.query
        .join(Clase)
        .filter(Reserva.usuario_id == current_user.id, Reserva.estado == "reservada")
        .order_by(Clase.fecha, Clase.hora_inicio)
        .all()
    )
    return render_template(
        "alumno/mis_turnos.html",
        reservas=reservas,
        hoy=hoy_estudio(),
        ahora=ahora_estudio(),
    )


@bp.route("/cancelar/<int:reserva_id>", methods=["POST"])
@login_required
def cancelar(reserva_id):
    reserva = Reserva.query.get_or_404(reserva_id)

    # Un alumno solo puede cancelar SUS PROPIAS reservas, nunca las
    # de otro (esto se valida en el servidor, no alcanza con ocultar
    # el botón en el frontend).
    if reserva.usuario_id != current_user.id:
        abort(403)

    try:
        event_id_a_borrar = reserva.google_event_id
        clase = reserva.clase
        a_tiempo = cancelar_reserva(reserva, current_user)
        db.session.commit()

        # Igual que al crear: borramos en Google DESPUÉS de confirmar
        # la cancelación en nuestra base.
        if event_id_a_borrar:
            eliminar_evento(event_id_a_borrar)

        # Se liberó un lugar: avisamos (mail) a quien haya pedido la
        # campanita para esta clase.
        notificar_cupo_liberado(clase)
        db.session.commit()

        if a_tiempo:
            flash("Turno cancelado a tiempo: se acreditó una clase para recuperar este mes.", "success")
        else:
            flash("Turno cancelado. Como fue con menos de 4hs de anticipación, no se acredita clase de recuperación.", "warning")
    except ValueError as e:
        db.session.rollback()
        flash(str(e), "danger")

    return redirect(url_for("alumno.mis_turnos"))


# ------------------------------------------------------------------
# CAMPANITA: avisarme si se libera un lugar en una clase llena
# ------------------------------------------------------------------

@bp.route("/aviso-cupo/<int:clase_id>", methods=["POST"])
@login_required
def aviso_cupo_crear(clase_id):
    clase = Clase.query.get_or_404(clase_id)

    aviso = AvisoCupo.query.filter_by(usuario_id=current_user.id, clase_id=clase.id).first()
    if aviso is None:
        db.session.add(AvisoCupo(usuario_id=current_user.id, clase_id=clase.id))
    elif aviso.notificado:
        # Ya se le había avisado una vez (y la clase se volvió a
        # llenar): lo re-suscribimos para la próxima vez que se libere.
        aviso.notificado = False
        aviso.fecha_notificado = None
    db.session.commit()
    flash("🔔 Te vamos a avisar por mail si se libera un lugar.", "success")
    return redirect(url_for("alumno.horarios_del_dia", fecha_str=clase.fecha.isoformat()))


@bp.route("/aviso-cupo/<int:clase_id>/cancelar", methods=["POST"])
@login_required
def aviso_cupo_cancelar(clase_id):
    clase = Clase.query.get_or_404(clase_id)

    aviso = AvisoCupo.query.filter_by(usuario_id=current_user.id, clase_id=clase.id).first()
    if aviso:
        db.session.delete(aviso)
        db.session.commit()
        flash("Aviso cancelado.", "info")
    return redirect(url_for("alumno.horarios_del_dia", fecha_str=clase.fecha.isoformat()))
