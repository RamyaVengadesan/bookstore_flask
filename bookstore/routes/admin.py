"""Admin panel: dashboard, books, orders, customers, coupons, categories."""
import os
import re
import secrets
import sqlite3
from datetime import date, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from ..db import get_db, query
from ..utils import ORDER_FLOW, add_event, admin_required, restock_order

bp = Blueprint("admin", __name__, url_prefix="/admin")

ALLOWED_IMG = {"png", "jpg", "jpeg", "webp", "gif"}
ALL_STATUSES = ORDER_FLOW + ["Cancelled"]


@bp.route("/")
@admin_required
def dashboard():
    one = lambda sql, a=(): query(sql, a, one=True)
    totals = one("""SELECT COALESCE(SUM(total),0) revenue, COUNT(*) orders FROM orders WHERE status!='Cancelled'""")
    since = (date.today() - timedelta(days=6)).isoformat()
    daily = {r["d"]: r for r in query(
        """SELECT date(created_at) d, SUM(total) revenue, COUNT(*) n FROM orders
           WHERE status!='Cancelled' AND date(created_at) >= ? GROUP BY d""", (since,))}
    chart = []
    for i in range(7):
        d = (date.today() - timedelta(days=6 - i)).isoformat()
        chart.append({"label": d[8:] + "/" + d[5:7], "revenue": daily[d]["revenue"] if d in daily else 0,
                      "n": daily[d]["n"] if d in daily else 0})
    peak = max((c["revenue"] for c in chart), default=0) or 1
    return render_template(
        "admin/dashboard.html", totals=totals, chart=chart, peak=peak,
        users=one("SELECT COUNT(*) n FROM users WHERE is_admin=0")["n"],
        books=one("SELECT COUNT(*) n, COALESCE(SUM(stock),0) copies FROM books"),
        pending=one("SELECT COUNT(*) n FROM orders WHERE status IN ('Pending','Confirmed')")["n"],
        low_stock=query("SELECT id, name, stock FROM books WHERE stock <= 5 ORDER BY stock, name LIMIT 8"),
        recent=query("""SELECT o.*, u.fullname FROM orders o JOIN users u ON u.id=o.user_id
                        ORDER BY o.id DESC LIMIT 6"""),
        top=query("""SELECT oi.title, SUM(oi.qty) sold, SUM(oi.qty*oi.price) revenue FROM order_items oi
                     JOIN orders o ON o.id=oi.order_id WHERE o.status!='Cancelled'
                     GROUP BY oi.title ORDER BY sold DESC LIMIT 5"""),
    )


# ------------------------------------------------------------------ books
@bp.route("/books")
@admin_required
def books():
    q = request.args.get("q", "").strip()
    rows = query("""SELECT b.*, c.name AS category_name FROM books b JOIN categories c ON c.id=b.category_id
                    WHERE b.name LIKE ? OR b.author LIKE ? OR b.isbn LIKE ? ORDER BY b.id DESC""",
                 [f"%{q}%"] * 3)
    return render_template("admin/books.html", books=rows, q=q)


def _save_upload(file):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_IMG:
        raise ValueError("Cover image must be PNG, JPG, WEBP or GIF.")
    name = f"{secrets.token_hex(8)}.{ext}"
    file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], name))
    return url_for("static", filename=f"uploads/{name}")


