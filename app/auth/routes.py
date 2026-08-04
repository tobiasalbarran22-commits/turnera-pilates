from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required

from app.auth import bp
from app.auth.forms import LoginForm, CambiarPasswordForm
from app.extensions import db
from app.models import Usuario


@bp.route("/login", methods=["GET", "POST"])
def login():
    # Si ya está logueado, no tiene sentido mostrarle el login de nuevo:
    # lo mandamos directo a su panel correspondiente.
    if current_user.is_authenticated:
        return redirect(url_for("auth.redirigir_segun_rol"))

    form = LoginForm()

    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(email=form.email.data.lower().strip()).first()

        # OJO: comparamos primero que el usuario exista Y DESPUÉS la
        # contraseña. Si escribimos la condición al revés, un email
        # inexistente podría dar un error distinto ("AttributeError")
        # y eso le da pistas a un atacante sobre qué emails existen.
        if usuario is None or not usuario.check_password(form.password.data):
            flash("Email o contraseña incorrectos.", "danger")
            return redirect(url_for("auth.login"))

        if not usuario.activo:
            flash("Tu usuario está desactivado. Consultá con el estudio.", "warning")
            return redirect(url_for("auth.login"))

        login_user(usuario, remember=form.recordarme.data)
        return redirect(url_for("auth.redirigir_segun_rol"))

    return render_template("auth/login.html", form=form)


@bp.route("/redirigir")
@login_required
def redirigir_segun_rol():
    """
    Punto único de entrada después del login: decide a qué panel
    mandar al usuario según su rol. Así, si mañana agregamos un
    tercer tipo de usuario (ej: "profesor"), solo tocamos acá.
    """
    if current_user.es_admin:
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("alumno.dashboard"))


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Cerraste sesión correctamente.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/cambiar-password", methods=["GET", "POST"])
@login_required
def cambiar_password():
    """
    Autoservicio: cualquier usuario logueado (alumno o admin) cambia
    su propia contraseña. Para resetear la contraseña de OTRO usuario
    sigue existiendo el campo en admin/usuario_editar - eso lo hace
    el admin a mano cuando alguien se la olvida y no puede loguearse.
    """
    form = CambiarPasswordForm()

    if form.validate_on_submit():
        if not current_user.check_password(form.password_actual.data):
            flash("La contraseña actual no es correcta.", "danger")
            return render_template("auth/cambiar_password.html", form=form)

        current_user.set_password(form.password_nueva.data)
        db.session.commit()
        flash("Tu contraseña se actualizó correctamente.", "success")
        return redirect(url_for("auth.redirigir_segun_rol"))

    return render_template("auth/cambiar_password.html", form=form)
