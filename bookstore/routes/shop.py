"""Public storefront: home, catalogue, book page, search/delivery APIs, reviews, wishlist, info pages."""
import re
from datetime import date
from math import ceil

from flask import (Blueprint, Response, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)

from ..db import execute, get_db, query
from ..utils import delivery_info, login_required, recalc_rating, reply

bp = Blueprint("shop", __name__)

SORTS = {
    "relevance": "b.sold_count DESC, b.rating DESC",
    "price_asc": "b.price ASC",
    "price_desc": "b.price DESC",
    "rating": "b.rating DESC, b.review_count DESC",
    "newest": "b.id DESC",
    "discount": "(b.mrp - b.price) * 1.0 / NULLIF(b.mrp, 0) DESC",
    "name": "b.name COLLATE NOCASE ASC",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BOOK_SELECT = ("SELECT b.*, c.name AS category_name, c.slug AS category_slug, c.group_name "
               "FROM books b JOIN categories c ON c.id=b.category_id")
PAGES = {
    "about": "About us",
    "faq": "Help and FAQ",
    "shipping": "Shipping and delivery",
    "returns-policy": "Returns and refunds",
    "privacy": "Privacy policy",
    "terms": "Terms of use",
}


def _like(term):
    esc = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def _wishlist_ids():
    if not g.user:
        return set()
    return {r["book_id"] for r in query("SELECT book_id FROM wishlist WHERE user_id=?", (g.user["id"],))}


def remember_view(book_id):
    rv = [i for i in session.get("rv", []) if i != book_id]
    session["rv"] = ([book_id] + rv)[:10]


def recently_viewed(exclude=None, limit=6):
    ids = [i for i in session.get("rv", []) if i != exclude][:limit]
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    rows = {b["id"]: b for b in query(f"{BOOK_SELECT} WHERE b.id IN ({marks})", ids)}
    return [rows[i] for i in ids if i in rows]


# ------------------------------------------------------------------ home
@bp.route("/")
def home():
    best = query(f"{BOOK_SELECT} WHERE b.stock>0 ORDER BY b.sold_count DESC LIMIT 8")
    banners = []
    for b in query("SELECT * FROM banners WHERE active=1 ORDER BY sort_order, id"):
        if b["category_slug"]:
            covers = query(f"{BOOK_SELECT} WHERE c.slug=? AND b.stock>0 ORDER BY b.rating DESC, b.sold_count DESC LIMIT 3",
                           (b["category_slug"],))
        else:
            covers = best[:3]
        banners.append({**dict(b), "covers": covers})

    groups = [r["group_name"] for r in query(
        "SELECT group_name FROM categories GROUP BY group_name ORDER BY MIN(sort_order)")]
    trending = {g_: query(f"{BOOK_SELECT} WHERE c.group_name=? AND b.stock>0 ORDER BY b.sold_count DESC LIMIT 4", (g_,))
                for g_ in groups}
    return render_template(
        "home.html", banners=banners,
        deals=query(f"{BOOK_SELECT} WHERE b.stock>0 AND b.mrp>b.price ORDER BY {SORTS['discount']} LIMIT 6"),
        trending=trending,
        top_rated=query(f"{BOOK_SELECT} WHERE b.stock>0 ORDER BY b.rating DESC, b.review_count DESC, b.sold_count DESC LIMIT 6"),
        newest=query(f"{BOOK_SELECT} ORDER BY b.id DESC LIMIT 6"),
        authors=query("""SELECT author, COUNT(*) n, SUM(sold_count) s FROM books WHERE author NOT LIKE '%,%'
                         GROUP BY author ORDER BY s DESC LIMIT 12"""),
        cat_counts=query("""SELECT c.*, COUNT(b.id) n FROM categories c
                            LEFT JOIN books b ON b.category_id=c.id GROUP BY c.id ORDER BY c.sort_order"""),
        recent=recently_viewed(), wished=_wishlist_ids(),
    )


# ------------------------------------------------------------------ catalogue
def _clauses(a, skip=()):
    where, args = [], []
    q = a.get("q", "").strip()
    if q and "q" not in skip:
        where.append("(b.name LIKE ? ESCAPE '\\' OR b.author LIKE ? ESCAPE '\\' OR b.publisher LIKE ? ESCAPE '\\' OR b.isbn LIKE ? ESCAPE '\\')")
        args += [_like(q)] * 4
    for key, col in (("category", "c.slug"), ("group", "c.group_name"), ("publisher", "b.publisher"),
                     ("language", "b.language")):
        if a.get(key) and key not in skip:
            where.append(f"{col} = ?")
            args.append(a[key])
    if a.get("author") and "author" not in skip:
        where.append("b.author LIKE ? ESCAPE '\\'")
        args.append(_like(a["author"]))
    if a.get("in_stock") == "1":
        where.append("b.stock > 0")
    for key, op in (("min_price", ">="), ("max_price", "<=")):
        val = a.get(key, type=float) if hasattr(a, "get") else None
        if val is not None:
            where.append(f"b.price {op} ?")
            args.append(val)
    rating = a.get("rating", type=float)
    if rating:
        where.append("b.rating >= ?")
        args.append(rating)
    disc = a.get("discount", type=float)
    if disc:
        where.append("b.mrp > 0 AND (b.mrp - b.price) * 100.0 / b.mrp >= ?")
        args.append(disc)
    return ((" WHERE " + " AND ".join(where)) if where else ""), args


@bp.route("/books")
def catalogue():
    a = request.args
    sort = a.get("sort", "relevance")
    if sort not in SORTS:
        sort = "relevance"
    page = max(1, a.get("page", 1, type=int))
    per_page = current_app.config["PER_PAGE"]

    clause, args = _clauses(a)
    join = "FROM books b JOIN categories c ON c.id=b.category_id"
    total = query(f"SELECT COUNT(*) n {join}{clause}", args, one=True)["n"]
    pages = max(1, ceil(total / per_page))
    page = min(page, pages)
    books = query(f"{BOOK_SELECT}{clause} ORDER BY {SORTS[sort]} LIMIT ? OFFSET ?",
                  args + [per_page, (page - 1) * per_page])

    # facets: counted with every filter except their own, so options stay useful
    c2, a2 = _clauses(a, skip=("publisher",))
    publishers = query(f"SELECT b.publisher name, COUNT(*) n {join}{c2} GROUP BY b.publisher "
                       f"ORDER BY n DESC, b.publisher LIMIT 12", a2)
    c3, a3 = _clauses(a, skip=("language",))
    languages = query(f"SELECT b.language name, COUNT(*) n {join}{c3} GROUP BY b.language ORDER BY n DESC", a3)
    counts = {r["slug"]: r["n"] for r in query(
        "SELECT c.slug, COUNT(b.id) n FROM categories c LEFT JOIN books b ON b.category_id=c.id GROUP BY c.id")}

    keep = {k: v for k, v in a.items() if k != "page" and v}

    def without(*keys):
        return url_for("shop.catalogue", **{k: v for k, v in keep.items() if k not in keys})

    def facet_url(key, val):
        """Link that switches a filter on (or off again if it is already selected)."""
        base = {k: v for k, v in keep.items() if k != key}
        if keep.get(key) != str(val):
            base[key] = val
        return url_for("shop.catalogue", **base)

    def cat_url(slug):
        base = {k: v for k, v in keep.items() if k not in ("group", "category")}
        return url_for("shop.catalogue", category=slug, **base)

    chips = []
    labels = {"q": "Search", "author": "Author", "publisher": "Publisher", "language": "Language"}
    for k, label in labels.items():
        if keep.get(k):
            chips.append((f"{label}: {keep[k]}", without(k)))
    if keep.get("category"):
        name = next((c["name"] for c in g_categories() if c["slug"] == keep["category"]), keep["category"])
        chips.append((name, without("category")))
    if keep.get("group"):
        chips.append((keep["group"], without("group")))
    if keep.get("in_stock"):
        chips.append(("In stock", without("in_stock")))
    if keep.get("rating"):
        chips.append((f"{keep['rating']}+ stars", without("rating")))
    if keep.get("discount"):
        chips.append((f"{keep['discount']}%+ off", without("discount")))
    if keep.get("min_price") or keep.get("max_price"):
        chips.append((f"Rs {keep.get('min_price', 0)} to {keep.get('max_price') or 'any'}", without("min_price", "max_price")))

    if keep.get("q"):
        title = f"Results for “{keep['q']}”"
    elif keep.get("author"):
        title = f"Books by {keep['author']}"
    elif keep.get("publisher"):
        title = f"Books from {keep['publisher']}"
    elif keep.get("category"):
        title = next((c["name"] for c in g_categories() if c["slug"] == keep["category"]), "Books")
    elif keep.get("group"):
        title = keep["group"]
    elif keep.get("discount"):
        title = "Deals and offers"
    else:
        title = "All books"
    return render_template(
        "catalogue.html", books=books, total=total, page=page, pages=pages, sort=sort, title=title,
        cat=a.get("category", ""), counts=counts, base_args=keep, wished=_wishlist_ids(), chips=chips,
        publishers=publishers, languages=languages, f=a, without=without, facet_url=facet_url, cat_url=cat_url,
    )


def g_categories():
    return query("SELECT * FROM categories")


@bp.route("/deals")
def deals():
    return redirect(url_for("shop.catalogue", discount=15, sort="discount"))


@bp.route("/bestsellers")
def bestsellers():
    return redirect(url_for("shop.catalogue", sort="relevance"))


@bp.route("/new-arrivals")
def new_arrivals():
    return redirect(url_for("shop.catalogue", sort="newest"))


# ------------------------------------------------------------------ book page
@bp.route("/book/<int:book_id>")
def book(book_id):
    b = query(f"{BOOK_SELECT} WHERE b.id=?", (book_id,), one=True)
    if b is None:
        abort(404)
    uid = g.user["id"] if g.user else 0
    reviews = query("""SELECT r.*, u.fullname,
                              (SELECT COUNT(*) FROM review_votes v WHERE v.review_id=r.id) AS helpful,
                              EXISTS(SELECT 1 FROM review_votes v WHERE v.review_id=r.id AND v.user_id=?) AS voted
                       FROM reviews r JOIN users u ON u.id=r.user_id
                       WHERE r.book_id=? ORDER BY helpful DESC, r.created_at DESC""", (uid, book_id))
    dist = {i: 0 for i in range(1, 6)}
    for r in reviews:
        dist[r["rating"]] += 1
    my_review, purchased = None, False
    if g.user:
        my_review = query("SELECT * FROM reviews WHERE user_id=? AND book_id=?", (uid, book_id), one=True)
        purchased = query("""SELECT 1 FROM order_items oi JOIN orders o ON o.id=oi.order_id
                             WHERE o.user_id=? AND oi.book_id=? AND o.status!='Cancelled' LIMIT 1""",
                          (uid, book_id), one=True) is not None
    related = query(f"{BOOK_SELECT} WHERE b.category_id=? AND b.id!=? ORDER BY b.rating DESC, b.sold_count DESC LIMIT 6",
                    (b["category_id"], book_id))
    also = query(f"""{BOOK_SELECT} JOIN (SELECT oi2.book_id bid, COUNT(*) n FROM order_items oi
                                          JOIN order_items oi2 ON oi2.order_id=oi.order_id AND oi2.book_id!=oi.book_id
                                          WHERE oi.book_id=? GROUP BY oi2.book_id) x ON x.bid=b.id
                     ORDER BY x.n DESC LIMIT 6""", (book_id,))
    verified_ids = {r["user_id"] for r in query(
        """SELECT DISTINCT o.user_id FROM orders o JOIN order_items oi ON oi.order_id=o.id
           WHERE oi.book_id=? AND o.status!='Cancelled'""", (book_id,))}
    eta = delivery_info(session.get("pincode"))
    offers = query("SELECT * FROM coupons WHERE active=1 AND (expires_on IS NULL OR expires_on >= ?) ORDER BY percent",
                   (date.today().isoformat(),))
    recent = recently_viewed(exclude=book_id)
    remember_view(book_id)
    return render_template("book.html", b=b, reviews=reviews, dist=dist, my_review=my_review,
                           purchased=purchased, related=related, also=also, wished=_wishlist_ids(),
                           verified_ids=verified_ids, eta=eta, offers=offers, recent=recent)


@bp.route("/book/<int:book_id>/review", methods=["POST"])
@login_required
def review(book_id):
    if query("SELECT 1 FROM books WHERE id=?", (book_id,), one=True) is None:
        abort(404)
    rating = request.form.get("rating", type=int)
    title = request.form.get("title", "").strip()[:100]
    comment = request.form.get("comment", "").strip()[:2000]
    if rating not in (1, 2, 3, 4, 5):
        flash("Please choose a star rating from 1 to 5.", "error")
        return redirect(url_for("shop.book", book_id=book_id) + "#reviews")
    execute(
        """INSERT INTO reviews (user_id, book_id, rating, title, comment) VALUES (?,?,?,?,?)
           ON CONFLICT(user_id, book_id) DO UPDATE SET rating=excluded.rating, title=excluded.title,
               comment=excluded.comment, created_at=CURRENT_TIMESTAMP""",
        (g.user["id"], book_id, rating, title, comment))
    recalc_rating(book_id)
    flash("Thanks! Your review has been saved.", "success")
    return redirect(url_for("shop.book", book_id=book_id) + "#reviews")


@bp.route("/book/<int:book_id>/review/delete", methods=["POST"])
@login_required
def delete_review(book_id):
    execute("DELETE FROM reviews WHERE user_id=? AND book_id=?", (g.user["id"], book_id))
    recalc_rating(book_id)
    flash("Your review was removed.", "info")
    return redirect(url_for("shop.book", book_id=book_id) + "#reviews")


@bp.route("/review/<int:review_id>/helpful", methods=["POST"])
@login_required
def review_helpful(review_id):
    r = query("SELECT user_id FROM reviews WHERE id=?", (review_id,), one=True)
    if r is None:
        abort(404)
    if r["user_id"] == g.user["id"]:
        return reply(False, "You can't vote on your own review.", 400)
    had = query("SELECT 1 FROM review_votes WHERE user_id=? AND review_id=?", (g.user["id"], review_id), one=True)
    if had:
        execute("DELETE FROM review_votes WHERE user_id=? AND review_id=?", (g.user["id"], review_id))
    else:
        execute("INSERT INTO review_votes (user_id, review_id) VALUES (?,?)", (g.user["id"], review_id))
    n = query("SELECT COUNT(*) n FROM review_votes WHERE review_id=?", (review_id,), one=True)["n"]
    return reply(True, "Thanks for your feedback.", voted=not had, count=n)


# ------------------------------------------------------------------ APIs
@bp.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify(results=[])
    rows = query("""SELECT id, name, author, price, image, isbn FROM books
                    WHERE name LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\' OR isbn LIKE ? ESCAPE '\\'
                    ORDER BY sold_count DESC LIMIT 6""", [_like(q)] * 3)
    return jsonify(results=[{**dict(r), "url": url_for("shop.book", book_id=r["id"])} for r in rows])


@bp.route("/api/delivery")
def api_delivery():
    info = delivery_info(request.args.get("pincode"))
    if not info:
        return jsonify(ok=False, message="Enter a valid 6-digit PIN code."), 400
    session["pincode"] = info["pincode"]
    return jsonify(ok=True, label=info["label"], days=info["days"],
                   message=f"Delivery to {info['pincode']} by {info['label']}. Cash on Delivery available.")


# ------------------------------------------------------------------ wishlist
@bp.route("/wishlist")
@login_required
def wishlist():
    books = query(f"""{BOOK_SELECT} JOIN wishlist w ON w.book_id=b.id AND w.user_id=?
                      ORDER BY w.created_at DESC""", (g.user["id"],))
    return render_template("wishlist.html", books=books, wished={b["id"] for b in books})


@bp.route("/wishlist/toggle/<int:book_id>", methods=["POST"])
@login_required
def wishlist_toggle(book_id):
    if query("SELECT 1 FROM books WHERE id=?", (book_id,), one=True) is None:
        abort(404)
    exists = query("SELECT 1 FROM wishlist WHERE user_id=? AND book_id=?", (g.user["id"], book_id), one=True)
    if exists:
        execute("DELETE FROM wishlist WHERE user_id=? AND book_id=?", (g.user["id"], book_id))
        return reply(True, "Removed from your wishlist.", wished=False)
    execute("INSERT INTO wishlist (user_id, book_id) VALUES (?,?)", (g.user["id"], book_id))
    return reply(True, "Saved to your wishlist.", wished=True)


# ------------------------------------------------------------------ newsletter, contact, info pages
@bp.route("/newsletter", methods=["POST"])
def newsletter():
    email = request.form.get("email", "").strip().lower()
    if not EMAIL_RE.match(email):
        return reply(False, "Enter a valid email address.", 400)
    db = get_db()
    cur = db.execute("INSERT OR IGNORE INTO subscribers (email) VALUES (?)", (email,))
    db.commit()
    return reply(True, "You're subscribed. Watch your inbox for new arrivals and offers."
                 if cur.rowcount else "You're already subscribed.")


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    form = {}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in ("name", "email", "subject", "body")}
        errors = []
        if len(form["name"]) < 2:
            errors.append("Please enter your name.")
        if not EMAIL_RE.match(form["email"]):
            errors.append("Please enter a valid email address.")
        if len(form["subject"]) < 3:
            errors.append("Please add a subject.")
        if len(form["body"]) < 10:
            errors.append("Please write at least a short message so we can help.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            execute("INSERT INTO messages (name, email, subject, body) VALUES (?,?,?,?)",
                    (form["name"], form["email"], form["subject"][:150], form["body"][:3000]))
            flash("Thanks for getting in touch. We'll reply within one working day.", "success")
            return redirect(url_for("shop.contact"))
    elif g.user:
        form = {"name": g.user["fullname"], "email": g.user["email"]}
    return render_template("pages/contact.html", form=form)


@bp.route("/info/<slug>")
def info(slug):
    if slug not in PAGES:
        abort(404)
    return render_template(f"pages/{slug}.html", title=PAGES[slug])


@bp.route("/robots.txt")
def robots():
    return Response(f"User-agent: *\nDisallow: /admin\nDisallow: /cart\nDisallow: /checkout\n"
                    f"Sitemap: {url_for('shop.sitemap', _external=True)}\n", mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap():
    urls = [url_for("shop.home", _external=True), url_for("shop.catalogue", _external=True)]
    urls += [url_for("shop.catalogue", category=c["slug"], _external=True) for c in g_categories()]
    urls += [url_for("shop.info", slug=s, _external=True) for s in PAGES]
    urls += [url_for("shop.book", book_id=r["id"], _external=True) for r in query("SELECT id FROM books")]
    body = "".join(f"<url><loc>{u.replace('&', '&amp;')}</loc></url>" for u in urls)
    return Response('<?xml version="1.0" encoding="UTF-8"?>'
                    f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
                    mimetype="application/xml")
