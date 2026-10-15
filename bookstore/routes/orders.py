"""Checkout, order history, order tracking, cancellation and printable invoice."""
import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from ..db import get_db, query
from ..utils import (CANCELLABLE, RETURN_WINDOW_DAYS, ORDER_FLOW, add_event, cart_clear, cart_items, cart_set,
                     compute_totals, delivery_info, login_required, order_ref, restock_order, send_email)
from .auth import validate_address

bp = Blueprint("orders", __name__)

RETURN_REASONS = ["Damaged or defective", "Wrong item received", "Item not as described",
                  "Ordered by mistake", "Other"]
PAYMENT_METHODS = {
    "cod": "Cash on Delivery",
    "upi": "UPI (demo)",
    "card": "Credit / Debit Card (demo)",
}


@bp.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    items = [i for i in cart_items() if not i["unavailable"]]
    if not items:
        flash("Your cart is empty.", "info")
        return redirect(url_for("cart.view"))
    totals = compute_totals(items)
    addresses = query("SELECT * FROM addresses WHERE user_id=? ORDER BY is_default DESC, id", (g.user["id"],))

    if request.method == "POST":
        method = request.form.get("payment")
        choice = request.form.get("address_id", "new")
        errors = []
        if method not in PAYMENT_METHODS:
            errors.append("Please choose a payment method.")
        addr = None
        if choice != "new":
            addr = query("SELECT * FROM addresses WHERE id=? AND user_id=?", (choice, g.user["id"]), one=True)
            if addr is None:
                errors.append("Please choose a delivery address.")
        else:
            data, addr_errors = validate_address(request.form)
            errors += addr_errors
            addr = data
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("checkout.html", items=items, t=totals, addresses=addresses,
                                   methods=PAYMENT_METHODS, form=request.form), 400

        db = get_db()
        try:
            # Reserve stock atomically: the UPDATE only succeeds if enough copies remain.
            for i in items:
                cur = db.execute("UPDATE books SET stock=stock-?, sold_count=sold_count+? WHERE id=? AND stock>=?",
                                 (i["qty"], i["qty"], i["id"], i["qty"]))
                if cur.rowcount == 0:
                    raise ValueError(f"Sorry, “{i['name']}” no longer has enough stock. Please update your cart.")
            ship_to = ", ".join(p for p in (addr["line1"], addr["line2"], addr["city"], addr["state"], addr["pincode"]) if p)
            paid = "Paid" if method in ("upi", "card") else "Pending"
            cur = db.execute(
                """INSERT INTO orders (user_id, status, payment_method, payment_status, subtotal, discount,
                       shipping_fee, total, coupon_code, ship_name, ship_phone, ship_address)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (g.user["id"], "Pending", PAYMENT_METHODS[method], paid, totals["subtotal"], totals["discount"],
                 totals["shipping"], totals["total"], totals["coupon"]["code"] if totals["coupon"] else None,
                 addr["full_name"], addr["phone"], ship_to))
            oid = cur.lastrowid
            db.executemany("INSERT INTO order_items (order_id, book_id, title, author, price, qty) VALUES (?,?,?,?,?,?)",
                           [(oid, i["id"], i["name"], i["author"], i["price"], i["qty"]) for i in items])
            add_event(oid, "Pending", "Order placed")
            if choice == "new" and request.form.get("save_address"):
                first = db.execute("SELECT 1 FROM addresses WHERE user_id=?", (g.user["id"],)).fetchone() is None
                db.execute("""INSERT INTO addresses (user_id, full_name, phone, line1, line2, city, state, pincode, is_default)
                              VALUES (?,?,?,?,?,?,?,?,?)""",
                           (g.user["id"], addr["full_name"], addr["phone"], addr["line1"], addr["line2"],
                            addr["city"], addr["state"], addr["pincode"], 1 if first else 0))
            db.commit()
        except ValueError as e:
            db.rollback()
            flash(str(e), "error")
            return redirect(url_for("cart.view"))
        cart_clear()
        send_email(g.user["email"], f"Your {current_app.config['STORE_NAME']} order {order_ref(oid)} is confirmed",
                   f"Hi {g.user['fullname'].split()[0]},\n\nThanks for your order. Total: Rs {totals['total']:.0f} "
                   f"({PAYMENT_METHODS[method]}).\nTrack it any time: {url_for('orders.detail', order_id=oid, _external=True)}")
        return redirect(url_for("orders.success", order_id=oid))

    return render_template("checkout.html", items=items, t=totals, addresses=addresses,
                           methods=PAYMENT_METHODS, form={})


def _get_order(order_id):
    o = query("SELECT * FROM orders WHERE id=?", (order_id,), one=True)
    if o is None or (o["user_id"] != g.user["id"] and not g.user["is_admin"]):
        abort(404)
    return o


@bp.route("/orders/<int:order_id>/success")
@login_required
def success(order_id):
    o = _get_order(order_id)
    return render_template("order_success.html", o=o, eta=_order_eta(o))


def _order_eta(o):
    m = re.search(r"\b(\d{6})\s*$", o["ship_address"])
    placed = datetime.strptime(o["created_at"], "%Y-%m-%d %H:%M:%S").date()
    return delivery_info(m.group(1), start=placed) if m else None


def _return_state(o):
    """(existing return row, eligible?) for an order."""
    ret = query("SELECT * FROM returns WHERE order_id=?", (o["id"],), one=True)
    eligible = False
    if o["status"] == "Delivered" and ret is None:
        ev = query("SELECT created_at FROM order_events WHERE order_id=? AND status='Delivered' ORDER BY id DESC",
                   (o["id"],), one=True)
        if ev:
            when = datetime.strptime(ev["created_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            eligible = datetime.now(timezone.utc) - when <= timedelta(days=RETURN_WINDOW_DAYS)
    return ret, eligible


@bp.route("/orders")
@login_required
def history():
    status = request.args.get("status", "all")
    extra = {"active": " AND o.status NOT IN ('Delivered','Cancelled')", "delivered": " AND o.status='Delivered'",
             "cancelled": " AND o.status='Cancelled'"}.get(status, "")
    orders = query("""SELECT o.*, (SELECT SUM(qty) FROM order_items WHERE order_id=o.id) n_items
                      FROM orders o WHERE user_id=?""" + extra + " ORDER BY o.id DESC", (g.user["id"],))
    previews = {o["id"]: query("""SELECT oi.title, b.image, b.isbn FROM order_items oi LEFT JOIN books b ON b.id=oi.book_id
                                  WHERE oi.order_id=? LIMIT 3""", (o["id"],)) for o in orders}
    return render_template("orders.html", orders=orders, previews=previews, status=status)


@bp.route("/orders/<int:order_id>")
@login_required
def detail(order_id):
    o = _get_order(order_id)
    items = query("""SELECT oi.*, b.image, b.isbn FROM order_items oi LEFT JOIN books b ON b.id=oi.book_id
                     WHERE oi.order_id=?""", (order_id,))
    events = query("SELECT * FROM order_events WHERE order_id=? ORDER BY id", (order_id,))
    ret, can_return = _return_state(o)
    return render_template("order_detail.html", o=o, items=items, events=events, flow=ORDER_FLOW,
                           can_cancel=o["status"] in CANCELLABLE, ret=ret, can_return=can_return,
                           eta=_order_eta(o) if o["status"] not in ("Delivered", "Cancelled") else None,
                           return_days=RETURN_WINDOW_DAYS)


@bp.route("/orders/<int:order_id>/invoice")
@login_required
def invoice(order_id):
    o = _get_order(order_id)
    items = query("SELECT * FROM order_items WHERE order_id=?", (order_id,))
    customer = query("SELECT fullname, email FROM users WHERE id=?", (o["user_id"],), one=True)
    return render_template("invoice.html", o=o, items=items, customer=customer)


@bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel(order_id):
    o = _get_order(order_id)
    if o["user_id"] != g.user["id"]:
        abort(403)
    if o["status"] not in CANCELLABLE:
        flash("This order can no longer be cancelled.", "error")
        return redirect(url_for("orders.detail", order_id=order_id))
    db = get_db()
    pay = "Refunded" if o["payment_status"] == "Paid" else "Cancelled"
    db.execute("UPDATE orders SET status='Cancelled', payment_status=? WHERE id=?", (pay, order_id))
    restock_order(order_id)
    add_event(order_id, "Cancelled", "Cancelled by customer")
    db.commit()
    flash("Your order has been cancelled." + (" Your payment will be refunded." if pay == "Refunded" else ""), "success")
    return redirect(url_for("orders.detail", order_id=order_id))


@bp.route("/orders/<int:order_id>/return", methods=["GET", "POST"])
@login_required
def request_return(order_id):
    o = _get_order(order_id)
    if o["user_id"] != g.user["id"]:
        abort(403)
    ret, eligible = _return_state(o)
    if not eligible:
        flash("This order isn't eligible for a return. Returns are accepted within "
              f"{RETURN_WINDOW_DAYS} days of delivery, once per order.", "error")
        return redirect(url_for("orders.detail", order_id=order_id))
    if request.method == "POST":
        reason = request.form.get("reason", "")
        details = request.form.get("details", "").strip()[:1000]
        if reason not in RETURN_REASONS:
            flash("Please choose a reason for the return.", "error")
        else:
            db = get_db()
            db.execute("INSERT INTO returns (order_id, user_id, reason, details) VALUES (?,?,?,?)",
                       (order_id, g.user["id"], reason, details))
            add_event(order_id, "Return requested", reason)
            db.commit()
            flash("Your return request has been sent. We'll update you within two working days.", "success")
            return redirect(url_for("orders.detail", order_id=order_id))
    items = query("SELECT * FROM order_items WHERE order_id=?", (order_id,))
    return render_template("return_form.html", o=o, items=items, reasons=RETURN_REASONS)


@bp.route("/orders/<int:order_id>/reorder", methods=["POST"])
@login_required
def reorder(order_id):
    o = _get_order(order_id)
    added = skipped = 0
    for it in query("SELECT book_id, qty FROM order_items WHERE order_id=?", (o["id"],)):
        stock = query("SELECT stock FROM books WHERE id=?", (it["book_id"],), one=True) if it["book_id"] else None
        if stock and stock["stock"] > 0:
            cart_set(it["book_id"], it["qty"])
            added += 1
        else:
            skipped += 1
    flash(f"Added {added} {'book' if added == 1 else 'books'} to your cart."
          + (f" {skipped} unavailable." if skipped else ""), "success" if added else "error")
    return redirect(url_for("cart.view"))