def _book_form(book=None):
    cats = query("SELECT * FROM categories ORDER BY name")
    if request.method == "POST":
        f = request.form
        errors, data = [], {}
        data["name"] = f.get("name", "").strip()
        data["author"] = f.get("author", "").strip()
        data["publisher"] = f.get("publisher", "").strip()
        data["isbn"] = f.get("isbn", "").strip() or None
        data["description"] = f.get("description", "").strip()
        data["category_id"] = f.get("category_id", type=int)
        data["price"] = f.get("price", type=float)
        data["mrp"] = f.get("mrp", type=float) or None
        data["stock"] = f.get("stock", type=int)
        if not data["name"] or not data["author"] or not data["publisher"]:
            errors.append("Title, author and publisher are required.")
        if data["price"] is None or data["price"] < 0:
            errors.append("Enter a valid price.")
        if data["stock"] is None or data["stock"] < 0:
            errors.append("Stock must be zero or more.")
        if data["mrp"] and data["price"] is not None and data["mrp"] < data["price"]:
            errors.append("MRP can't be lower than the selling price.")
        if not any(c["id"] == data["category_id"] for c in cats):
            errors.append("Choose a category.")
        image = (book["image"] if book else None)
        try:
            up = _save_upload(request.files.get("cover"))
            if up:
                image = up
            elif f.get("image_url", "").strip():
                image = f["image_url"].strip()
            elif f.get("clear_image") == "1":
                image = None
        except ValueError as e:
            errors.append(str(e))
        data["image"] = image
        if not errors:
            db = get_db()
            try:
                if book:
                    sets = ", ".join(f"{k}=?" for k in data)
                    db.execute(f"UPDATE books SET {sets} WHERE id=?", [*data.values(), book["id"]])
                else:
                    cols = ", ".join(data)
                    db.execute(f"INSERT INTO books ({cols}) VALUES ({','.join('?' * len(data))})", list(data.values()))
                db.commit()
            except sqlite3.IntegrityError:
                errors.append("Another book already uses that ISBN.")
            else:
                flash("Book saved.", "success")
                return redirect(url_for("admin.books"))
        for e in errors:
            flash(e, "error")
        return render_template("admin/book_form.html", book=data, cats=cats, editing=bool(book)), 400
    return render_template("admin/book_form.html", book=book or {}, cats=cats, editing=bool(book))


@bp.route("/books/new", methods=["GET", "POST"])
@admin_required
def book_new():
    return _book_form()


@bp.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
@admin_required
def book_edit(book_id):
    b = query("SELECT * FROM books WHERE id=?", (book_id,), one=True)
    if b is None:
        abort(404)
    return _book_form(b)


@bp.route("/books/<int:book_id>/delete", methods=["POST"])
@admin_required
def book_delete(book_id):
    db = get_db()
    db.execute("DELETE FROM books WHERE id=?", (book_id,))
    db.commit()
    flash("Book deleted. Past orders keep their record of it.", "info")
    return redirect(url_for("admin.books"))


@bp.route("/books/<int:book_id>/stock", methods=["POST"])
@admin_required
def book_stock(book_id):
    stock = request.form.get("stock", type=int)
    if stock is None or stock < 0:
        flash("Enter a valid stock number.", "error")
    else:
        db = get_db()
        db.execute("UPDATE books SET stock=? WHERE id=?", (stock, book_id))
        db.commit()
        flash("Stock updated.", "success")
    return redirect(request.referrer or url_for("admin.books"))


# ------------------------------------------------------------------ orders
@bp.route("/orders")
@admin_required
def orders():
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    where, args = [], []
    if status in ALL_STATUSES:
        where.append("o.status=?")
        args.append(status)
    if q:
        digits = re.sub(r"\D", "", q)
        where.append("(u.fullname LIKE ? OR u.username LIKE ? OR o.id = ?)")
        args += [f"%{q}%", f"%{q}%", int(digits) if digits else -1]
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    rows = query(f"""SELECT o.*, u.fullname, u.username FROM orders o JOIN users u ON u.id=o.user_id
                     {clause} ORDER BY o.id DESC LIMIT 200""", args)
    return render_template("admin/orders.html", orders=rows, statuses=ALL_STATUSES, status=status, q=q)


