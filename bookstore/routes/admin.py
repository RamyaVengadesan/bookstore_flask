"""Admin console: dashboard, reports + CSV, books (incl. bulk import), orders, returns, reviews,
customers, inbox, subscribers, banners, coupons, departments, settings, activity log."""
import csv
import io
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta

from flask import (Blueprint, Response, abort, current_app, flash, redirect, render_template, request,
                   url_for)

from ..db import get_db, query
from ..utils import (ORDER_FLOW, RETURN_WINDOW_DAYS, add_event, admin_required, all_settings, local_today,
                     log_admin, make_reset_token, money, recalc_rating, restock_order, save_settings, setting_num)

bp = Blueprint("admin", __name__, url_prefix="/admin")

ALLOWED_IMG = {"png", "jpg", "jpeg", "webp", "gif"}
ALL_STATUSES = ORDER_FLOW + ["Cancelled"]
RETURN_STATUSES = ["Requested", "Approved", "Refunded", "Rejected"]
RETURN_NEXT = {"Requested": ["Approved", "Rejected"], "Approved": ["Refunded", "Rejected"],
               "Refunded": [], "Rejected": []}
THEMES = ["indigo", "violet", "amber", "teal"]


def one(sql, a=()):
    return query(sql, a, one=True)


def _loc():
    """SQLite date modifier that converts stored UTC times into the store's local time."""
    return f"{current_app.config['TZ_OFFSET_MINUTES']:+d} minutes"


def _page_args(default=50):
    page = max(1, request.args.get("page", 1, type=int))
    return page, default, (page - 1) * default


def _csv(filename, header, rows):
    """CSV download. Text starting with = + - @ is prefixed so spreadsheets never run it as a formula."""
    def safe(v):
        if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + v
        return v
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow([safe(v) for v in r])
    log_admin("Exported CSV", filename)
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


def _range():
    """from/to query args as ISO dates, defaulting to the last 30 local days."""
    today = local_today()
    def parse(v, d):
        try:
            return date.fromisoformat(v)
        except (TypeError, ValueError):
            return d
    end = parse(request.args.get("to"), today)
    start = parse(request.args.get("from"), end - timedelta(days=29))
    if start > end:
        start, end = end, start
    if (end - start).days > 730:
        start = end - timedelta(days=730)
    return start, end


def _sales_by_day(start, end):
    rows = {r["d"]: r for r in query(
        f"""SELECT date(created_at, '{_loc()}') d, SUM(total) revenue, COUNT(*) n FROM orders
            WHERE status!='Cancelled' AND date(created_at, '{_loc()}') BETWEEN ? AND ?
            GROUP BY d""", (start.isoformat(), end.isoformat()))}
    out, d = [], start
    while d <= end:
        r = rows.get(d.isoformat())
        out.append({"date": d.isoformat(), "label": d.strftime("%d %b"), "revenue": r["revenue"] if r else 0,
                    "n": r["n"] if r else 0})
        d += timedelta(days=1)
    return out


