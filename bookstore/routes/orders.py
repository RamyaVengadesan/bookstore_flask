"""Checkout, order history, order tracking, cancellation and printable invoice."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..db import get_db, query
from ..utils import (CANCELLABLE, ORDER_FLOW, add_event, cart_clear, cart_items, compute_totals,
                     login_required, restock_order)
from .auth import validate_address

bp = Blueprint("orders", __name__)

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
    return render_template("order_success.html", o=_get_order(order_id))


@bp.route("/orders")
@login_required
def history():
    orders = query("""SELECT o.*, (SELECT SUM(qty) FROM order_items WHERE order_id=o.id) n_items
                      FROM orders o WHERE user_id=? ORDER BY o.id DESC""", (g.user["id"],))
    previews = {o["id"]: query("""SELECT oi.title, b.image FROM order_items oi LEFT JOIN books b ON b.id=oi.book_id
                                  WHERE oi.order_id=? LIMIT 3""", (o["id"],)) for o in orders}
    return render_template("orders.html", orders=orders, previews=previews)


@bp.route("/orders/<int:order_id>")
@login_required
def detail(order_id):
    o = _get_order(order_id)
    items = query("""SELECT oi.*, b.image FROM order_items oi LEFT JOIN books b ON b.id=oi.book_id
                     WHERE oi.order_id=?""", (order_id,))
    events = query("SELECT * FROM order_events WHERE order_id=? ORDER BY id", (order_id,))
    return render_template("order_detail.html", o=o, items=items, events=events, flow=ORDER_FLOW,
                           can_cancel=o["status"] in CANCELLABLE)


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
