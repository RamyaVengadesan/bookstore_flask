"""Registration, login/logout, account page (profile, password, addresses)."""
import hashlib
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import execute, get_db, query
from ..utils import login_required, merge_guest_cart, safe_next, send_email

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-\s]{7,15}$")


def _password_errors(pw):
    errs = []
    if len(pw) < 8:
        errs.append("Password must be at least 8 characters.")
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        errs.append("Password must contain both letters and numbers.")
    return errs


def _start_session(user):
    guest_cart = session.get("cart", {})      # keep the guest's cart across the session reset
    session.clear()
    session["user_id"] = user["id"]
    session.permanent = True
    if guest_cart:
        session["cart"] = guest_cart
        merge_guest_cart(user["id"])


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("shop.home"))
    form = {}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in ("fullname", "username", "email")}
        pw, pw2 = request.form.get("password", ""), request.form.get("confirm", "")
        errors = []
        if len(form["fullname"]) < 3:
            errors.append("Full name must be at least 3 characters.")
        if not USERNAME_RE.match(form["username"]):
            errors.append("Username must be 3-30 characters: letters, numbers or underscores.")
        if not EMAIL_RE.match(form["email"]):
            errors.append("Please enter a valid email address.")
        errors += _password_errors(pw)
        if pw != pw2:
            errors.append("Passwords do not match.")
        if not errors:
            try:
                uid = execute("INSERT INTO users (fullname, username, email, password) VALUES (?,?,?,?)",
                              (form["fullname"], form["username"], form["email"].lower(), generate_password_hash(pw)))
            except sqlite3.IntegrityError:
                errors.append("That username or email is already registered.")
            else:
                _start_session({"id": uid})
                flash(f"Welcome to {current_app.config['STORE_NAME']}, {form['fullname'].split()[0]}!", "success")
                return redirect(url_for("shop.home"))
        for e in errors:
            flash(e, "error")
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("shop.home"))
    nxt = request.values.get("next", "")
    if request.method == "POST":
        ident = request.form.get("username", "").strip()
        pw = request.form.get("password", "")
        user = query("SELECT * FROM users WHERE username=? OR email=?", (ident, ident), one=True)
        if user and check_password_hash(user["password"], pw):
            _start_session(user)
            flash(f"Welcome back, {user['fullname'].split()[0]}!", "success")
            return redirect(safe_next(nxt, "admin.dashboard" if user["is_admin"] else "shop.home"))
        flash("Invalid username/email or password.", "error")
    return render_template("auth/login.html", next=nxt)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("shop.home"))


# ------------------------------------------------------------------ password reset
def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


@bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    link = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = query("SELECT * FROM users WHERE email=?", (email,), one=True) if EMAIL_RE.match(email) else None
        if user:
            token = secrets.token_urlsafe(32)
            expires = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            execute("INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (?,?,?)",
                    (user["id"], _hash(token), expires))
            link = url_for("auth.reset", token=token, _external=True)
            send_email(user["email"], f"Reset your {current_app.config['STORE_NAME']} password",
                       f"Hi {user['fullname'].split()[0]},\n\nUse this link to choose a new password (valid for 1 hour):\n"
                       f"{link}\n\nIf you didn't ask for this, you can ignore this email.")
        flash("If that email is registered, we've sent a link to reset your password.", "info")
        if not current_app.config["DEMO_SHOW_RESET_LINK"]:
            link = None
    return render_template("auth/forgot.html", link=link)


def _valid_reset(token):
    row = query("SELECT * FROM password_resets WHERE token_hash=? AND used=0", (_hash(token),), one=True)
    if row and row["expires_at"] >= datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"):
        return row
    return None


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    row = _valid_reset(token)
    if row is None:
        flash("That reset link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot"))
    if request.method == "POST":
        pw, pw2 = request.form.get("password", ""), request.form.get("confirm", "")
        errors = _password_errors(pw) + (["Passwords do not match."] if pw != pw2 else [])
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db = get_db()
            db.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(pw), row["user_id"]))
            db.execute("UPDATE password_resets SET used=1 WHERE user_id=?", (row["user_id"],))
            db.commit()
            flash("Your password has been changed. You can log in now.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", token=token)


