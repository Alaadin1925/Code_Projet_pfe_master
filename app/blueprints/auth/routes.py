"""Authentication routes."""
from datetime import datetime

from flask import (flash, redirect, render_template, request, url_for)
from flask_login import current_user, login_required, login_user, logout_user

from ...extensions import db
from ...repositories import user_repository
from . import auth_bp


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = user_repository.get_by_username(username)
        if user and user.is_active and user.check_password(password):
            login_user(user)
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            next_url = request.args.get("next")
            return redirect(next_url or url_for("dashboard.index"))
        flash("Identifiants invalides.", "error")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Vous êtes déconnecté.", "success")
    return redirect(url_for("auth.login"))
