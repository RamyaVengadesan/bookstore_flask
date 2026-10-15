"""Shared helpers: auth decorators, CSRF, cart + pricing logic, formatting."""
import re
import secrets
import smtplib
from email.message import EmailMessage
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, flash, g, jsonify, redirect, request, session, url_for

from .db import execute, get_db, query

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
    return f"{current_app.config['ORDER_PREFIX']}-{int(order_id):06d}"


RETURN_WINDOW_DAYS = 7


def delivery_info(pincode, start=None):
    """Demo delivery estimate from a PIN code (2-5 working days, never on a Sunday)."""
    pin = (pincode or "").strip()
    if not re.fullmatch(r"[1-9]\d{5}", pin):
        return None
    days = 2 + (int(pin[0]) * 7) % 4
    d = (start or date.today()) + timedelta(days=days)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return {"pincode": pin, "days": days, "date": d, "label": d.strftime("%a, %d %b")}


def cover_url(image, isbn, size="M"):
    """Cover for a book: an uploaded/explicit image, else Open Library by ISBN (404s if unknown)."""
    if image:
        return image
    if isbn:
        return f"https://covers.openlibrary.org/b/isbn/{isbn.replace('-', '')}-{size}.jpg?default=false"
    return None


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
    free_above, fee = shipping_rules()
    shipping = 0 if (after >= free_above or subtotal == 0) else fee
    return {
        "subtotal": subtotal, "discount": discount, "coupon": coupon,
        "shipping": shipping, "total": after + shipping,
        "free_ship_gap": max(0, free_above - after) if subtotal else 0,
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


# ---------------------------------------------------------------- email
def send_email(to, subject, body):
    """Send an email. Without MAIL_SERVER configured, the message is printed to the server console
    (and kept in app.config['OUTBOX'] for tests), which is what you want while developing."""
    cfg = current_app.config
    cfg.setdefault("OUTBOX", []).append({"to": to, "subject": subject, "body": body})
    server = cfg.get("MAIL_SERVER")
    if not server:
        current_app.logger.info("EMAIL to %s | %s\n%s", to, subject, body)
        return True
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg.get("MAIL_FROM") or cfg.get("MAIL_USERNAME"), to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(server, cfg.get("MAIL_PORT", 587), timeout=10) as smtp:
            smtp.starttls()
            if cfg.get("MAIL_USERNAME"):
                smtp.login(cfg["MAIL_USERNAME"], cfg.get("MAIL_PASSWORD", ""))
            smtp.send_message(msg)
        return True
    except Exception:                       # never let a mail problem break an order
        current_app.logger.exception("Could not send email to %s", to)
        return False


# ---------------------------------------------------------------- store settings (editable in the admin console)
SETTING_DEFAULTS = {
    "store_name": "", "tagline": "", "announcement": "Use code WELCOME10 for 10% off your first order",
    "free_above": "500", "ship_fee": "40", "low_stock": "5", "support_email": "support@readora.local",
}


def all_settings():
    if "_settings" not in g:
        saved = {r["key"]: r["value"] for r in query("SELECT key, value FROM settings")}
        g._settings = {**SETTING_DEFAULTS, **saved}
    return g._settings


def setting_num(key, fallback):
    try:
        return float(all_settings().get(key))
    except (TypeError, ValueError):
        return fallback


def shipping_rules():
    return setting_num("free_above", 500), setting_num("ship_fee", 40)


def save_settings(values):
    db = get_db()
    for k, v in values.items():
        db.execute("INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
    db.commit()
    g.pop("_settings", None)


def log_admin(action, detail=None):
    """Append to the admin activity log (who did what)."""
    uid = g.user["id"] if g.get("user") else None
    execute("INSERT INTO admin_log (user_id, action, detail) VALUES (?,?,?)", (uid, action, (detail or "")[:300]))


def local_today():
    tz = timezone(timedelta(minutes=current_app.config["TZ_OFFSET_MINUTES"]))
    return datetime.now(timezone.utc).astimezone(tz).date()


def make_reset_token(user_id):
    """Create a one-hour password-reset token (same table the Forgot password page uses)."""
    import hashlib
    token = secrets.token_urlsafe(32)
    exp = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    execute("UPDATE password_resets SET used=1 WHERE user_id=?", (user_id,))
    execute("INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (?,?,?)",
            (user_id, hashlib.sha256(token.encode()).hexdigest(), exp))
    return token