# ------------------------------------------------------------------ account
@bp.route("/account")
@login_required
def account():
    addresses = query("SELECT * FROM addresses WHERE user_id=? ORDER BY is_default DESC, id", (g.user["id"],))
    stats = query("""SELECT COUNT(*) orders, COALESCE(SUM(total),0) spent FROM orders
                     WHERE user_id=? AND status!='Cancelled'""", (g.user["id"],), one=True)
    return render_template("auth/account.html", addresses=addresses, stats=stats)


@bp.route("/account/profile", methods=["POST"])
@login_required
def update_profile():
    fullname = request.form.get("fullname", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    if len(fullname) < 3 or not EMAIL_RE.match(email) or (phone and not PHONE_RE.match(phone)):
        flash("Please check your name, email and phone number.", "error")
    else:
        try:
            execute("UPDATE users SET fullname=?, email=?, phone=? WHERE id=?", (fullname, email, phone, g.user["id"]))
            flash("Profile updated.", "success")
        except sqlite3.IntegrityError:
            flash("That email is already used by another account.", "error")
    return redirect(url_for("auth.account"))


@bp.route("/account/password", methods=["POST"])
@login_required
def change_password():
    cur, new, conf = (request.form.get(k, "") for k in ("current", "new", "confirm"))
    errors = _password_errors(new)
    if not check_password_hash(g.user["password"], cur):
        errors.insert(0, "Your current password is incorrect.")
    if new != conf:
        errors.append("New passwords do not match.")
    if errors:
        for e in errors:
            flash(e, "error")
    else:
        execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(new), g.user["id"]))
        flash("Password changed.", "success")
    return redirect(url_for("auth.account"))


def validate_address(form):
    d = {k: form.get(k, "").strip() for k in ("full_name", "phone", "line1", "line2", "city", "state", "pincode")}
    errors = []
    if len(d["full_name"]) < 3:
        errors.append("Enter the recipient's full name.")
    if not PHONE_RE.match(d["phone"]):
        errors.append("Enter a valid phone number.")
    if len(d["line1"]) < 5:
        errors.append("Enter the street address.")
    if not d["city"] or not d["state"]:
        errors.append("City and state are required.")
    if not re.fullmatch(r"\d{6}", d["pincode"]):
        errors.append("PIN code must be 6 digits.")
    return d, errors


@bp.route("/account/address", methods=["POST"])
@login_required
def add_address():
    d, errors = validate_address(request.form)
    nxt = safe_next(request.form.get("next"), "auth.account")
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(nxt)
    first = query("SELECT 1 FROM addresses WHERE user_id=?", (g.user["id"],), one=True) is None
    default = 1 if (first or request.form.get("is_default")) else 0
    db = get_db()
    if default:
        db.execute("UPDATE addresses SET is_default=0 WHERE user_id=?", (g.user["id"],))
    db.execute("""INSERT INTO addresses (user_id, full_name, phone, line1, line2, city, state, pincode, is_default)
                  VALUES (?,?,?,?,?,?,?,?,?)""",
               (g.user["id"], d["full_name"], d["phone"], d["line1"], d["line2"], d["city"], d["state"], d["pincode"], default))
    db.commit()
    flash("Address saved.", "success")
    return redirect(nxt)


@bp.route("/account/address/<int:aid>/delete", methods=["POST"])
@login_required
def delete_address(aid):
    execute("DELETE FROM addresses WHERE id=? AND user_id=?", (aid, g.user["id"]))
    flash("Address removed.", "info")
    return redirect(url_for("auth.account"))


@bp.route("/account/address/<int:aid>/default", methods=["POST"])
@login_required
def default_address(aid):
    db = get_db()
    if db.execute("SELECT 1 FROM addresses WHERE id=? AND user_id=?", (aid, g.user["id"])).fetchone():
        db.execute("UPDATE addresses SET is_default=0 WHERE user_id=?", (g.user["id"],))
        db.execute("UPDATE addresses SET is_default=1 WHERE id=?", (aid,))
        db.commit()
    return redirect(url_for("auth.account"))
