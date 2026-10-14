"""Shared helpers: auth decorators, CSRF, cart + pricing logic, formatting."""
import secrets
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, flash, g, jsonify, redirect, request, session, url_for

from .db import execute, get_db, query

FREE_SHIPPING_ABOVE = 500
SHIPPING_FEE = 40
MAX_QTY_PER_BOOK = 10
ORDER_FLOW = ["Pending", "Confirmed", "Shipped", "Out for Delivery", "Delivered"]
CANCELLABLE = ("Pending", "Confirmed")


# ---------------------------------------------------------------- request helpers
def wants_json():
    return request.headers.get("X-Requested-With") == "fetch"


def safe_next(target, fallback="shop.home"):
    """Only allow redirects to local paths (prevents open-redirect)."""
    if target:
        p = urlparse(target)
        if not p.netloc and not p.scheme and target.startswith("/") and not target.startswith("//"):
            return target
    return url_for(fallback)


def reply(ok, message, status=200, redirect_to=None, **extra):
    """Respond with JSON for fetch() calls, flash + redirect for normal forms."""
    if wants_json():
        return jsonify(ok=ok, message=message, **extra), status
    flash(message, "success" if ok else "error")
    return redirect(redirect_to or request.referrer or url_for("shop.home"))


# ---------------------------------------------------------------- CSRF
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
            abort(400, "Invalid or missing CSRF token. Please reload the page and try again.")


# ---------------------------------------------------------------- auth
def load_user():
    uid = session.get("user_id")
    g.user = query("SELECT * FROM users WHERE id = ?", (uid,), one=True) if uid else None
    if uid and g.user is None:
        session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            if wants_json():
                return jsonify(ok=False, message="Please log in first.", login=True), 401
            flash("Please log in to continue.", "info")
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*a, **kw)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*a, **kw):
        if not g.user["is_admin"]:
            abort(403)
        return view(*a, **kw)
    return wrapped


# ---------------------------------------------------------------- formatting
def money(v):
    v = float(v or 0)
    return f"₹{v:,.0f}" if v == int(v) else f"₹{v:,.2f}"


def local_dt(value, fmt="%d %b %Y, %I:%M %p"):
    if not value:
        return ""
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    tz = timezone(timedelta(minutes=current_app.config["TZ_OFFSET_MINUTES"]))
    return dt.astimezone(tz).strftime(fmt)


def order_ref(order_id):
    return f"PU-{int(order_id):06d}"


# ---------------------------------------------------------------- cart
def _guest_cart():
    return session.setdefault("cart", {})


def cart_items():
    """Cart lines as dicts: book fields + qty + line_total (works for guests and users)."""
    if g.user:
        rows = query(
            """SELECT b.*, c.qty FROM cart_items c JOIN books b ON b.id = c.book_id
               WHERE c.user_id = ? ORDER BY b.name""", (g.user["id"],))
    else:
        cart = session.get("cart", {})
        if not cart:
            return []
        ids = [int(i) for i in cart]
        marks = ",".join("?" * len(ids))
        books = {b["id"]: b for b in query(f"SELECT * FROM books WHERE id IN ({marks})", ids)}
        rows = []
        for bid, qty in cart.items():
            b = books.get(int(bid))
            if b:
                rows.append({**dict(b), "qty": qty})
        rows.sort(key=lambda r: r["name"])
    items = []
    for r in rows:
        d = dict(r)
        d["qty"] = max(1, min(d["qty"], d["stock"] or 0, MAX_QTY_PER_BOOK)) if d["stock"] else d["qty"]
        d["line_total"] = d["qty"] * d["price"]
        d["unavailable"] = d["stock"] <= 0
        items.append(d)
    return items


def cart_count():
    if g.user:
        row = query("SELECT COALESCE(SUM(qty),0) n FROM cart_items WHERE user_id=?", (g.user["id"],), one=True)
        return row["n"]
    return sum(session.get("cart", {}).values())


