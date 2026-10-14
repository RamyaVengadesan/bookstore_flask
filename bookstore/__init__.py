import os
import secrets
from pathlib import Path

from flask import Flask, g, render_template, request

from . import db as database
from .utils import (cart_count, check_csrf, csrf_token, load_user, local_dt, money,
                    order_ref)


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "bookstore.sqlite"),
        TZ_OFFSET_MINUTES=330,                     # IST; shown times are converted from UTC
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,        # 2 MB uploads
        UPLOAD_FOLDER=os.path.join(app.static_folder, "uploads"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PER_PAGE=12,
    )
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or _persistent_secret(app.instance_path)
    if test_config:
        app.config.update(test_config)

    database.init_app(app)

    # DB is created on first run so `python run.py` just works.
    if not os.path.exists(app.config["DATABASE"]):
        with app.app_context():
            database.init_db()
            database.create_admin("admin", os.environ.get("ADMIN_PASSWORD", "admin123"))

    from .routes import admin, auth, cart, orders, shop
    for bp in (shop.bp, auth.bp, cart.bp, orders.bp, admin.bp):
        app.register_blueprint(bp)

    app.before_request(load_user)
    app.before_request(check_csrf)

    app.jinja_env.filters["money"] = money
    app.jinja_env.filters["dt"] = local_dt
    app.jinja_env.globals.update(csrf_token=csrf_token, order_ref=order_ref)

    @app.context_processor
    def inject():
        cats = database.query("SELECT * FROM categories ORDER BY name")
        return {"nav_categories": cats, "cart_count": cart_count(),
                "current_endpoint": request.endpoint}

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def client_error(e):
        msgs = {400: "Bad request", 403: "You don't have access to this page",
                404: "We couldn't find that page", 413: "That file is too large (2 MB max)"}
        return render_template("error.html", code=e.code, title=msgs.get(e.code, e.name),
                               detail=getattr(e, "description", "")), e.code

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", code=500, title="Something went wrong on our side",
                               detail="Please try again in a moment."), 500

    return app


def _persistent_secret(instance_path):
    """Generate a random secret key once and keep it in instance/ so sessions survive restarts."""
    path = Path(instance_path) / "secret_key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()
