"""Shopping cart + coupon endpoints (work for guests and logged-in users)."""
from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for

from ..db import query
from ..utils import (MAX_QTY_PER_BOOK, cart_count, cart_get_qty, cart_items, cart_set, compute_totals,
                     money, reply, validate_coupon, wants_json, shipping_rules)

bp = Blueprint("cart", __name__)


def _snapshot(book_id=None):
    """Fresh numbers for the page after any cart change (used by the JS to update in place)."""
    items = cart_items()
    t = compute_totals(items)
    lines = {i["id"]: {"qty": i["qty"], "line_total": money(i["line_total"])} for i in items}
    return {
        "count": cart_count(), "lines": lines,
        "subtotal": money(t["subtotal"]), "discount": money(t["discount"]), "has_discount": t["discount"] > 0,
        "shipping": "FREE" if t["shipping"] == 0 else money(t["shipping"]), "total": money(t["total"]),
        "free_ship_gap": money(t["free_ship_gap"]), "needs_more": t["free_ship_gap"] > 0,
        "empty": not items,
    }


@bp.route("/cart")
def view():
    items = cart_items()
    totals = compute_totals(items)
    return render_template("cart.html", items=items, t=totals, max_qty=MAX_QTY_PER_BOOK,
                           free_above=shipping_rules()[0], ship_fee=shipping_rules()[1],
                           coupons=query("SELECT * FROM coupons WHERE active=1 ORDER BY percent"))


@bp.route("/cart/add/<int:book_id>", methods=["POST"])
def add(book_id):
    book = query("SELECT name, stock FROM books WHERE id=?", (book_id,), one=True)
    if book is None:
        abort(404)
    if book["stock"] <= 0:
        return reply(False, f"Sorry, “{book['name']}” is out of stock.", 409)
    want = request.form.get("qty", 1, type=int) or 1
    have = cart_get_qty(book_id)
    new = cart_set(book_id, have + max(1, want))
    msg = f"Added “{book['name']}” to your cart."
    if new == have:
        msg = f"You already have the maximum available ({new}) in your cart."
    dest = url_for("cart.view") if request.form.get("buy_now") else None
    return reply(new != have, msg, redirect_to=dest, **_snapshot())


@bp.route("/cart/update/<int:book_id>", methods=["POST"])
def update(book_id):
    qty = request.form.get("qty", type=int)
    if qty is None:
        abort(400)
    final = cart_set(book_id, qty)
    msg = "Item removed from cart." if final == 0 else "Cart updated."
    if final < qty:
        msg = f"Only {final} available for this book."
    return reply(True, msg, redirect_to=url_for("cart.view"), **_snapshot())


@bp.route("/cart/remove/<int:book_id>", methods=["POST"])
def remove(book_id):
    cart_set(book_id, 0)
    return reply(True, "Item removed from cart.", redirect_to=url_for("cart.view"), **_snapshot())


@bp.route("/cart/coupon", methods=["POST"])
def apply_coupon():
    code = request.form.get("code", "").strip()
    items = cart_items()
    subtotal = sum(i["line_total"] for i in items if not i["unavailable"])
    if not code:
        return reply(False, "Enter a coupon code.", 400, redirect_to=url_for("cart.view"))
    coupon, err = validate_coupon(code, subtotal)
    if err:
        return reply(False, err, 400, redirect_to=url_for("cart.view"), **_snapshot())
    session["coupon"] = coupon["code"]
    return reply(True, f"Coupon {coupon['code']} applied: {coupon['percent']}% off.",
                 redirect_to=url_for("cart.view"), **_snapshot())


@bp.route("/cart/coupon/remove", methods=["POST"])
def remove_coupon():
    session.pop("coupon", None)
    return reply(True, "Coupon removed.", redirect_to=url_for("cart.view"), **_snapshot())