def cart_set(book_id, qty):
    """Set quantity (0 removes). Clamped to stock and per-book limit. Returns final qty."""
    book = query("SELECT stock FROM books WHERE id=?", (book_id,), one=True)
    if book is None:
        abort(404)
    qty = max(0, min(int(qty), book["stock"], MAX_QTY_PER_BOOK))
    if g.user:
        if qty == 0:
            execute("DELETE FROM cart_items WHERE user_id=? AND book_id=?", (g.user["id"], book_id))
        else:
            execute(
                """INSERT INTO cart_items (user_id, book_id, qty) VALUES (?,?,?)
                   ON CONFLICT(user_id, book_id) DO UPDATE SET qty = excluded.qty""",
                (g.user["id"], book_id, qty))
    else:
        cart = _guest_cart()
        if qty == 0:
            cart.pop(str(book_id), None)
        else:
            cart[str(book_id)] = qty
        session.modified = True
    return qty


def cart_get_qty(book_id):
    if g.user:
        r = query("SELECT qty FROM cart_items WHERE user_id=? AND book_id=?", (g.user["id"], book_id), one=True)
        return r["qty"] if r else 0
    return session.get("cart", {}).get(str(book_id), 0)


def cart_clear():
    if g.user:
        execute("DELETE FROM cart_items WHERE user_id=?", (g.user["id"],))
    session.pop("cart", None)
    session.pop("coupon", None)


def merge_guest_cart(user_id):
    """After login: fold the session cart into the saved cart."""
    guest = session.pop("cart", {})
    for bid, qty in guest.items():
        book = query("SELECT stock FROM books WHERE id=?", (int(bid),), one=True)
        if not book or book["stock"] <= 0:
            continue
        existing = query("SELECT qty FROM cart_items WHERE user_id=? AND book_id=?", (user_id, int(bid)), one=True)
        total = min((existing["qty"] if existing else 0) + qty, book["stock"], MAX_QTY_PER_BOOK)
        execute(
            """INSERT INTO cart_items (user_id, book_id, qty) VALUES (?,?,?)
               ON CONFLICT(user_id, book_id) DO UPDATE SET qty = excluded.qty""",
            (user_id, int(bid), total))


# ---------------------------------------------------------------- coupons + totals
def validate_coupon(code, subtotal):
    """Return (coupon_row, error_message)."""
    c = query("SELECT * FROM coupons WHERE code = ?", (code.strip(),), one=True)
    if not c or not c["active"]:
        return None, "That coupon code is not valid."
    if c["expires_on"] and date.fromisoformat(c["expires_on"]) < date.today():
        return None, "That coupon has expired."
    if subtotal < c["min_amount"]:
        return None, f"This coupon needs a cart value of at least {money(c['min_amount'])}."
    return c, None


def compute_totals(items):
    subtotal = sum(i["line_total"] for i in items if not i["unavailable"])
    discount, coupon = 0.0, None
    code = session.get("coupon")
    if code and subtotal:
        coupon, err = validate_coupon(code, subtotal)
        if coupon:
            discount = round(subtotal * coupon["percent"] / 100, 2)
            if coupon["max_discount"]:
                discount = min(discount, coupon["max_discount"])
        else:
            session.pop("coupon", None)
    after = subtotal - discount
    shipping = 0 if (after >= FREE_SHIPPING_ABOVE or subtotal == 0) else SHIPPING_FEE
    return {
        "subtotal": subtotal, "discount": discount, "coupon": coupon,
        "shipping": shipping, "total": after + shipping,
        "free_ship_gap": max(0, FREE_SHIPPING_ABOVE - after) if subtotal else 0,
    }


# ---------------------------------------------------------------- orders
def add_event(order_id, status, note=None):
    get_db().execute("INSERT INTO order_events (order_id, status, note) VALUES (?,?,?)", (order_id, status, note))


def restock_order(order_id):
    db = get_db()
    for it in db.execute("SELECT book_id, qty FROM order_items WHERE order_id=?", (order_id,)).fetchall():
        if it["book_id"]:
            db.execute("UPDATE books SET stock = stock + ?, sold_count = MAX(0, sold_count - ?) WHERE id=?",
                       (it["qty"], it["qty"], it["book_id"]))


def recalc_rating(book_id):
    row = query("SELECT COUNT(*) n, AVG(rating) a FROM reviews WHERE book_id=?", (book_id,), one=True)
    if row["n"]:
        execute("UPDATE books SET rating=?, review_count=? WHERE id=?", (round(row["a"], 1), row["n"], book_id))
    else:
        execute("UPDATE books SET review_count=0 WHERE id=?", (book_id,))
