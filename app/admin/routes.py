from datetime import datetime, timedelta

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.admin import bp
from app.decorators import admin_required
from app.extensions import db
from app.models import Usuario, Clase, Plan, Horario, InscripcionFija, Reserva, AvisoCupo
from app.admin.forms import UsuarioForm, HorarioForm, DIAS_SEMANA
from app.admin.services import (
    generar_clases_para_mes, asignar_horario_fijo, quitar_horario_fijo,
    cancelar_clase, cancelar_clases_del_dia, reactivar_clase,
)
from app.integrations.google_calendar import eliminar_evento
from app.integrations.email import enviar_aviso_clase_cancelada
from app.utils import hoy_estudio


@bp.route("/")
@login_required
@admin_required
def dashboard():
    total_alumnos = Usuario.query.filter_by(rol="alumno", activo=True).count()
    clases_hoy = Clase.query.filter_by(fecha=hoy_estudio(), cancelada=False).count()
    return render_template("admin/dashboard.html", total_alumnos=total_alumnos, clases_hoy=clases_hoy)


# ------------------------------------------------------------------
# GESTIÓN DE USUARIOS (crear, editar, listar, dar de baja/alta)
# ------------------------------------------------------------------

def _cargar_choices_plan(form):
    """
    Las opciones del SelectField de Plan dependen de lo que haya en
    la base de datos, así que las completamos "a mano" en cada
    request (no se pueden dejar fijas en la clase del formulario).
    Agregamos una opción "0 = sin plan" para los administradores,
    que no necesitan uno.
    """
    planes = Plan.query.filter_by(activo=True).all()
    form.plan_id.choices = [(0, "— Sin plan —")] + [(p.id, p.nombre) for p in planes]


@bp.route("/usuarios")
@login_required
@admin_required
def usuarios():
    """Listado de todos los usuarios (admins y alumnos)."""
    filtro_rol = request.args.get("rol")  # ?rol=alumno o ?rol=admin, opcional
    query = Usuario.query
    if filtro_rol in ("alumno", "admin"):
        query = query.filter_by(rol=filtro_rol)
    lista_usuarios = query.order_by(Usuario.activo.desc(), Usuario.nombre).all()
    return render_template("admin/usuarios_lista.html", usuarios=lista_usuarios, filtro_rol=filtro_rol)


@bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def usuario_nuevo():
    form = UsuarioForm()
    _cargar_choices_plan(form)

    if form.validate_on_submit():
        # Al CREAR, la contraseña es obligatoria (acá sí la exigimos a mano)
        if not form.password.data:
            flash("La contraseña es obligatoria para un usuario nuevo.", "danger")
            return render_template("admin/usuarios_form.html", form=form, modo="crear")

        nuevo = Usuario(
            nombre=form.nombre.data.strip(),
            apellido=form.apellido.data.strip(),
            email=form.email.data.lower().strip(),
            rol=form.rol.data,
            modalidad=form.modalidad.data,
            plan_id=form.plan_id.data if form.plan_id.data != 0 else None,
            clases_disponibles=form.clases_disponibles.data or 0,
        )
        nuevo.set_password(form.password.data)

        db.session.add(nuevo)
        db.session.commit()
        flash(f"Usuario {nuevo.nombre_completo} creado correctamente.", "success")
        return redirect(url_for("admin.usuarios"))

    return render_template("admin/usuarios_form.html", form=form, modo="crear")


@bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def usuario_editar(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)

    # Pasamos usuario_actual=usuario para que la validación de email
    # duplicado no se confunda con el propio usuario que edito.
    form = UsuarioForm(usuario_actual=usuario, obj=usuario)
    _cargar_choices_plan(form)

    # Para que la plantilla pueda avisarle al admin ANTES de mandar el
    # formulario (confirm() del lado del navegador) si está por bajarle
    # el plan a un alumno con horarios fijos asignados - ver más abajo
    # por qué eso importa.
    planes_clases = {p.id: p.clases_por_mes for p in Plan.query.filter_by(activo=True).all()}
    plan_actual_clases = usuario.plan.clases_por_mes if usuario.plan else 0
    cantidad_horarios_fijos = sum(1 for i in usuario.inscripciones_fijas if i.activo)

    if request.method == "GET":
        # Precargamos el plan actual (0 si no tiene)
        form.plan_id.data = usuario.plan_id or 0

    if form.validate_on_submit():
        # Evitamos que un admin se quite el rol de admin a sí mismo
        # por error y se quede sin poder administrar el sistema.
        if usuario.id == current_user.id and form.rol.data != "admin":
            flash("No podés quitarte el rol de administrador a vos mismo.", "danger")
            return render_template(
                "admin/usuarios_form.html", form=form, modo="editar", usuario=usuario,
                planes_clases=planes_clases, plan_actual_clases=plan_actual_clases,
                cantidad_horarios_fijos=cantidad_horarios_fijos,
            )

        plan_nuevo_id = form.plan_id.data if form.plan_id.data != 0 else None
        plan_anterior = usuario.plan
        plan_nuevo = Plan.query.get(plan_nuevo_id) if plan_nuevo_id else None
        clases_antes = plan_anterior.clases_por_mes if plan_anterior else 0
        clases_despues = plan_nuevo.clases_por_mes if plan_nuevo else 0

        # Si el nuevo plan tiene MENOS clases por mes que el anterior,
        # los horarios fijos que el alumno tenía asignados dejan de
        # tener sentido (fueron pensados para un cupo mensual más
        # grande - ver horarios_fijos_permitidos en admin/services.py) y
        # podrían volver a generar el mismo desfasaje de saldo que ya
        # arreglamos ahí. En vez de dejarlos "colgados", se los
        # quitamos de una: cancela sus turnos futuros por esos
        # horarios y borra la asignación fija. La confirmación
        # ("¿querés continuar?") se le muestra al admin del lado del
        # navegador antes de mandar el formulario (ver usuarios_form.html);
        # acá repetimos la lógica de todos modos porque la decisión de
        # negocio (bajar de plan implica perder los horarios fijos)
        # tiene que valer sin importar si el JS llegó a correr o no.
        inscripciones_activas = [i for i in usuario.inscripciones_fijas if i.activo]
        horarios_quitados = 0
        if plan_nuevo_id != usuario.plan_id and clases_despues < clases_antes and inscripciones_activas:
            for inscripcion in inscripciones_activas:
                quitar_horario_fijo(inscripcion)
                horarios_quitados += 1

        usuario.nombre = form.nombre.data.strip()
        usuario.apellido = form.apellido.data.strip()
        usuario.email = form.email.data.lower().strip()
        usuario.rol = form.rol.data
        usuario.modalidad = form.modalidad.data
        usuario.plan_id = plan_nuevo_id
        usuario.clases_disponibles = form.clases_disponibles.data or 0

        # La contraseña solo se cambia si se escribió algo nuevo
        if form.password.data:
            usuario.set_password(form.password.data)

        db.session.commit()

        if horarios_quitados > 0:
            flash(
                f"Usuario {usuario.nombre_completo} actualizado. Como bajó a un plan con menos clases, se le "
                f"quitaron sus {horarios_quitados} horario(s) fijo(s) y se cancelaron los turnos futuros que "
                "tenía por esos horarios. Se recomienda avisarle para que vuelva a reservar sus clases dentro "
                "del nuevo plan.", "warning"
            )
        else:
            flash(f"Usuario {usuario.nombre_completo} actualizado correctamente.", "success")
        return redirect(url_for("admin.usuarios"))

    return render_template(
        "admin/usuarios_form.html", form=form, modo="editar", usuario=usuario,
        planes_clases=planes_clases, plan_actual_clases=plan_actual_clases,
        cantidad_horarios_fijos=cantidad_horarios_fijos,
    )


@bp.route("/usuarios/<int:usuario_id>/baja", methods=["POST"])
@login_required
@admin_required
def usuario_dar_de_baja(usuario_id):
    """
    OJO: acá NO borramos el usuario de la base de datos (DELETE).
    Lo marcamos como inactivo (activo=False).

    ¿Por qué no borrarlo directamente? Porque el usuario puede tener
    Reservas históricas asociadas (clases a las que fue, canceló,
    etc.). Si lo borráramos, se rompería ese historial. Dar de baja
    (desactivar) es la práctica estándar: el usuario no puede volver
    a loguearse, pero el historial queda intacto.
    """
    usuario = Usuario.query.get_or_404(usuario_id)

    if usuario.id == current_user.id:
        flash("No podés darte de baja a vos mismo.", "danger")
        return redirect(url_for("admin.usuarios"))

    usuario.activo = False
    db.session.commit()
    flash(f"Usuario {usuario.nombre_completo} dado de baja.", "info")
    return redirect(url_for("admin.usuarios"))