def _bar_chart(days, w=760, h=240):
    """Pre-computed SVG geometry so the template needs no chart library."""
    top = max((d["revenue"] for d in days), default=0)
    step = 10 ** max(0, len(str(int(top))) - 1) if top else 1
    ymax = ((top // step) + 1) * step if top else 1000
    pad_l, pad_b, pad_t = 52, 28, 10
    iw, ih = w - pad_l - 8, h - pad_b - pad_t
    n = max(len(days), 1)
    slot = iw / n
    bw = max(2, min(34, slot * 0.7))
    bars = []
    for i, d in enumerate(days):
        bh = ih * d["revenue"] / ymax if ymax else 0
        bars.append({"x": round(pad_l + i * slot + (slot - bw) / 2, 1), "y": round(pad_t + ih - bh, 1),
                     "w": round(bw, 1), "h": round(max(bh, 0), 1),
                     "tip": f"{d['label']}: {money(d['revenue'])} from {d['n']} order{'s' if d['n'] != 1 else ''}"})
    grid = [{"y": round(pad_t + ih - ih * k / 4, 1), "label": _short(ymax * k / 4)} for k in range(5)]
    every = max(1, round(n / 8))
    labels = [{"x": round(pad_l + i * slot + slot / 2, 1), "t": d["label"]} for i, d in enumerate(days) if i % every == 0]
    return {"w": w, "h": h, "bars": bars, "grid": grid, "labels": labels, "base": pad_t + ih, "left": pad_l}


def _short(v):
    return f"₹{v/100000:.1f}L" if v >= 100000 else f"₹{v/1000:.0f}k" if v >= 1000 else f"₹{v:.0f}"


def _pct_change(cur, prev):
    if not prev:
        return None
    return round((cur - prev) * 100 / prev)


def set_order_status(order, new, note=None):
    """Shared by the single-order page and bulk actions. Returns an error message or None."""
    if new not in ALL_STATUSES or new == order["status"]:
        return "Choose a different status."
    if order["status"] == "Cancelled":
        return "A cancelled order can't be reopened."
    if new != "Cancelled" and ORDER_FLOW.index(new) < ORDER_FLOW.index(order["status"]):
        return f"{order_label(order)} can't go back from {order['status']} to {new}."
    db = get_db()
    pay = order["payment_status"]
    if new == "Cancelled":
        pay = "Refunded" if pay == "Paid" else "Cancelled"
        restock_order(order["id"])
    elif new == "Delivered":
        pay = "Paid"
    db.execute("UPDATE orders SET status=?, payment_status=? WHERE id=?", (new, pay, order["id"]))
    add_event(order["id"], new, note or f"Status set to {new}")
    db.commit()
    log_admin("Order status", f"{order_label(order)} -> {new}")
    return None


def order_label(o):
    from ..utils import order_ref
    return order_ref(o["id"])


@bp.route("/")
@admin_required
def dashboard():
    days = request.args.get("days", 30, type=int)
    days = days if days in (7, 30, 90) else 30
    today = local_today()
    start, prev_end = today - timedelta(days=days - 1), today - timedelta(days=days)
    prev_start = prev_end - timedelta(days=days - 1)
    cur = _sales_by_day(start, today)
    revenue, orders_n = sum(d["revenue"] for d in cur), sum(d["n"] for d in cur)
    prev = _sales_by_day(prev_start, prev_end)
    p_rev, p_n = sum(d["revenue"] for d in prev), sum(d["n"] for d in prev)
    s_, e_ = start.isoformat(), today.isoformat()
    by_cat = query(f"""SELECT COALESCE(c.name,'Other') dept, SUM(oi.qty*oi.price) revenue, SUM(oi.qty) units
                       FROM order_items oi JOIN orders o ON o.id=oi.order_id
                       LEFT JOIN books b ON b.id=oi.book_id LEFT JOIN categories c ON c.id=b.category_id
                       WHERE o.status!='Cancelled' AND date(o.created_at,'{_loc()}') BETWEEN ? AND ?
                       GROUP BY dept ORDER BY revenue DESC LIMIT 8""", (s_, e_))
    statuses = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) n FROM orders GROUP BY status")}
    low = setting_num("low_stock", 5)
    return render_template(
        "admin/dashboard.html", days=days, chart=_bar_chart(cur), revenue=revenue, orders_n=orders_n,
        aov=(revenue / orders_n if orders_n else 0), rev_delta=_pct_change(revenue, p_rev), ord_delta=_pct_change(orders_n, p_n),
        new_users=one(f"SELECT COUNT(*) n FROM users WHERE is_admin=0 AND date(created_at,'{_loc()}') BETWEEN ? AND ?", (s_, e_))["n"],
        users=one("SELECT COUNT(*) n FROM users WHERE is_admin=0")["n"],
        by_cat=by_cat, cat_peak=max((c["revenue"] for c in by_cat), default=0) or 1,
        statuses=statuses, status_total=sum(statuses.values()) or 1, flow=ALL_STATUSES,
        queue={"pending": statuses.get("Pending", 0),
               "returns": one("SELECT COUNT(*) n FROM returns WHERE status='Requested'")["n"],
               "messages": one("SELECT COUNT(*) n FROM messages WHERE status='New'")["n"],
               "low": one("SELECT COUNT(*) n FROM books WHERE stock>0 AND stock<=?", (low,))["n"],
               "out": one("SELECT COUNT(*) n FROM books WHERE stock=0")["n"]},
        low_stock=query("SELECT id, name, stock FROM books WHERE stock <= ? ORDER BY stock, name LIMIT 8", (low,)),
        recent=query("""SELECT o.*, u.fullname FROM orders o JOIN users u ON u.id=o.user_id
                        ORDER BY o.id DESC LIMIT 7"""),
        top=query(f"""SELECT oi.title, SUM(oi.qty) sold, SUM(oi.qty*oi.price) revenue FROM order_items oi
                      JOIN orders o ON o.id=oi.order_id WHERE o.status!='Cancelled'
                      AND date(o.created_at,'{_loc()}') BETWEEN ? AND ?
                      GROUP BY oi.title ORDER BY sold DESC LIMIT 6""", (s_, e_)),
        activity=query("""SELECT l.*, u.username FROM admin_log l LEFT JOIN users u ON u.id=l.user_id
                          ORDER BY l.id DESC LIMIT 8"""),
    )


# ------------------------------------------------------------------ reports + exports
@bp.route("/reports")
@admin_required
def reports():
    start, end = _range()
    s_, e_ = start.isoformat(), end.isoformat()
    daily = _sales_by_day(start, end)
    where = f"date(o.created_at,'{_loc()}') BETWEEN ? AND ?"
    live = one(f"""SELECT COUNT(*) n, COALESCE(SUM(total),0) revenue, COALESCE(SUM(discount),0) discounts,
                          COALESCE(SUM(shipping_fee),0) shipping FROM orders o WHERE status!='Cancelled' AND {where}""", (s_, e_))
    cancelled = one(f"SELECT COUNT(*) n FROM orders o WHERE status='Cancelled' AND {where}", (s_, e_))["n"]
    units = one(f"""SELECT COALESCE(SUM(oi.qty),0) n FROM order_items oi JOIN orders o ON o.id=oi.order_id
                    WHERE o.status!='Cancelled' AND {where}""", (s_, e_))["n"]
    returns = one(f"""SELECT COUNT(*) n FROM returns r JOIN orders o ON o.id=r.order_id WHERE {where}""", (s_, e_))["n"]
    by_cat = query(f"""SELECT COALESCE(c.name,'Other') dept, SUM(oi.qty) units, SUM(oi.qty*oi.price) revenue
                       FROM order_items oi JOIN orders o ON o.id=oi.order_id
                       LEFT JOIN books b ON b.id=oi.book_id LEFT JOIN categories c ON c.id=b.category_id
                       WHERE o.status!='Cancelled' AND {where} GROUP BY dept ORDER BY revenue DESC""", (s_, e_))
    by_book = query(f"""SELECT oi.title, oi.author, SUM(oi.qty) units, SUM(oi.qty*oi.price) revenue
                        FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE o.status!='Cancelled' AND {where}
                        GROUP BY oi.title, oi.author ORDER BY units DESC, revenue DESC LIMIT 15""", (s_, e_))
    by_pay = query(f"""SELECT payment_method, COUNT(*) n, SUM(total) revenue FROM orders o
                       WHERE status!='Cancelled' AND {where} GROUP BY payment_method ORDER BY revenue DESC""", (s_, e_))
    by_coupon = query(f"""SELECT coupon_code, COUNT(*) n, SUM(discount) given FROM orders o
                          WHERE status!='Cancelled' AND coupon_code IS NOT NULL AND {where}
                          GROUP BY coupon_code ORDER BY n DESC""", (s_, e_))
    return render_template("admin/reports.html", start=s_, end=e_, daily=daily, chart=_bar_chart(daily), live=live,
                           cancelled=cancelled, units=units, returns=returns, by_cat=by_cat, by_book=by_book,
                           by_pay=by_pay, by_coupon=by_coupon,
                           aov=(live["revenue"] / live["n"] if live["n"] else 0))


@bp.route("/export/<kind>.csv")
@admin_required
def export(kind):
    start, end = _range()
    s_, e_ = start.isoformat(), end.isoformat()
    from ..utils import order_ref
    if kind == "orders":
        rows = query(f"""SELECT o.*, u.fullname, u.email FROM orders o JOIN users u ON u.id=o.user_id
                         WHERE date(o.created_at,'{_loc()}') BETWEEN ? AND ? ORDER BY o.id""", (s_, e_))
        return _csv(f"orders_{s_}_{e_}.csv",
                    ["Order", "Date (UTC)", "Customer", "Email", "Status", "Payment", "Payment status", "Subtotal",
                     "Discount", "Coupon", "Delivery", "Total", "Ship to", "Phone"],
                    [(order_ref(o["id"]), o["created_at"], o["fullname"], o["email"], o["status"], o["payment_method"],
                      o["payment_status"], o["subtotal"], o["discount"], o["coupon_code"] or "", o["shipping_fee"],
                      o["total"], f"{o['ship_name']}, {o['ship_address']}", o["ship_phone"]) for o in rows])
    if kind == "sales":
        rows = query(f"""SELECT o.id, o.created_at, o.status, oi.title, oi.author, oi.qty, oi.price
                         FROM order_items oi JOIN orders o ON o.id=oi.order_id
                         WHERE date(o.created_at,'{_loc()}') BETWEEN ? AND ? ORDER BY o.id""", (s_, e_))
        return _csv(f"sales_lines_{s_}_{e_}.csv", ["Order", "Date (UTC)", "Status", "Title", "Author", "Qty", "Unit price", "Line total"],
                    [(order_ref(r["id"]), r["created_at"], r["status"], r["title"], r["author"], r["qty"], r["price"],
                      r["qty"] * r["price"]) for r in rows])
    if kind == "books":
        rows = query("""SELECT b.*, c.name cname FROM books b JOIN categories c ON c.id=b.category_id ORDER BY b.id""")
        return _csv("books.csv", BOOK_COLS, [(b["name"], b["author"], b["publisher"], b["cname"], b["isbn"] or "", b["price"],
                                               b["mrp"] or "", b["stock"], b["language"], b["format"], b["description"] or "")
                                              for b in rows])
    if kind == "customers":
        rows = query("""SELECT u.*, COUNT(o.id) orders, COALESCE(SUM(CASE WHEN o.status!='Cancelled' THEN o.total END),0) spent
                        FROM users u LEFT JOIN orders o ON o.user_id=u.id WHERE u.is_admin=0 GROUP BY u.id ORDER BY u.id""")
        return _csv("customers.csv", ["Name", "Username", "Email", "Phone", "Joined (UTC)", "Orders", "Spent"],
                    [(u["fullname"], u["username"], u["email"], u["phone"] or "", u["created_at"], u["orders"], u["spent"]) for u in rows])
    if kind == "returns":
        rows = query("SELECT * FROM returns ORDER BY id")
        return _csv("returns.csv", ["Return", "Order", "Reason", "Details", "Status", "Note", "Requested (UTC)"],
                    [(r["id"], order_ref(r["order_id"]), r["reason"], r["details"] or "", r["status"], r["admin_note"] or "",
                      r["created_at"]) for r in rows])
    if kind == "subscribers":
        return _csv("subscribers.csv", ["Email", "Subscribed (UTC)"],
                    [(r["email"], r["created_at"]) for r in query("SELECT * FROM subscribers ORDER BY id")])
    abort(404)


# ------------------------------------------------------------------ books
BOOK_COLS = ["name", "author", "publisher", "category", "isbn", "price", "mrp", "stock", "language", "format", "description"]


@bp.route("/books")
@admin_required
def books():
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", type=int)
    show = request.args.get("show", "")
    low = int(setting_num("low_stock", 5))
    where, args = ["(b.name LIKE ? OR b.author LIKE ? OR b.isbn LIKE ?)"], [f"%{q}%"] * 3
    if cat:
        where.append("b.category_id=?"); args.append(cat)
    if show == "low":
        where.append("b.stock>0 AND b.stock<=?"); args.append(low)
    elif show == "out":
        where.append("b.stock=0")
    clause = " WHERE " + " AND ".join(where)
    total = one(f"SELECT COUNT(*) n FROM books b{clause}", args)["n"]
    page, per, off = _page_args(40)
    pages = max(1, -(-total // per))
    rows = query(f"""SELECT b.*, c.name AS category_name FROM books b JOIN categories c ON c.id=b.category_id
                     {clause} ORDER BY b.id DESC LIMIT ? OFFSET ?""", args + [per, off])
    base = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template("admin/books.html", books=rows, q=q, cat=cat, show=show, total=total, page=page, pages=pages,
                           cats=query("SELECT * FROM categories ORDER BY name"), base=base, low=low)


@bp.route("/books/bulk", methods=["POST"])
@admin_required
def books_bulk():
    ids = [int(i) for i in request.form.getlist("ids") if i.isdigit()]
    action = request.form.get("action", "")
    if not ids:
        flash("Select at least one book first.", "error")
        return redirect(request.referrer or url_for("admin.books"))
    marks, db = ",".join("?" * len(ids)), get_db()
    if action == "delete":
        db.execute(f"DELETE FROM books WHERE id IN ({marks})", ids)
        msg = f"Deleted {len(ids)} book(s)."
    elif action == "category":
        cid = request.form.get("category_id", type=int)
        if not one("SELECT 1 FROM categories WHERE id=?", (cid,)):
            flash("Choose a department.", "error")
            return redirect(request.referrer or url_for("admin.books"))
        db.execute(f"UPDATE books SET category_id=? WHERE id IN ({marks})", [cid, *ids])
        msg = f"Moved {len(ids)} book(s)."
    elif action == "price_pct":
        pct = request.form.get("pct", type=float)
        if pct is None or not -90 <= pct <= 200:
            flash("Enter a percentage between -90 and 200.", "error")
            return redirect(request.referrer or url_for("admin.books"))
        f = 1 + pct / 100
        db.execute(f"UPDATE books SET mrp = CASE WHEN mrp IS NOT NULL THEN ROUND(mrp*?,0) END, price=ROUND(price*?,0) WHERE id IN ({marks})", [f, f, *ids])
        db.execute(f"UPDATE books SET mrp=NULL WHERE id IN ({marks}) AND mrp < price", ids)
        msg = f"Changed prices of {len(ids)} book(s) by {pct:g}%."
    else:
        flash("Choose an action.", "error")
        return redirect(request.referrer or url_for("admin.books"))
    db.commit()
    log_admin("Bulk books", msg)
    flash(msg, "success")
    return redirect(request.referrer or url_for("admin.books"))


@bp.route("/books/import", methods=["GET", "POST"])
@admin_required
def books_import():
    result = None
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename.lower().endswith(".csv"):
            flash("Upload a .csv file (use the template for the right columns).", "error")
        else:
            result = _import_books(f.stream, dry=request.form.get("dry") == "1")
            if result["fatal"]:
                flash(result["fatal"], "error")
            elif not result["dry"]:
                log_admin("Imported books", f"{result['added']} added, {result['updated']} updated, {len(result['errors'])} skipped")
                flash(f"Import finished: {result['added']} added, {result['updated']} updated.", "success")
    return render_template("admin/import.html", result=result, cols=BOOK_COLS)


@bp.route("/books/import-template.csv")
@admin_required
def books_template():
    return _csv("books_template.csv", BOOK_COLS,
                [("Sample Title", "Author Name", "Publisher", "Computer Science", "9780000000001", 499, 599, 20, "English", "Paperback", "One-line description")])


def _import_books(stream, dry):
    out = {"added": 0, "updated": 0, "errors": [], "fatal": None, "dry": dry, "rows": 0}
    try:
        reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig", newline=""))
        reader.fieldnames = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
        missing = [c for c in ("name", "author", "publisher", "category", "price", "stock") if c not in reader.fieldnames]
        if missing:
            out["fatal"] = "Missing column(s): " + ", ".join(missing) + ". Download the template to see the layout."
            return out
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        out["fatal"] = "That file isn't a valid UTF-8 CSV."
        return out
    if len(rows) > 2000:
        out["fatal"] = "Please import at most 2,000 rows at a time."
        return out
    cats = {}
    for c in query("SELECT id, slug, name FROM categories"):
        cats[c["slug"].lower()] = c["id"]; cats[c["name"].lower()] = c["id"]
    db = get_db()
    seen = set()
    for n, r in enumerate(rows, start=2):                       # row 1 is the header
        out["rows"] += 1
        g = lambda k: (r.get(k) or "").strip()
        problems = []
        if not (g("name") and g("author") and g("publisher")):
            problems.append("title, author and publisher are required")
        cid = cats.get(g("category").lower())
        if not cid:
            problems.append(f"unknown department “{g('category')}”")
        try:
            price = float(g("price")); assert price >= 0
        except (ValueError, AssertionError):
            problems.append("invalid price"); price = 0
        mrp = None
        if g("mrp"):
            try:
                mrp = float(g("mrp"))
                if mrp < price:
                    problems.append("MRP is lower than price")
            except ValueError:
                problems.append("invalid MRP")
        try:
            stock = int(float(g("stock"))); assert stock >= 0
        except (ValueError, AssertionError):
            problems.append("invalid stock"); stock = 0
        isbn = re.sub(r"[\s-]", "", g("isbn")) or None
        if isbn and isbn in seen:
            problems.append("duplicate ISBN inside the file")
        if problems:
            out["errors"].append((n, g("name") or "(no title)", "; ".join(problems)))
            continue
        if isbn:
            seen.add(isbn)
        vals = (g("name"), g("author"), g("publisher"), cid, isbn, price, mrp, stock,
                g("language") or "English", g("format") or "Paperback", g("description"))
        existing = db.execute("SELECT id FROM books WHERE isbn=?", (isbn,)).fetchone() if isbn else None
        if existing:
            out["updated"] += 1
            if not dry:
                db.execute("""UPDATE books SET name=?, author=?, publisher=?, category_id=?, isbn=?, price=?, mrp=?, stock=?,
                              language=?, format=?, description=? WHERE id=?""", (*vals, existing["id"]))
        else:
            out["added"] += 1
            if not dry:
                db.execute("""INSERT INTO books (name, author, publisher, category_id, isbn, price, mrp, stock, language, format, description)
                              VALUES (?,?,?,?,?,?,?,?,?,?,?)""", vals)
    if dry:
        db.rollback()
    else:
        db.commit()
    return out


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
        data["language"] = f.get("language", "").strip() or "English"
        data["format"] = f.get("format", "").strip() or "Paperback"
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
                log_admin("Saved book", data["name"])
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
    row = db.execute("SELECT name FROM books WHERE id=?", (book_id,)).fetchone()
    db.execute("DELETE FROM books WHERE id=?", (book_id,))
    db.commit()
    log_admin("Deleted book", row["name"] if row else str(book_id))
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
    pay = request.args.get("payment", "")
    q = request.args.get("q", "").strip()
    d1, d2 = request.args.get("from", ""), request.args.get("to", "")
    where, args = [], []
    if status in ALL_STATUSES:
        where.append("o.status=?"); args.append(status)
    if pay in ("Paid", "Pending", "Refunded", "Cancelled"):
        where.append("o.payment_status=?"); args.append(pay)
    if q:
        digits = re.sub(r"\D", "", q)
        where.append("(u.fullname LIKE ? OR u.username LIKE ? OR o.id = ?)")
        args += [f"%{q}%", f"%{q}%", int(digits) if digits else -1]
    for val, op in ((d1, ">="), (d2, "<=")):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
            where.append(f"date(o.created_at,'{_loc()}') {op} ?"); args.append(val)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = one(f"SELECT COUNT(*) n, COALESCE(SUM(o.total),0) amount FROM orders o JOIN users u ON u.id=o.user_id{clause}", args)
    page, per, off = _page_args(40)
    rows = query(f"""SELECT o.*, u.fullname, u.username FROM orders o JOIN users u ON u.id=o.user_id
                     {clause} ORDER BY o.id DESC LIMIT ? OFFSET ?""", args + [per, off])
    counts = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) n FROM orders GROUP BY status")}
    base = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template("admin/orders.html", orders=rows, statuses=ALL_STATUSES, status=status, q=q, pay=pay, d1=d1, d2=d2,
                           total=total, page=page, pages=max(1, -(-total["n"] // per)), counts=counts, base=base)


@bp.route("/orders/bulk", methods=["POST"])
@admin_required
def orders_bulk():
    ids = [int(i) for i in request.form.getlist("ids") if i.isdigit()]
    new = request.form.get("status", "")
    if not ids or new not in ALL_STATUSES:
        flash("Select orders and a status first.", "error")
    else:
        ok, bad = 0, 0
        for oid in ids:
            o = one("SELECT * FROM orders WHERE id=?", (oid,))
            if o and set_order_status(o, new) is None:
                ok += 1
            else:
                bad += 1
        flash(f"{ok} order(s) marked {new}." + (f" {bad} skipped (can't move to that status)." if bad else ""),
              "success" if ok else "error")
    return redirect(request.referrer or url_for("admin.orders"))


@bp.route("/orders/<int:order_id>", methods=["GET", "POST"])
@admin_required
def order(order_id):
    o = one("""SELECT o.*, u.fullname, u.email, u.username FROM orders o JOIN users u ON u.id=o.user_id
               WHERE o.id=?""", (order_id,))
    if o is None:
        abort(404)
    if request.method == "POST":
        err = set_order_status(o, request.form.get("status"), request.form.get("note", "").strip()[:200] or None)
        flash(err or f"Order marked {request.form.get('status')}.", "error" if err else "success")
        return redirect(url_for("admin.order", order_id=order_id))
    return render_template(
        "admin/order.html", o=o, statuses=ALL_STATUSES,
        items=query("SELECT * FROM order_items WHERE order_id=?", (order_id,)),
        events=query("SELECT * FROM order_events WHERE order_id=? ORDER BY id", (order_id,)),
        ret=one("SELECT * FROM returns WHERE order_id=?", (order_id,)))


# ------------------------------------------------------------------ customers
@bp.route("/users")
@admin_required
def users():
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "new")
    order_by = {"new": "u.id DESC", "spent": "spent DESC", "orders": "orders DESC"}.get(sort, "u.id DESC")
    page, per, off = _page_args(40)
    rows = query(f"""SELECT u.*, COUNT(o.id) orders, COALESCE(SUM(CASE WHEN o.status!='Cancelled' THEN o.total END),0) spent,
                            MAX(o.created_at) last_order
                     FROM users u LEFT JOIN orders o ON o.user_id=u.id
                     WHERE u.fullname LIKE ? OR u.username LIKE ? OR u.email LIKE ?
                     GROUP BY u.id ORDER BY {order_by} LIMIT ? OFFSET ?""", [f"%{q}%"] * 3 + [per, off])
    total = one("SELECT COUNT(*) n FROM users WHERE fullname LIKE ? OR username LIKE ? OR email LIKE ?", [f"%{q}%"] * 3)["n"]
    return render_template("admin/users.html", users=rows, q=q, sort=sort, total=total, page=page,
                           pages=max(1, -(-total // per)), base={k: v for k, v in request.args.items() if k != "page" and v})


@bp.route("/users/<int:uid>")
@admin_required
def user_detail(uid):
    u = one("SELECT * FROM users WHERE id=?", (uid,))
    if u is None:
        abort(404)
    return render_template(
        "admin/user.html", u=u,
        stats=one("""SELECT COUNT(*) orders, COALESCE(SUM(CASE WHEN status!='Cancelled' THEN total END),0) spent,
                            COALESCE(SUM(status='Cancelled'),0) cancelled FROM orders WHERE user_id=?""", (uid,)),
        orders=query("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 20", (uid,)),
        addresses=query("SELECT * FROM addresses WHERE user_id=?", (uid,)),
        reviews=query("""SELECT r.*, b.name FROM reviews r JOIN books b ON b.id=r.book_id WHERE r.user_id=? ORDER BY r.id DESC LIMIT 10""", (uid,)),
        returns=one("SELECT COUNT(*) n FROM returns WHERE user_id=?", (uid,))["n"],
        reset_link=request.args.get("reset"))


@bp.route("/users/<int:uid>/role", methods=["POST"])
@admin_required
def user_role(uid):
    from flask import g
    u = one("SELECT * FROM users WHERE id=?", (uid,))
    if u is None:
        abort(404)
    if u["id"] == g.user["id"]:
        flash("You can't change your own admin access.", "error")
    else:
        make = 0 if u["is_admin"] else 1
        db = get_db()
        db.execute("UPDATE users SET is_admin=? WHERE id=?", (make, uid))
        db.commit()
        log_admin("Admin access", f"{u['username']} {'granted' if make else 'removed'}")
        flash(f"{u['fullname']} is now {'an admin' if make else 'a regular customer'}.", "success")
    return redirect(url_for("admin.user_detail", uid=uid))


@bp.route("/users/<int:uid>/reset-link", methods=["POST"])
@admin_required
def user_reset_link(uid):
    u = one("SELECT * FROM users WHERE id=?", (uid,))
    if u is None:
        abort(404)
    token = make_reset_token(uid)
    log_admin("Password reset link", u["username"])
    return redirect(url_for("admin.user_detail", uid=uid, reset=url_for("auth.reset", token=token)))


# ------------------------------------------------------------------ returns
@bp.route("/returns")
@admin_required
def returns():
    status = request.args.get("status", "")
    where, args = "", []
    if status in RETURN_STATUSES:
        where, args = " WHERE r.status=?", [status]
    rows = query(f"""SELECT r.*, o.total, o.payment_status, u.fullname,
                            (SELECT GROUP_CONCAT(title || ' × ' || qty, ', ') FROM order_items WHERE order_id=r.order_id) items
                     FROM returns r JOIN orders o ON o.id=r.order_id JOIN users u ON u.id=r.user_id{where}
                     ORDER BY (r.status='Requested') DESC, r.id DESC LIMIT 200""", args)
    counts = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) n FROM returns GROUP BY status")}
    return render_template("admin/returns.html", rows=rows, status=status, statuses=RETURN_STATUSES, counts=counts, next=RETURN_NEXT)


@bp.route("/returns/<int:rid>", methods=["POST"])
@admin_required
def return_update(rid):
    r = one("SELECT r.*, o.total, o.user_id ouid FROM returns r JOIN orders o ON o.id=r.order_id WHERE r.id=?", (rid,))
    if r is None:
        abort(404)
    new = request.form.get("status", "")
    note = request.form.get("note", "").strip()[:300] or None
    back = request.referrer or url_for("admin.returns")
    if new not in RETURN_NEXT[r["status"]]:
        flash(f"A {r['status'].lower()} return can't move to {new or 'that status'}.", "error")
        return redirect(back)
    if new == "Rejected" and not note:
        flash("Add a short note so the customer knows why.", "error")
        return redirect(back)
    db = get_db()
    extra = ""
    if new == "Refunded":
        db.execute("UPDATE orders SET payment_status='Refunded' WHERE id=?", (r["order_id"],))
        extra = f" ({money(r['total'])} refunded"
        if request.form.get("restock") == "1":
            restock_order(r["order_id"])
            extra += ", books returned to stock"
        extra += ")"
    db.execute("UPDATE returns SET status=?, admin_note=COALESCE(?, admin_note), updated_at=CURRENT_TIMESTAMP WHERE id=?", (new, note, rid))
    add_event(r["order_id"], f"Return {new.lower()}", (note or "") + extra if (note or extra) else None)
    db.commit()
    log_admin("Return " + new.lower(), f"{order_label({'id': r['order_id']})}")
    from ..utils import send_email
    cust = one("SELECT email, fullname FROM users WHERE id=?", (r["user_id"],))
    if cust:
        send_email(cust["email"], f"Update on your return for {order_label({'id': r['order_id']})}",
                   f"Hi {cust['fullname'].split()[0]},\n\nYour return request is now: {new}.\n" + (f"Note from us: {note}\n" if note else ""))
    flash(f"Return marked {new}{extra}.", "success")
    return redirect(back)


# ------------------------------------------------------------------ reviews
@bp.route("/reviews")
@admin_required
def reviews():
    q = request.args.get("q", "").strip()
    rating = request.args.get("rating", type=int)
    where, args = ["(b.name LIKE ? OR u.fullname LIKE ? OR r.comment LIKE ? OR r.title LIKE ?)"], [f"%{q}%"] * 4
    if rating in (1, 2, 3, 4, 5):
        where.append("r.rating=?"); args.append(rating)
    clause = " WHERE " + " AND ".join(where)
    page, per, off = _page_args(30)
    total = one(f"SELECT COUNT(*) n FROM reviews r JOIN books b ON b.id=r.book_id JOIN users u ON u.id=r.user_id{clause}", args)["n"]
    rows = query(f"""SELECT r.*, b.name book, u.fullname, (SELECT COUNT(*) FROM review_votes v WHERE v.review_id=r.id) votes
                     FROM reviews r JOIN books b ON b.id=r.book_id JOIN users u ON u.id=r.user_id
                     {clause} ORDER BY r.id DESC LIMIT ? OFFSET ?""", args + [per, off])
    return render_template("admin/reviews.html", rows=rows, q=q, rating=rating, total=total, page=page,
                           pages=max(1, -(-total // per)), base={k: v for k, v in request.args.items() if k != "page" and v})


@bp.route("/reviews/<int:rid>/delete", methods=["POST"])
@admin_required
def review_delete(rid):
    r = one("SELECT book_id, title FROM reviews WHERE id=?", (rid,))
    if r:
        db = get_db()
        db.execute("DELETE FROM reviews WHERE id=?", (rid,))
        db.commit()
        recalc_rating(r["book_id"])
        log_admin("Deleted review", f"#{rid} {r['title'] or ''}")
        flash("Review removed and the book's rating recalculated.", "success")
    return redirect(request.referrer or url_for("admin.reviews"))


# ------------------------------------------------------------------ inbox + subscribers
@bp.route("/messages")
@admin_required
def messages():
    status = request.args.get("status", "")
    where, args = "", []
    if status in ("New", "Resolved"):
        where, args = " WHERE status=?", [status]
    rows = query(f"SELECT * FROM messages{where} ORDER BY (status='New') DESC, id DESC LIMIT 200", args)
    counts = {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) n FROM messages GROUP BY status")}
    return render_template("admin/messages.html", rows=rows, status=status, counts=counts)


@bp.route("/messages/<int:mid>/toggle", methods=["POST"])
@admin_required
def message_toggle(mid):
    db = get_db()
    db.execute("UPDATE messages SET status = CASE status WHEN 'New' THEN 'Resolved' ELSE 'New' END WHERE id=?", (mid,))
    db.commit()
    return redirect(request.referrer or url_for("admin.messages"))


@bp.route("/messages/<int:mid>/delete", methods=["POST"])
@admin_required
def message_delete(mid):
    db = get_db()
    db.execute("DELETE FROM messages WHERE id=?", (mid,))
    db.commit()
    flash("Message deleted.", "info")
    return redirect(request.referrer or url_for("admin.messages"))


@bp.route("/subscribers")
@admin_required
def subscribers():
    return render_template("admin/subscribers.html", rows=query("SELECT * FROM subscribers ORDER BY id DESC LIMIT 500"),
                           total=one("SELECT COUNT(*) n FROM subscribers")["n"])


@bp.route("/subscribers/<int:sid>/delete", methods=["POST"])
@admin_required
def subscriber_delete(sid):
    db = get_db()
    db.execute("DELETE FROM subscribers WHERE id=?", (sid,))
    db.commit()
    flash("Subscriber removed.", "info")
    return redirect(url_for("admin.subscribers"))


# ------------------------------------------------------------------ banners
def _banner_data():
    f = request.form
    d = {"title": f.get("title", "").strip()[:120], "subtitle": f.get("subtitle", "").strip()[:220],
         "cta_text": f.get("cta_text", "").strip()[:30] or "Shop now", "link": f.get("link", "").strip(),
         "theme": f.get("theme", "indigo"), "category_slug": f.get("category_slug", "").strip() or None,
         "active": 1 if f.get("active") else 0}
    errors = []
    if not d["title"]:
        errors.append("A banner needs a headline.")
    if not (d["link"].startswith("/") and not d["link"].startswith("//") or re.match(r"^https?://", d["link"])):
        errors.append("The link must start with / (inside the store) or https://.")
    if d["theme"] not in THEMES:
        d["theme"] = "indigo"
    return d, errors


@bp.route("/banners")
@admin_required
def banners():
    return render_template("admin/banners.html", rows=query("SELECT * FROM banners ORDER BY sort_order, id"))


@bp.route("/banners/new", methods=["GET", "POST"])
@bp.route("/banners/<int:bid>/edit", methods=["GET", "POST"])
@admin_required
def banner_form(bid=None):
    b = one("SELECT * FROM banners WHERE id=?", (bid,)) if bid else None
    if bid and b is None:
        abort(404)
    if request.method == "POST":
        d, errors = _banner_data()
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/banner_form.html", b=d, themes=THEMES, editing=bool(bid), cats=query("SELECT slug, name FROM categories ORDER BY name")), 400
        db = get_db()
        if bid:
            db.execute("""UPDATE banners SET title=?, subtitle=?, cta_text=?, link=?, theme=?, category_slug=?, active=? WHERE id=?""",
                       (*d.values(), bid))
        else:
            nxt = one("SELECT COALESCE(MAX(sort_order),-1)+1 n FROM banners")["n"]
            db.execute("""INSERT INTO banners (title, subtitle, cta_text, link, theme, category_slug, active, sort_order)
                          VALUES (?,?,?,?,?,?,?,?)""", (*d.values(), nxt))
        db.commit()
        log_admin("Saved banner", d["title"])
        flash("Banner saved.", "success")
        return redirect(url_for("admin.banners"))
    return render_template("admin/banner_form.html", b=b or {"theme": "indigo", "active": 1, "cta_text": "Shop now", "link": "/books"},
                           themes=THEMES, editing=bool(bid), cats=query("SELECT slug, name FROM categories ORDER BY name"))


@bp.route("/banners/<int:bid>/<action>", methods=["POST"])
@admin_required
def banner_action(bid, action):
    db = get_db()
    rows = [r["id"] for r in db.execute("SELECT id FROM banners ORDER BY sort_order, id")]
    if bid not in rows:
        abort(404)
    if action == "toggle":
        db.execute("UPDATE banners SET active = 1 - active WHERE id=?", (bid,))
    elif action == "delete":
        db.execute("DELETE FROM banners WHERE id=?", (bid,))
        log_admin("Deleted banner", str(bid))
    elif action in ("up", "down"):
        i = rows.index(bid)
        j = i - 1 if action == "up" else i + 1
        if 0 <= j < len(rows):
            rows[i], rows[j] = rows[j], rows[i]
    else:
        abort(404)
    if action in ("up", "down", "delete"):
        rows = [r for r in rows if not (action == "delete" and r == bid)]
        for pos, r in enumerate(rows):
            db.execute("UPDATE banners SET sort_order=? WHERE id=?", (pos, r))
    db.commit()
    return redirect(url_for("admin.banners"))


# ------------------------------------------------------------------ coupons / departments
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
                log_admin("Created coupon", code)
                flash(f"Coupon {code} created.", "success")
            except sqlite3.IntegrityError:
                flash("That coupon code already exists.", "error")
        return redirect(url_for("admin.coupons"))
    return render_template("admin/coupons.html", coupons=query(
        """SELECT c.*, (SELECT COUNT(*) FROM orders o WHERE o.coupon_code=c.code AND o.status!='Cancelled') used
           FROM coupons c ORDER BY id DESC"""))


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
    log_admin("Deleted coupon", str(cid))
    return redirect(url_for("admin.coupons"))


@bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        group = request.form.get("group_name", "").strip()[:40] or "More"
        slug = re.sub(r"[^a-z0-9]+", "-", (request.form.get("slug") or name).lower()).strip("-")
        if not name or not slug:
            flash("Enter a department name.", "error")
        else:
            try:
                db = get_db()
                nxt = one("SELECT COALESCE(MAX(sort_order),0)+1 n FROM categories")["n"]
                db.execute("INSERT INTO categories (slug, name, group_name, sort_order) VALUES (?,?,?,?)", (slug, name, group, nxt))
                db.commit()
                log_admin("Added department", name)
                flash("Department added.", "success")
            except sqlite3.IntegrityError:
                flash("That department already exists.", "error")
        return redirect(url_for("admin.categories"))
    return render_template("admin/categories.html", cats=query(
        """SELECT c.*, COUNT(b.id) n FROM categories c LEFT JOIN books b ON b.category_id=c.id
           GROUP BY c.id ORDER BY c.sort_order, c.name"""),
        groups=[r["group_name"] for r in query("SELECT DISTINCT group_name FROM categories ORDER BY group_name")])


@bp.route("/categories/<int:cid>/update", methods=["POST"])
@admin_required
def category_update(cid):
    name = request.form.get("name", "").strip()
    group = request.form.get("group_name", "").strip()[:40] or "More"
    order = request.form.get("sort_order", type=int)
    if not name or order is None:
        flash("Name and order are required.", "error")
    else:
        db = get_db()
        db.execute("UPDATE categories SET name=?, group_name=?, sort_order=? WHERE id=?", (name, group, order, cid))
        db.commit()
        flash("Department updated.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/categories/<int:cid>/delete", methods=["POST"])
@admin_required
def category_delete(cid):
    if one("SELECT 1 FROM books WHERE category_id=?", (cid,)):
        flash("Move or delete the books in this department first.", "error")
    else:
        db = get_db()
        db.execute("DELETE FROM categories WHERE id=?", (cid,))
        db.commit()
        log_admin("Deleted department", str(cid))
        flash("Department deleted.", "info")
    return redirect(url_for("admin.categories"))


# ------------------------------------------------------------------ settings + activity
@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        f = request.form
        errors, vals = [], {}
        vals["store_name"] = f.get("store_name", "").strip()[:40]
        vals["tagline"] = f.get("tagline", "").strip()[:80]
        vals["announcement"] = f.get("announcement", "").strip()[:140]
        vals["support_email"] = f.get("support_email", "").strip()[:120]
        for key, label, lo, hi in (("free_above", "Free delivery threshold", 0, 100000), ("ship_fee", "Delivery fee", 0, 5000),
                                   ("low_stock", "Low-stock level", 0, 1000)):
            v = f.get(key, type=float)
            if v is None or not lo <= v <= hi:
                errors.append(f"{label} must be between {lo} and {hi}.")
            else:
                vals[key] = f"{v:g}"
        if vals["support_email"] and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", vals["support_email"]):
            errors.append("Enter a valid support email.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            save_settings(vals)
            log_admin("Updated settings")
            flash("Settings saved.", "success")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html", s=all_settings(), cfg=current_app.config)


@bp.route("/activity")
@admin_required
def activity():
    page, per, off = _page_args(50)
    total = one("SELECT COUNT(*) n FROM admin_log")["n"]
    rows = query("""SELECT l.*, u.username FROM admin_log l LEFT JOIN users u ON u.id=l.user_id
                    ORDER BY l.id DESC LIMIT ? OFFSET ?""", (per, off))
    return render_template("admin/activity.html", rows=rows, page=page, pages=max(1, -(-total // per)), base={})