@bp.route("/orders/<int:order_id>", methods=["GET", "POST"])
@admin_required
def order(order_id):
    o = query("""SELECT o.*, u.fullname, u.email, u.username FROM orders o JOIN users u ON u.id=o.user_id
                 WHERE o.id=?""", (order_id,), one=True)
    if o is None:
        abort(404)
    if request.method == "POST":
        new = request.form.get("status")
        note = request.form.get("note", "").strip()[:200] or None
        if new not in ALL_STATUSES or new == o["status"]:
            flash("Choose a different status.", "error")
        elif o["status"] == "Cancelled":
            flash("A cancelled order can't be reopened.", "error")
        else:
            db = get_db()
            pay = o["payment_status"]
            if new == "Cancelled":
                pay = "Refunded" if pay == "Paid" else "Cancelled"
                restock_order(order_id)
            elif new == "Delivered":
                pay = "Paid"
            db.execute("UPDATE orders SET status=?, payment_status=? WHERE id=?", (new, pay, order_id))
            add_event(order_id, new, note or f"Status set to {new}")
            db.commit()
            flash(f"Order marked {new}.", "success")
        return redirect(url_for("admin.order", order_id=order_id))
    return render_template(
        "admin/order.html", o=o, statuses=ALL_STATUSES,
        items=query("SELECT * FROM order_items WHERE order_id=?", (order_id,)),
        events=query("SELECT * FROM order_events WHERE order_id=? ORDER BY id", (order_id,)))


# ------------------------------------------------------------------ customers
@bp.route("/users")
@admin_required
def users():
    rows = query("""SELECT u.*, COUNT(o.id) orders, COALESCE(SUM(CASE WHEN o.status!='Cancelled' THEN o.total END),0) spent
                    FROM users u LEFT JOIN orders o ON o.user_id=u.id GROUP BY u.id ORDER BY u.id DESC""")
    return render_template("admin/users.html", users=rows)


# ------------------------------------------------------------------ coupons / categories
@bp.route("/coupons", methods=["GET", "POST"])
@admin_required
def coupons():
    if request.method == "POST":
        f = request.form
        code = re.sub(r"[^A-Za-z0-9]", "", f.get("code", "")).upper()
        percent, min_amt = f.get("percent", type=int), f.get("min_amount", type=float) or 0
        max_disc = f.get("max_discount", type=float) or None
        exp = f.get("expires_on") or None
        if not code or not percent or not 1 <= percent <= 90:
            flash("Enter a code and a percentage between 1 and 90.", "error")
        else:
            try:
                db = get_db()
                db.execute("INSERT INTO coupons (code, percent, min_amount, max_discount, expires_on) VALUES (?,?,?,?,?)",
                           (code, percent, min_amt, max_disc, exp))
                db.commit()
                flash(f"Coupon {code} created.", "success")
            except sqlite3.IntegrityError:
                flash("That coupon code already exists.", "error")
        return redirect(url_for("admin.coupons"))
    return render_template("admin/coupons.html", coupons=query("SELECT * FROM coupons ORDER BY id DESC"))


@bp.route("/coupons/<int:cid>/toggle", methods=["POST"])
@admin_required
def coupon_toggle(cid):
    db = get_db()
    db.execute("UPDATE coupons SET active = 1 - active WHERE id=?", (cid,))
    db.commit()
    return redirect(url_for("admin.coupons"))


@bp.route("/coupons/<int:cid>/delete", methods=["POST"])
@admin_required
def coupon_delete(cid):
    db = get_db()
    db.execute("DELETE FROM coupons WHERE id=?", (cid,))
    db.commit()
    return redirect(url_for("admin.coupons"))


@bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        slug = re.sub(r"[^a-z0-9]+", "-", (request.form.get("slug") or name).lower()).strip("-")
        if not name or not slug:
            flash("Enter a category name.", "error")
        else:
            try:
                db = get_db()
                db.execute("INSERT INTO categories (slug, name) VALUES (?,?)", (slug, name))
                db.commit()
                flash("Category added.", "success")
            except sqlite3.IntegrityError:
                flash("That category already exists.", "error")
        return redirect(url_for("admin.categories"))
    return render_template("admin/categories.html", cats=query(
        "SELECT c.*, COUNT(b.id) n FROM categories c LEFT JOIN books b ON b.category_id=c.id GROUP BY c.id ORDER BY c.name"))
