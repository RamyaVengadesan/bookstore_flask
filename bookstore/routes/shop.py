"""Public storefront: home, catalogue, book page, search API, reviews, wishlist."""
from math import ceil

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, url_for

from ..db import execute, query
from ..utils import login_required, recalc_rating, reply

bp = Blueprint("shop", __name__)

SORTS = {
    "relevance": "b.sold_count DESC, b.rating DESC",
    "price_asc": "b.price ASC",
    "price_desc": "b.price DESC",
    "rating": "b.rating DESC, b.review_count DESC",
    "newest": "b.id DESC",
    "name": "b.name COLLATE NOCASE ASC",
}


def _like(term):
    esc = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def _wishlist_ids():
    if not g.user:
        return set()
    return {r["book_id"] for r in query("SELECT book_id FROM wishlist WHERE user_id=?", (g.user["id"],))}


BOOK_SELECT = "SELECT b.*, c.name AS category_name, c.slug AS category_slug FROM books b JOIN categories c ON c.id=b.category_id"


@bp.route("/")
def home():
    return render_template(
        "home.html",
        bestsellers=query(f"{BOOK_SELECT} WHERE b.stock>0 ORDER BY b.sold_count DESC LIMIT 4"),
        top_rated=query(f"{BOOK_SELECT} WHERE b.stock>0 ORDER BY b.rating DESC, b.review_count DESC LIMIT 4"),
        newest=query(f"{BOOK_SELECT} ORDER BY b.id DESC LIMIT 4"),
        cat_counts=query("""SELECT c.*, COUNT(b.id) n FROM categories c
                            LEFT JOIN books b ON b.category_id=c.id GROUP BY c.id ORDER BY c.name"""),
        stats=query("SELECT COUNT(*) books, COALESCE(SUM(stock),0) copies FROM books", one=True),
        wished=_wishlist_ids(),
    )


@bp.route("/books")
def catalogue():
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", "")
    sort = request.args.get("sort", "relevance")
    if sort not in SORTS:
        sort = "relevance"
    in_stock = request.args.get("in_stock") == "1"
    min_p = request.args.get("min_price", type=float)
    max_p = request.args.get("max_price", type=float)
    page = max(1, request.args.get("page", 1, type=int))
    per_page = current_app.config["PER_PAGE"]

    where, args = [], []
    if q:
        where.append("(b.name LIKE ? ESCAPE '\\' OR b.author LIKE ? ESCAPE '\\' OR b.publisher LIKE ? ESCAPE '\\' OR b.isbn LIKE ? ESCAPE '\\')")
        args += [_like(q)] * 4
    if cat:
        where.append("c.slug = ?")
        args.append(cat)
    if in_stock:
        where.append("b.stock > 0")
    if min_p is not None:
        where.append("b.price >= ?")
        args.append(min_p)
    if max_p is not None:
        where.append("b.price <= ?")
        args.append(max_p)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total = query(f"SELECT COUNT(*) n FROM books b JOIN categories c ON c.id=b.category_id{clause}", args, one=True)["n"]
    pages = max(1, ceil(total / per_page))
    page = min(page, pages)
    books = query(f"{BOOK_SELECT}{clause} ORDER BY {SORTS[sort]} LIMIT ? OFFSET ?",
                  args + [per_page, (page - 1) * per_page])

    counts = {r["slug"]: r["n"] for r in query(
        "SELECT c.slug, COUNT(b.id) n FROM categories c LEFT JOIN books b ON b.category_id=c.id GROUP BY c.id")}
    # query string (minus page) for pagination links
    base_args = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template(
        "catalogue.html", books=books, total=total, page=page, pages=pages, q=q, cat=cat, sort=sort,
        in_stock=in_stock, min_price=request.args.get("min_price", ""), max_price=request.args.get("max_price", ""),
        counts=counts, base_args=base_args, wished=_wishlist_ids(),
    )


@bp.route("/book/<int:book_id>")
def book(book_id):
    b = query(f"{BOOK_SELECT} WHERE b.id=?", (book_id,), one=True)
    if b is None:
        abort(404)
    reviews = query("""SELECT r.*, u.fullname FROM reviews r JOIN users u ON u.id=r.user_id
                       WHERE r.book_id=? ORDER BY r.created_at DESC""", (book_id,))
    dist = {i: 0 for i in range(1, 6)}
    for r in reviews:
        dist[r["rating"]] += 1
    my_review, purchased = None, False
    if g.user:
        my_review = query("SELECT * FROM reviews WHERE user_id=? AND book_id=?", (g.user["id"], book_id), one=True)
        purchased = query("""SELECT 1 FROM order_items oi JOIN orders o ON o.id=oi.order_id
                             WHERE o.user_id=? AND oi.book_id=? AND o.status!='Cancelled' LIMIT 1""",
                          (g.user["id"], book_id), one=True) is not None
    related = query(f"{BOOK_SELECT} WHERE b.category_id=? AND b.id!=? ORDER BY b.rating DESC LIMIT 4",
                    (b["category_id"], book_id))
    verified_ids = {r["user_id"] for r in query(
        """SELECT DISTINCT o.user_id FROM orders o JOIN order_items oi ON oi.order_id=o.id
           WHERE oi.book_id=? AND o.status!='Cancelled'""", (book_id,))}
    return render_template("book.html", b=b, reviews=reviews, dist=dist, my_review=my_review,
                           purchased=purchased, related=related, wished=_wishlist_ids(),
                           verified_ids=verified_ids)


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


@bp.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify(results=[])
    rows = query("""SELECT id, name, author, price, image FROM books
                    WHERE name LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\' OR isbn LIKE ? ESCAPE '\\'
                    ORDER BY sold_count DESC LIMIT 6""", [_like(q)] * 3)
    return jsonify(results=[{**dict(r), "url": url_for("shop.book", book_id=r["id"])} for r in rows])


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