@bp.route("/usuarios/<int:usuario_id>/reactivar", methods=["POST"])
@login_required
@admin_required
def usuario_reactivar(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    usuario.activo = True
    db.session.commit()
    flash(f"Usuario {usuario.nombre_completo} reactivado.", "success")
    return redirect(url_for("admin.usuarios"))


@bp.route("/usuarios/<int:usuario_id>/eliminar", methods=["POST"])
@login_required
@admin_required
def usuario_eliminar(usuario_id):
    """
    Borrado DEFINITIVO: borra al usuario y, en cascada, todo lo que
    depende de él (reservas, inscripciones a horarios fijos, avisos
    de cupo pendientes), sin excepción. Esto pierde el historial de
    ese alumno para siempre - si en cambio solo se lo quiere sacar de
    circulación sin perder registros, la opción es "dar de baja"
    (usuario_dar_de_baja), que desactiva la cuenta sin borrar nada.
    """
    usuario = Usuario.query.get_or_404(usuario_id)

    if usuario.id == current_user.id:
        flash("No podés eliminarte a vos mismo.", "danger")
        return redirect(url_for("admin.usuarios"))

    nombre = usuario.nombre_completo

    # Antes de borrar las reservas, borramos sus eventos de Google
    # Calendar (si tenían uno sincronizado) para no dejar turnos
    # huérfanos en el calendario del estudio.
    for reserva in usuario.reservas:
        if reserva.google_event_id:
            eliminar_evento(reserva.google_event_id)

    usuario.reservas.delete()
    AvisoCupo.query.filter_by(usuario_id=usuario.id).delete()
    InscripcionFija.query.filter_by(usuario_id=usuario.id).delete()

    db.session.delete(usuario)
    db.session.commit()
    flash(f"Usuario {nombre} eliminado definitivamente, junto con todo su historial.", "info")
    return redirect(url_for("admin.usuarios"))


@bp.route("/usuarios/<int:usuario_id>/restablecer-saldo", methods=["POST"])
@login_required
@admin_required
def usuario_restablecer_saldo(usuario_id):
    """
    Restablece el saldo mensual del alumno según su plan. El sistema
    NUNCA lo hace solo al empezar el mes: es el admin quien decide
    cuándo, apretando este botón (o editando el número a mano en el
    formulario de edición).

    También reinicia clases_recuperables a 0: las clases de
    recuperación se acreditan para usarse "dentro del mismo mes" (ver
    cancelar_reserva en app/alumno/services.py), así que no tiene
    sentido que sigan arrastrándose una vez que el admin da por
    iniciado un nuevo mes.
    """
    usuario = Usuario.query.get_or_404(usuario_id)

    if not usuario.plan:
        flash(f"{usuario.nombre_completo} no tiene un plan asignado.", "warning")
        return redirect(url_for("admin.usuarios"))

    usuario.clases_disponibles = usuario.plan.clases_por_mes
    usuario.clases_recuperables = 0
    db.session.commit()
    flash(f"Saldo de {usuario.nombre_completo} restablecido a {usuario.plan.clases_por_mes} clases.", "success")
    return redirect(url_for("admin.usuarios"))


# ------------------------------------------------------------------
# HORARIOS FIJOS (asignar a un alumno de modalidad "fijo" a un día y
# horario semanal, para que quede reservado automáticamente)
# ------------------------------------------------------------------

@bp.route("/usuarios/<int:usuario_id>/horarios-fijos", methods=["GET", "POST"])
@login_required
@admin_required
def usuario_horarios_fijos(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    if usuario.es_admin:
        abort(404)

    if request.method == "POST":
        # El horario_id llega de un <form>: si viene vacío o con algo
        # que no es un número, int() explotaría con un 500 en vez de
        # devolver un error normal.
        try:
            horario_id = int(request.form.get("horario_id", ""))
        except (TypeError, ValueError):
            abort(400)
        horario = Horario.query.get_or_404(horario_id)
        accion = request.form.get("accion")

        if accion == "asignar":
            try:
                _, reservadas, saltadas_por_saldo, saltadas_por_cupo = asignar_horario_fijo(usuario, horario)
                if saltadas_por_saldo > 0:
                    flash(
                        f"{usuario.nombre_completo} quedó asignada/o de forma fija a {horario}, pero no "
                        f"tenía saldo suficiente y se saltearon {saltadas_por_saldo} clase(s) ya generadas "
                        "(no le quedaron turnos reales para esas fechas). Cargale saldo (clases disponibles) "
                        "y volvé a asignarlo, o esperá a la próxima generación mensual.", "warning"
                    )
                elif saltadas_por_cupo > 0:
                    flash(
                        f"{usuario.nombre_completo} quedó asignada/o de forma fija a {horario}, pero "
                        f"{saltadas_por_cupo} clase(s) de este mes ya estaban llenas y no se le pudo reservar "
                        "el lugar ahí. Revisá esas fechas en Clases si querés hacerle lugar.", "warning"
                    )
                else:
                    flash(f"{usuario.nombre_completo} quedó asignada/o de forma fija a {horario}.", "success")
            except ValueError as e:
                flash(str(e), "danger")
        elif accion == "quitar":
            inscripcion = InscripcionFija.query.filter_by(usuario_id=usuario.id, horario_id=horario.id).first()
            if inscripcion:
                quitar_horario_fijo(inscripcion)
                flash("Horario fijo quitado.", "info")

        return redirect(url_for("admin.usuario_horarios_fijos", usuario_id=usuario.id))

    horarios_activos = Horario.query.filter_by(activo=True).order_by(Horario.dia_semana, Horario.hora).all()
    asignados_ids = {i.horario_id for i in usuario.inscripciones_fijas if i.activo}

    return render_template(
        "admin/usuario_horarios_fijos.html",
        usuario=usuario,
        horarios_activos=horarios_activos,
        asignados_ids=asignados_ids,
        dias_semana=DIAS_SEMANA,
    )


# ------------------------------------------------------------------
# GESTIÓN DE HORARIOS (la grilla semanal + generación de clases)
# ------------------------------------------------------------------

@bp.route("/horarios")
@login_required
@admin_required
def horarios():
    lista = Horario.query.order_by(Horario.dia_semana, Horario.hora).all()

    # Agrupamos los horarios por día de la semana para mostrarlos
    # como una grilla (Lunes: [...], Martes: [...], etc.)
    por_dia = {i: [] for i in range(7)}
    for h in lista:
        por_dia[h.dia_semana].append(h)

    return render_template(
        "admin/horarios_lista.html",
        por_dia=por_dia,
        dias_semana=DIAS_SEMANA,
        hoy=hoy_estudio(),
    )


@bp.route("/horarios/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def horario_nuevo():
    form = HorarioForm()

    if form.validate_on_submit():
        # Evitamos cargar el mismo día+hora dos veces por error
        ya_existe = Horario.query.filter_by(dia_semana=form.dia_semana.data, hora=form.hora.data).first()
        if ya_existe:
            flash("Ya existe un horario cargado para ese día y esa hora.", "danger")
            return render_template("admin/horarios_form.html", form=form)

        nuevo = Horario(dia_semana=form.dia_semana.data, hora=form.hora.data)
        db.session.add(nuevo)
        db.session.commit()
        flash("Horario agregado a la grilla semanal.", "success")
        return redirect(url_for("admin.horarios"))

    return render_template("admin/horarios_form.html", form=form)


@bp.route("/horarios/<int:horario_id>/toggle", methods=["POST"])
@login_required
@admin_required
def horario_toggle(horario_id):
    """
    Activa/desactiva un horario de la grilla semanal SIN borrarlo.
    Un horario desactivado deja de generar clases nuevas hacia
    adelante, pero no toca las clases que ya se generaron ni las
    reservas que ya tenían los alumnos (para eso están, aparte,
    "Cancelar clase" y "Cancelar todas las clases del día" en
    /clases - pensadas para un día puntual, ej. un feriado, sin tener
    que dar de baja el horario semanal entero).
    """
    horario = Horario.query.get_or_404(horario_id)
    horario.activo = not horario.activo
    db.session.commit()
    estado = "activado" if horario.activo else "desactivado"
    flash(f"Horario {estado}.", "info")
    return redirect(url_for("admin.horarios"))


@bp.route("/horarios/<int:horario_id>/eliminar", methods=["POST"])
@login_required
@admin_required
def horario_eliminar(horario_id):
    """
    Igual que con los usuarios: solo permitimos el borrado DEFINITIVO
    si ese horario todavía no generó ninguna clase en el calendario.
    Si ya generó clases (aunque sea una), lo mandamos a desactivar
    en su lugar, para no perder el historial de esas clases.
    """
    horario = Horario.query.get_or_404(horario_id)

    if len(horario.clases_generadas) > 0:
        flash("Este horario ya generó clases en el calendario: no se puede eliminar, pero podés desactivarlo.", "warning")
        return redirect(url_for("admin.horarios"))

    # Antes de borrar el horario hay que borrar las InscripcionFija que
    # lo apuntan. Si no, quedan filas huérfanas con un horario_id que ya
    # no existe (SQLite no fuerza las claves foráneas por defecto), y la
    # próxima vez que se lee inscripcion.horario eso da None: revienta
    # con AttributeError tanto en admin/services.asignar_horario_fijo
    # (i.horario.dia_semana) como en la pantalla de horarios fijos del
    # alumno. No usamos quitar_horario_fijo() acá porque este horario
    # todavía no generó ninguna clase: no hay reservas que cancelar.
    inscripciones_borradas = InscripcionFija.query.filter_by(horario_id=horario.id).delete()

    db.session.delete(horario)
    db.session.commit()
    if inscripciones_borradas:
        flash(
            f"Horario eliminado. También se quitó de los horarios fijos de {inscripciones_borradas} alumna/o "
            "(no tenían turnos reservados: este horario nunca llegó a generar clases).", "info"
        )
    else:
        flash("Horario eliminado.", "info")
    return redirect(url_for("admin.horarios"))


@bp.route("/horarios/generar-clases", methods=["POST"])
@login_required
@admin_required
def generar_clases():
    """
    Toma la grilla semanal (los Horarios activos) y genera las clases
    concretas en el calendario para el mes indicado. Se puede correr
    varias veces sin problema: no duplica clases ya generadas.
    """
    hoy = hoy_estudio()

    # Estos dos valores llegan de un <form>. int() sobre algo vacío o
    # no numérico tira un 500, y un año fuera de rango (0, 99999) hace
    # explotar date(anio, mes, 1) más adentro, en generar_clases_para_mes.
    # Los validamos acá, que es donde entran al sistema.
    try:
        anio = int(request.form.get("anio", hoy.year))
        mes = int(request.form.get("mes", hoy.month))
    except (TypeError, ValueError):
        flash("Mes o año inválido.", "danger")
        return redirect(url_for("admin.horarios"))

    if not 1 <= mes <= 12:
        flash("Mes inválido.", "danger")
        return redirect(url_for("admin.horarios"))

    # Rango razonable: el año actual y hasta 5 hacia adelante. Generar
    # clases de años pasados no sirve para nada y solo llena la base.
    if not hoy.year <= anio <= hoy.year + 5:
        flash(f"Año inválido: solo se pueden generar clases entre {hoy.year} y {hoy.year + 5}.", "danger")
        return redirect(url_for("admin.horarios"))

    creadas = generar_clases_para_mes(anio, mes)
    flash(f"Se generaron {creadas} clases nuevas para {mes}/{anio}.", "success")
    return redirect(url_for("admin.horarios"))


# ------------------------------------------------------------------
# CLASES DEL DÍA: quién se anotó en cada una y cuántas camillas
# están ocupadas.
# ------------------------------------------------------------------

@bp.route("/clases")
@login_required
@admin_required
def clases():
    hoy = hoy_estudio()
    fecha_str = request.args.get("fecha")
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else hoy
    except ValueError:
        fecha = hoy

    clases_del_dia = Clase.query.filter_by(fecha=fecha).order_by(Clase.hora_inicio).all()
    for clase in clases_del_dia:
        clase.reservas_activas = (
            clase.reservas.filter_by(estado="reservada")
            .join(Usuario)
            .order_by(Usuario.nombre)
            .all()
        )

    # Para el botón de "cancelar todas las clases del día": la lista
    # combinada (sin repetidos) de alumnas/os afectados en CUALQUIER
    # clase no cancelada de este día, para mostrarla en la confirmación
    # antes de aplicar la baja masiva (ver clases.html).
    afectados_del_dia = []
    ids_ya_agregados = set()
    for clase in clases_del_dia:
        if clase.cancelada:
            continue
        for reserva in clase.reservas_activas:
            if reserva.usuario_id not in ids_ya_agregados:
                ids_ya_agregados.add(reserva.usuario_id)
                afectados_del_dia.append(reserva.usuario)

    return render_template(
        "admin/clases.html",
        clases=clases_del_dia,
        fecha=fecha,
        hoy=hoy,
        dia_anterior=fecha - timedelta(days=1),
        dia_siguiente=fecha + timedelta(days=1),
        afectados_del_dia=afectados_del_dia,
    )


@bp.route("/clases/<int:clase_id>/cancelar", methods=["POST"])
@login_required
@admin_required
def clase_cancelar(clase_id):
    """
    Cancela una clase puntual (ej: feriado). La confirmación de "¿estás
    seguro?" con el detalle de a quién afecta se le muestra al admin
    del lado del navegador, en la misma página de /clases (ver
    clases.html: ahí mismo ya se lista quién está anotado en cada
    clase). Acá del lado del servidor cancelamos de verdad: se le
    avisa por mail a cada alumno afectado y se le acredita una clase
    para recuperar (ver admin.services.cancelar_clase).
    """
    clase = Clase.query.get_or_404(clase_id)
    fecha_str = clase.fecha.isoformat()

    if clase.cancelada:
        flash("Esta clase ya estaba cancelada.", "info")
        return redirect(url_for("admin.clases", fecha=fecha_str))

    reservas_canceladas = cancelar_clase(clase)

    # Google Calendar y el mail son "best-effort" (ver el resto del
    # sistema): la clase ya quedó cancelada en nuestra base pase lo
    # que pase acá.
    for reserva in reservas_canceladas:
        if reserva.google_event_id:
            eliminar_evento(reserva.google_event_id)
        enviar_aviso_clase_cancelada(reserva.usuario, clase)

    if reservas_canceladas:
        flash(
            f"Clase del {clase.fecha.strftime('%d/%m')} a las {clase.hora_inicio.strftime('%H:%M')}hs cancelada. "
            f"Se avisó por mail a {len(reservas_canceladas)} alumno(s) y se le acreditó una clase para recuperar "
            "a cada uno.", "warning"
        )
    else:
        flash(
            f"Clase del {clase.fecha.strftime('%d/%m')} a las {clase.hora_inicio.strftime('%H:%M')}hs cancelada. "
            "No tenía alumnos anotados.", "info"
        )

    return redirect(url_for("admin.clases", fecha=fecha_str))


@bp.route("/clases/<int:clase_id>/reactivar", methods=["POST"])
@login_required
@admin_required
def clase_reactivar(clase_id):
    """
    Reactiva una clase cancelada por error (ver
    admin.services.reactivar_clase): la vuelve a dejar disponible para
    reservar, y recupera el crédito de recuperación de cada alumno
    afectado si todavía no lo gastó en otra clase.
    """
    clase = Clase.query.get_or_404(clase_id)
    fecha_str = clase.fecha.isoformat()

    if not clase.cancelada:
        flash("Esta clase no estaba cancelada.", "info")
        return redirect(url_for("admin.clases", fecha=fecha_str))

    recuperados = reactivar_clase(clase)

    mensaje = (
        f"Clase del {clase.fecha.strftime('%d/%m')} a las {clase.hora_inicio.strftime('%H:%M')}hs reactivada. "
        "Ya está disponible para reservar de nuevo."
    )
    if recuperados:
        mensaje += f" Se recuperaron {recuperados} crédito(s) de recuperación que todavía no se habían usado."
    flash(mensaje, "success")

    return redirect(url_for("admin.clases", fecha=fecha_str))


@bp.route("/clases/cancelar-dia", methods=["POST"])
@login_required
@admin_required
def clases_cancelar_dia():
    """
    Cancela TODAS las clases de una fecha puntual (cualquier horario,
    no solo uno) de una sola vez - pensado para un feriado o un día
    entero que el estudio no abre, sin tener que cancelar clase por
    clase. Mismo criterio que clase_cancelar: la confirmación de
    "¿estás seguro?" con el detalle de a quién afecta se le muestra al
    admin del lado del navegador (ver clases.html); acá se aplica de
    verdad, clase por clase (ver admin.services.cancelar_clases_del_dia).
    """
    fecha_str = request.form.get("fecha")
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        abort(404)

    reservas_canceladas = cancelar_clases_del_dia(fecha)

    for reserva in reservas_canceladas:
        if reserva.google_event_id:
            eliminar_evento(reserva.google_event_id)
        enviar_aviso_clase_cancelada(reserva.usuario, reserva.clase)

    if reservas_canceladas:
        flash(
            f"Se cancelaron todas las clases del {fecha.strftime('%d/%m')}. Se avisó por mail a "
            f"{len(reservas_canceladas)} alumno(s) y se le acreditó una clase para recuperar a cada uno.", "warning"
        )
    else:
        flash(f"Se cancelaron todas las clases del {fecha.strftime('%d/%m')}. No tenían alumnos anotados.", "info")

    return redirect(url_for("admin.clases", fecha=fecha_str))
