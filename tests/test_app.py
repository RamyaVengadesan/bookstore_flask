import re

import pytest

from bookstore import create_app
from bookstore.db import get_db


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "t.sqlite"), "SECRET_KEY": "x",
                      "UPLOAD_FOLDER": str(tmp_path)})
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def token(client, path="/books"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def post(client, url, data=None, path="/books", **kw):
    data = dict(data or {})
    data["_csrf"] = token(client, path)
    return client.post(url, data=data, **kw)


def register(client, username="ramya", pw="secret123"):
    return post(client, "/register", dict(fullname="Ramya V", username=username, email=f"{username}@x.com",
                                           password=pw, confirm=pw), path="/register", follow_redirects=True)


def login(client, u, p):
    return post(client, "/login", {"username": u, "password": p}, follow_redirects=True)


ADDR = dict(full_name="Ramya V", phone="9876543210", line1="12 Main Road", city="Pondicherry",
            state="Puducherry", pincode="605001")


def stock(app, bid):
    with app.app_context():
        return get_db().execute("SELECT stock, sold_count FROM books WHERE id=?", (bid,)).fetchone()


def test_pages_load(client):
    for url in ["/", "/books", "/books?q=network", "/books?category=cse&sort=price_asc&in_stock=1", "/book/1", "/cart", "/login", "/register"]:
        assert client.get(url).status_code == 200, url
    assert client.get("/book/9999").status_code == 404
    assert client.get("/api/search?q=algo").get_json()["results"]


def test_search_and_filters(client):
    html = client.get("/books?q=Tanenbaum").get_data(as_text=True)
    assert "Computer Networks" in html and "Operating System Concepts" not in html
    html = client.get("/books?min_price=700&q=Digital").get_data(as_text=True)
    assert "Digital Signal Processing" in html and "Digital Design" not in html
    assert "No books match" in client.get("/books?q=zzzzzz").get_data(as_text=True)
    # SQL wildcard characters are treated literally
    assert "No books match" in client.get("/books?q=%25").get_data(as_text=True)


def test_csrf_required(client):
    assert client.post("/login", data={"username": "a", "password": "b"}).status_code == 400
    assert client.post("/cart/add/1").status_code == 400


def test_register_validation_and_login(client):
    r = post(client, "/register", dict(fullname="A", username="x", email="bad", password="short", confirm="no"), path="/register")
    assert b"at least 3 characters" in r.data and b"valid email" in r.data
    assert b"Welcome to Readora" in register(client).data
    client.post("/logout", data={"_csrf": token(client)})
    assert b"Invalid username" in login(client, "ramya", "wrongpass1").data
    assert b"Welcome back" in login(client, "ramya", "secret123").data
    # duplicate
    client.post("/logout", data={"_csrf": token(client)})
    assert b"already registered" in register(client).data


def test_open_redirect_blocked(client):
    register(client)
    client.post("/logout", data={"_csrf": token(client)})
    r = post(client, "/login", {"username": "ramya", "password": "secret123", "next": "https://evil.com"})
    assert r.headers["Location"] == "/"


def test_guest_cart_merges_on_login(client):
    register(client)
    client.post("/logout", data={"_csrf": token(client)})
    r = post(client, "/cart/add/1", {"qty": 2}, path="/", headers={"X-Requested-With": "fetch"})
    assert r.get_json()["count"] == 2
    login(client, "ramya", "secret123")
    assert re.search(rb'id="cart-badge" >2<', client.get("/").data)


def test_cart_limits_and_out_of_stock(client, app):
    r = post(client, "/cart/add/8", {"qty": 50}, path="/", headers={"X-Requested-With": "fetch"})
    assert r.get_json()["count"] == 6          # stock of book 8 is 6
    with app.app_context():
        db = get_db(); db.execute("UPDATE books SET stock=0 WHERE id=2"); db.commit()
    r = post(client, "/cart/add/2", path="/", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 409


def test_coupon_rules(client):
    post(client, "/cart/add/1", path="/")            # 550
    r = post(client, "/cart/coupon", {"code": "BOOKS20"}, path="/cart", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 400 and "at least" in r.get_json()["message"]
    r = post(client, "/cart/coupon", {"code": "welcome10"}, path="/cart", headers={"X-Requested-With": "fetch"})
    j = r.get_json()
    assert j["ok"] and j["discount"] == "₹55"
    r = post(client, "/cart/coupon", {"code": "NOPE"}, path="/cart", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 400


def test_checkout_stock_and_cancel(client, app):
    register(client)
    start = stock(app, 1)["stock"]
    post(client, "/cart/add/1", {"qty": 2}, path="/")
    post(client, "/cart/coupon", {"code": "WELCOME10"}, path="/cart")
    # missing address -> error, nothing ordered
    r = post(client, "/checkout", {"payment": "cod", "address_id": "new"}, path="/checkout")
    assert r.status_code == 400 and stock(app, 1)["stock"] == start
    r = post(client, "/checkout", {"payment": "upi", "address_id": "new", "save_address": "1", **ADDR}, path="/checkout")
    assert r.status_code == 302 and "/success" in r.headers["Location"]
    s = stock(app, 1)
    assert s["stock"] == start - 2
    with app.app_context():
        o = get_db().execute("SELECT * FROM orders").fetchone()
        assert o["subtotal"] == 1100 and o["discount"] == 110 and o["shipping_fee"] == 0 and o["total"] == 990
        assert o["payment_status"] == "Paid"
    # cart emptied, address saved
    assert b"Your cart is empty" in client.get("/cart").data
    assert b"Pondicherry" in client.get("/account").data
    # cancel -> restock + refund
    r = post(client, "/orders/1/cancel", path="/orders/1", follow_redirects=True)
    assert b"cancelled" in r.data and stock(app, 1)["stock"] == start
    with app.app_context():
        assert get_db().execute("SELECT payment_status FROM orders").fetchone()[0] == "Refunded"
    # cannot cancel twice
    assert b"no longer be cancelled" in post(client, "/orders/1/cancel", path="/orders/1", follow_redirects=True).data


def test_orders_are_private(client, app):
    register(client)
    post(client, "/cart/add/3", path="/")
    post(client, "/checkout", {"payment": "cod", "address_id": "new", **ADDR}, path="/checkout")
    assert client.get("/orders/1").status_code == 200
    client.post("/logout", data={"_csrf": token(client)})
    register(client, "other")
    assert client.get("/orders/1").status_code == 404
    assert client.get("/orders/1/invoice").status_code == 404


def test_reviews_and_wishlist(client):
    register(client)
    r = post(client, "/book/1/review", {"rating": 3, "title": "ok", "comment": "fine"}, path="/book/1", follow_redirects=True)
    assert b"Thanks" in r.data
    post(client, "/book/1/review", {"rating": 5, "title": "better", "comment": "great"}, path="/book/1")
    html = client.get("/book/1").get_data(as_text=True)
    assert "better" in html and html.count("review-form") >= 1 and "ok</h4>" not in html
    r = post(client, "/wishlist/toggle/4", path="/", headers={"X-Requested-With": "fetch"})
    assert r.get_json()["wished"] is True
    assert b"Database System Concepts" in client.get("/wishlist").data
    r = post(client, "/wishlist/toggle/4", path="/", headers={"X-Requested-With": "fetch"})
    assert r.get_json()["wished"] is False


def test_wishlist_requires_login(client):
    r = post(client, "/wishlist/toggle/1", path="/", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 401


def test_admin_access_and_flow(client, app):
    # normal users and guests are kept out
    assert client.get("/admin/").status_code == 302
    register(client)
    assert client.get("/admin/").status_code == 403
    client.post("/logout", data={"_csrf": token(client)})
    # place an order as a customer first
    login(client, "ramya", "secret123")
    post(client, "/cart/add/5", {"qty": 1}, path="/")
    post(client, "/checkout", {"payment": "cod", "address_id": "new", **ADDR}, path="/checkout")
    client.post("/logout", data={"_csrf": token(client)})
    # admin
    assert b"Welcome back" in login(client, "admin", "admin123").data
    for url in ["/admin/", "/admin/books", "/admin/books/new", "/admin/books/1/edit", "/admin/orders", "/admin/orders/1",
                "/admin/users", "/admin/coupons", "/admin/categories"]:
        assert client.get(url).status_code == 200, url
    r = post(client, "/admin/orders/1", {"status": "Shipped", "note": "Courier X"}, path="/admin/orders/1", follow_redirects=True)
    assert b"marked Shipped" in r.data
    r = post(client, "/admin/orders/1", {"status": "Delivered"}, path="/admin/orders/1", follow_redirects=True)
    with app.app_context():
        assert get_db().execute("SELECT payment_status FROM orders").fetchone()[0] == "Paid"
    # create a book
    r = post(client, "/admin/books/new", dict(name="Thermodynamics", author="Cengel", publisher="McGraw", category_id=1,
                                              price=500, mrp=550, stock=7, description="d"), path="/admin/books/new", follow_redirects=True)
    assert b"Book saved" in r.data and b"Thermodynamics" in client.get("/books?q=thermo").data
    # validation
    r = post(client, "/admin/books/new", dict(name="", author="", publisher="", category_id=1, price=-5, stock=1), path="/admin/books/new")
    assert r.status_code == 400
    # coupon
    r = post(client, "/admin/coupons", dict(code="diwali 15", percent=15, min_amount=0), path="/admin/coupons", follow_redirects=True)
    assert b"DIWALI15" in r.data


def test_catalogue_is_large_and_grouped(client, app):
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT COUNT(*) FROM books").fetchone()[0] >= 140
        groups = {r[0] for r in db.execute("SELECT group_name FROM categories")}
        assert {"Engineering", "Fiction", "Exam Prep", "Kids"} <= groups
        # original books keep their ids
        assert db.execute("SELECT name FROM books WHERE id=3").fetchone()[0] == "Computer Networks"
    html = client.get("/books?category=mech").get_data(as_text=True)
    assert "Engineering Thermodynamics" in html and "Atomic Habits" not in html
    assert "Atomic Habits" in client.get("/books?category=selfhelp").get_data(as_text=True)
    # pagination
    assert "Next" in client.get("/books").get_data(as_text=True)
    assert client.get("/books?page=999").status_code == 200
    # ISBN-based cover URL is used when a book has an ISBN
    assert "covers.openlibrary.org" in client.get("/book/1").get_data(as_text=True)


def test_old_database_is_backed_up_not_lost(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite"
    con = sqlite3.connect(path); con.execute("CREATE TABLE users (id INTEGER)"); con.commit(); con.close()
    app = create_app({"TESTING": True, "DATABASE": str(path), "SECRET_KEY": "x"})
    assert list(tmp_path.glob("old.v0.*.bak")), "old DB should be kept as a backup"
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM books").fetchone()[0] >= 140


# ------------------------------------------------------------------ Phase 2
FETCH = {"X-Requested-With": "fetch"}


def test_home_sections_and_info_pages(client):
    html = client.get("/").get_data(as_text=True)
    for needle in ["Deals of the day", "Trending now", "Popular authors", "Browse by department", "data-carousel", "Back to campus"]:
        assert needle in html, needle
    for slug in ["about", "faq", "shipping", "returns-policy", "privacy", "terms"]:
        assert client.get(f"/info/{slug}").status_code == 200, slug
    assert client.get("/info/nope").status_code == 404
    assert client.get("/contact").status_code == 200
    assert b"<urlset" in client.get("/sitemap.xml").data and b"Disallow: /admin" in client.get("/robots.txt").data


def test_extra_filters(client):
    assert "Atomic Habits" in client.get("/books?author=James+Clear").get_data(as_text=True)
    html = client.get("/books?publisher=Puffin").get_data(as_text=True)
    assert "Matilda" in html and "Atomic Habits" not in html
    assert "Gunahon Ka Devta" in client.get("/books?language=Hindi").get_data(as_text=True)
    assert "Atomic Habits" not in client.get("/books?language=Hindi").get_data(as_text=True)
    assert "Engineering Thermodynamics" in client.get("/books?group=Engineering&q=thermo").get_data(as_text=True)
    assert "No books match" in client.get("/books?group=Fiction&q=thermo").get_data(as_text=True)
    assert client.get("/books?rating=4.8&sort=discount").status_code == 200
    assert client.get("/books?discount=20").status_code == 200
    assert client.get("/deals").status_code == 302


def test_delivery_checker(client):
    j = client.get("/api/delivery?pincode=605001").get_json()
    assert j["ok"] and "by" in j["message"]
    assert client.get("/api/delivery?pincode=12").status_code == 400
    assert client.get("/api/delivery?pincode=012345").status_code == 400
    assert "605001" in client.get("/book/1").get_data(as_text=True)      # remembered for the session


def test_recently_viewed(client):
    client.get("/book/3"); client.get("/book/4")
    html = client.get("/book/5").get_data(as_text=True)
    assert "Recently viewed" in html and "Database System Concepts" in html


def test_helpful_votes(client):
    register(client)
    post(client, "/book/1/review", {"rating": 5, "title": "great", "comment": "x"}, path="/book/1")
    client.post("/logout", data={"_csrf": token(client)})
    register(client, "other")
    r = post(client, "/review/1/helpful", path="/book/1", headers=FETCH)
    assert r.get_json() == {"ok": True, "message": "Thanks for your feedback.", "voted": True, "count": 1}
    r = post(client, "/review/1/helpful", path="/book/1", headers=FETCH)
    assert r.get_json()["count"] == 0
    client.post("/logout", data={"_csrf": token(client)})
    login(client, "ramya", "secret123")
    assert post(client, "/review/1/helpful", path="/book/1", headers=FETCH).status_code == 400   # own review


def test_newsletter_and_contact(client, app):
    r = post(client, "/newsletter", {"email": "a@b.com"}, path="/", headers=FETCH)
    assert r.get_json()["ok"]
    assert "already" in post(client, "/newsletter", {"email": "A@B.com"}, path="/", headers=FETCH).get_json()["message"]
    assert post(client, "/newsletter", {"email": "bad"}, path="/", headers=FETCH).status_code == 400
    r = post(client, "/contact", {"name": "R", "email": "r@x.com", "subject": "x", "body": "short"}, path="/contact")
    assert b"at least a short message" in r.data and b"Please add a subject" in r.data
    r = post(client, "/contact", {"name": "Ramya", "email": "r@x.com", "subject": "Order help",
                                  "body": "Where is my order please?"}, path="/contact", follow_redirects=True)
    assert b"Thanks for getting in touch" in r.data
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1


def test_password_reset_flow(client, app):
    register(client)
    client.post("/logout", data={"_csrf": token(client)})
    r = post(client, "/forgot", {"email": "ramya@x.com"}, path="/forgot")
    assert b"/reset/" in r.data                                # demo mode shows the link
    mail = app.config["OUTBOX"][-1]
    link = re.search(r"http://localhost(/reset/\S+)", mail["body"]).group(1)
    assert client.get(link).status_code == 200
    r = post(client, link, {"password": "weak", "confirm": "weak"}, path="/books")
    assert b"at least 8" in r.data
    r = post(client, link, {"password": "brandnew123", "confirm": "brandnew123"}, path="/books", follow_redirects=True)
    assert b"password has been changed" in r.data
    assert b"Welcome back" in login(client, "ramya", "brandnew123").data
    client.post("/logout", data={"_csrf": token(client)})
    # link is single use; unknown tokens are rejected
    assert client.get(link, follow_redirects=True).request.path == "/forgot"
    assert client.get("/reset/bogus", follow_redirects=True).request.path == "/forgot"
    # unknown email gets the same message and no link
    r = post(client, "/forgot", {"email": "nobody@x.com"}, path="/forgot")
    assert b"If that email is registered" in r.data and b"/reset/" not in r.data


def _place_order(client, book=3):
    post(client, f"/cart/add/{book}", path="/")
    return post(client, "/checkout", {"payment": "cod", "address_id": "new", **ADDR}, path="/checkout")


def test_returns_flow_and_reorder(client, app):
    register(client)
    _place_order(client)
    assert any("confirmed" in m["subject"] for m in app.config["OUTBOX"])
    # not delivered yet -> cannot return
    assert b"isn&#39;t eligible" in client.get("/orders/1/return", follow_redirects=True).data
    with app.app_context():
        db = get_db()
        db.execute("UPDATE orders SET status='Delivered'")
        db.execute("INSERT INTO order_events (order_id, status) VALUES (1, 'Delivered')")
        db.commit()
    assert b"Request a return" in client.get("/orders/1").data
    r = post(client, "/orders/1/return", {"reason": "bogus"}, path="/orders/1")
    assert b"choose a reason" in r.data
    r = post(client, "/orders/1/return", {"reason": "Damaged or defective", "details": "torn"}, path="/orders/1", follow_redirects=True)
    assert b"return request has been sent" in r.data and b"Return requested" in r.data
    assert b"Request a return" not in client.get("/orders/1").data           # only once per order
    # reorder puts the book back in the cart
    post(client, "/orders/1/reorder", path="/orders/1")
    assert b"Computer Networks" in client.get("/cart").data
    # an expired window is refused
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM returns")
        db.execute("UPDATE order_events SET created_at='2020-01-01 00:00:00' WHERE status='Delivered'")
        db.commit()
    assert b"closed" in client.get("/orders/1").data


def test_order_filters_and_eta(client):
    register(client)
    r = _place_order(client)
    assert b"Estimated delivery by" in client.get(r.headers["Location"]).data
    assert b"RD-000001" in client.get("/orders").data
    assert b"RD-000001" in client.get("/orders?status=active").data
    assert b"No orders here" in client.get("/orders?status=delivered").data


# ------------------------------------------------------------------ phase 3: admin console
def _admin(client):
    assert b"Welcome back" in login(client, "admin", "admin123").data


def _order_as_customer(client, book=5, qty=2, user="ramya"):
    register(client, user)
    post(client, f"/cart/add/{book}", {"qty": qty}, path="/")
    post(client, "/checkout", {"payment": "cod", "address_id": "new", **ADDR}, path="/checkout")
    client.post("/logout", data={"_csrf": token(client)})


ADMIN_PAGES = ["/admin/", "/admin/?days=7", "/admin/?days=90", "/admin/reports", "/admin/reports?from=2026-01-01&to=2026-12-31",
               "/admin/books", "/admin/books?show=low", "/admin/books?show=out&q=a&category=1", "/admin/books/import",
               "/admin/books/new", "/admin/books/1/edit", "/admin/orders", "/admin/orders?status=Pending&payment=Pending&from=2020-01-01",
               "/admin/returns", "/admin/reviews", "/admin/users", "/admin/users?sort=spent&q=a", "/admin/messages",
               "/admin/subscribers", "/admin/banners", "/admin/banners/new", "/admin/banners/1/edit", "/admin/coupons",
               "/admin/categories", "/admin/settings", "/admin/activity"]


def test_admin_pages_all_load_and_are_protected(client):
    for url in ADMIN_PAGES:
        assert client.get(url).status_code == 302, url          # guests are sent to log in
    register(client)
    for url in ADMIN_PAGES + ["/admin/export/orders.csv"]:
        assert client.get(url).status_code == 403, url          # customers are refused
    client.post("/logout", data={"_csrf": token(client)})
    _admin(client)
    for url in ADMIN_PAGES:
        assert client.get(url).status_code == 200, url
    assert client.get("/admin/export/nope.csv").status_code == 404


def test_dashboard_and_reports_numbers(client):
    _order_as_customer(client, 5, 2)
    _admin(client)
    html = client.get("/admin/").get_data(as_text=True)
    assert "new order" in html and "Revenue" in html
    rep = client.get("/admin/reports").get_data(as_text=True)
    assert "Best sellers" in rep and "Cash on Delivery" in rep
    # an empty far-past range shows zero orders and no crash
    assert "No sales in this range" in client.get("/admin/reports?from=2001-01-01&to=2001-01-31").get_data(as_text=True)


def test_csv_exports(client, app):
    _order_as_customer(client, 5, 1)
    with app.app_context():
        db = get_db(); db.execute("UPDATE users SET fullname='=HYPERLINK(\"http://x\")' WHERE username='ramya'"); db.commit()
    _admin(client)
    r = client.get("/admin/export/orders.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv" and "attachment" in r.headers["Content-Disposition"]
    text = r.get_data(as_text=True)
    assert "Order,Date" in text and "RD-000001" in text and "'=HYPERLINK" in text      # formula neutralised
    for kind in ("sales", "books", "customers", "returns", "subscribers"):
        assert client.get(f"/admin/export/{kind}.csv").status_code == 200, kind
    assert client.get("/admin/export/books.csv").get_data(as_text=True).count("\n") > 140
    assert b"Exported CSV" in client.get("/admin/activity").data


def _csv_file(text):
    import io
    return (io.BytesIO(text.encode("utf-8")), "books.csv")


def test_bulk_import(client, app):
    _admin(client)
    head = "name,author,publisher,category,isbn,price,mrp,stock,language,format,description\n"
    good = (head + "Imported One,A One,Pub,Computer Science,9781111111111,300,400,5,English,Paperback,d\n"
                   "Imported Two,A Two,Pub,cse,,250,,0,Hindi,Hardcover,\n"
                   "Bad Row,,Pub,Nowhere,,abc,,x,,,\n")
    count = lambda: get_db().execute("SELECT COUNT(*) FROM books").fetchone()[0]
    with app.app_context():
        before = count()
    # dry run saves nothing but reports
    r = post(client, "/admin/books/import", {"dry": "1", "file": _csv_file(good)}, path="/admin/books/import",
             content_type="multipart/form-data")
    assert b"Would add" in r.data and b"unknown department" in r.data and b"invalid price" in r.data
    with app.app_context():
        assert count() == before
    r = post(client, "/admin/books/import", {"file": _csv_file(good)}, path="/admin/books/import",
             content_type="multipart/form-data")
    assert b"Import finished: 2 added" in r.data
    with app.app_context():
        assert count() == before + 2
        row = get_db().execute("SELECT price, mrp, language FROM books WHERE name='Imported One'").fetchone()
        assert (row["price"], row["mrp"]) == (300, 400)
    # same ISBN again -> update, not duplicate
    again = head + "Imported One v2,A One,Pub,Computer Science,9781111111111,350,400,9,English,Paperback,d\n"
    r = post(client, "/admin/books/import", {"file": _csv_file(again)}, path="/admin/books/import", content_type="multipart/form-data")
    assert b"0 added, 1 updated" in r.data
    with app.app_context():
        assert count() == before + 2 and get_db().execute("SELECT price FROM books WHERE isbn='9781111111111'").fetchone()[0] == 350
    # wrong columns and wrong file type are refused
    r = post(client, "/admin/books/import", {"file": _csv_file("title,price\nx,1\n")}, path="/admin/books/import", content_type="multipart/form-data")
    assert b"Missing column" in r.data
    r = post(client, "/admin/books/import", {"file": (__import__("io").BytesIO(b"x"), "a.txt")}, path="/admin/books/import", content_type="multipart/form-data")
    assert b"Upload a .csv" in r.data
    assert client.get("/admin/books/import-template.csv").status_code == 200


def test_bulk_book_actions(client, app):
    _admin(client)
    r = post(client, "/admin/books/bulk", {"action": "delete"}, path="/admin/books", follow_redirects=True)
    assert b"Select at least one" in r.data
    with app.app_context():
        p1 = get_db().execute("SELECT price FROM books WHERE id=1").fetchone()[0]
    post(client, "/admin/books/bulk", {"action": "price_pct", "pct": "10", "ids": ["1", "2"]}, path="/admin/books")
    with app.app_context():
        assert get_db().execute("SELECT price FROM books WHERE id=1").fetchone()[0] == round(p1 * 1.1)
    post(client, "/admin/books/bulk", {"action": "category", "category_id": "2", "ids": ["1"]}, path="/admin/books")
    with app.app_context():
        assert get_db().execute("SELECT category_id FROM books WHERE id=1").fetchone()[0] == 2
    post(client, "/admin/books/bulk", {"action": "delete", "ids": ["1", "2"]}, path="/admin/books")
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM books WHERE id IN (1,2)").fetchone()[0] == 0


def test_order_status_rules_and_bulk(client, app):
    _order_as_customer(client, 5, 1, "user_a")
    _order_as_customer(client, 6, 1, "user_b")
    _admin(client)
    r = post(client, "/admin/orders/bulk", {"status": "Shipped", "ids": ["1", "2"]}, path="/admin/orders", follow_redirects=True)
    assert b"2 order(s) marked Shipped" in r.data
    # cannot go backwards
    r = post(client, "/admin/orders/1", {"status": "Pending"}, path="/admin/orders/1", follow_redirects=True)
    assert b"can&#39;t go back" in r.data
    post(client, "/admin/orders/1", {"status": "Cancelled"}, path="/admin/orders/1")
    r = post(client, "/admin/orders/bulk", {"status": "Delivered", "ids": ["1", "2"]}, path="/admin/orders", follow_redirects=True)
    assert b"1 order(s) marked Delivered" in r.data and b"1 skipped" in r.data       # cancelled one is skipped
    assert b"Order status" in client.get("/admin/activity").data


def _delivered(client, app, user="ramya"):
    _order_as_customer(client, 5, 2, user)
    _admin(client)
    post(client, "/admin/orders/1", {"status": "Delivered"}, path="/admin/orders/1")
    client.post("/logout", data={"_csrf": token(client)})
    login(client, user, "secret123")


def test_returns_workflow(client, app):
    _delivered(client, app)
    start = stock(app, 5)["stock"]
    post(client, "/orders/1/return", {"reason": "Damaged or defective", "details": "torn cover"}, path="/orders/1")
    client.post("/logout", data={"_csrf": token(client)})
    _admin(client)
    assert b"1</b> return request" in client.get("/admin/").data
    page = client.get("/admin/returns").get_data(as_text=True)
    assert "torn cover" in page and "Approve" in page
    # illegal jump and reject-without-note
    assert b"can&#39;t move" in post(client, "/admin/returns/1", {"status": "Refunded"}, path="/admin/returns", follow_redirects=True).data
    assert b"Add a short note" in post(client, "/admin/returns/1", {"status": "Rejected"}, path="/admin/returns", follow_redirects=True).data
    post(client, "/admin/returns/1", {"status": "Approved", "note": "Send it back"}, path="/admin/returns")
    r = post(client, "/admin/returns/1", {"status": "Refunded", "restock": "1"}, path="/admin/returns", follow_redirects=True)
    assert b"refunded" in r.data and b"returned to stock" in r.data
    assert stock(app, 5)["stock"] == start + 2
    with app.app_context():
        assert get_db().execute("SELECT payment_status FROM orders WHERE id=1").fetchone()[0] == "Refunded"
        assert get_db().execute("SELECT status FROM returns").fetchone()[0] == "Refunded"
        assert any("return" in m["subject"].lower() for m in app.config["OUTBOX"])
    # finished returns have no more actions
    assert b"ret-actions" not in client.get("/admin/returns?status=Refunded").data


def test_review_moderation_and_messages(client, app):
    register(client, "reviewer")
    post(client, "/book/1/review", {"rating": 1, "title": "meh", "comment": "bad"}, path="/book/1")
    post(client, "/contact", {"name": "Ann", "email": "a@x.com", "subject": "Hello", "body": "Where is my order?"}, path="/contact")
    post(client, "/newsletter", {"email": "n@x.com"}, path="/", headers={"X-Requested-With": "fetch"})
    client.post("/logout", data={"_csrf": token(client)})
    _admin(client)
    assert b"meh" in client.get("/admin/reviews").data
    post(client, "/admin/reviews/1/delete", path="/admin/reviews")
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0
        assert get_db().execute("SELECT review_count FROM books WHERE id=1").fetchone()[0] == 0
    assert b"Where is my order?" in client.get("/admin/messages?status=New").data
    assert b"unread message" in client.get("/admin/").data
    post(client, "/admin/messages/1/toggle", path="/admin/messages")
    assert b"Where is my order?" not in client.get("/admin/messages?status=New").data
    assert b"n@x.com" in client.get("/admin/subscribers").data
    post(client, "/admin/subscribers/1/delete", path="/admin/subscribers")
    assert b"n@x.com" not in client.get("/admin/subscribers").data
    post(client, "/admin/messages/1/delete", path="/admin/messages")


def test_banners_crud_and_home(client):
    _admin(client)
    r = post(client, "/admin/banners/new", {"title": "", "link": "javascript:alert(1)"}, path="/admin/banners/new")
    assert r.status_code == 400 and b"headline" in r.data and b"must start with" in r.data
    post(client, "/admin/banners/new", {"title": "Diwali Sale", "subtitle": "Big", "link": "/deals", "theme": "teal", "active": "1",
                                        "cta_text": "Go", "category_slug": "cse"}, path="/admin/banners/new")
    assert b"Diwali Sale" in client.get("/").data
    post(client, "/admin/banners/4/toggle", path="/admin/banners")
    assert b"Diwali Sale" not in client.get("/").data
    post(client, "/admin/banners/4/up", path="/admin/banners")
    post(client, "/admin/banners/4/delete", path="/admin/banners")
    assert b"Diwali Sale" not in client.get("/admin/banners").data
    assert client.post("/admin/banners/1/explode", data={"_csrf": token(client)}).status_code == 404


def test_settings_change_the_store(client, app):
    _admin(client)
    r = post(client, "/admin/settings", {"store_name": "Page Turner", "tagline": "Read more", "announcement": "Diwali week!",
                                         "free_above": "300", "ship_fee": "25", "low_stock": "8", "support_email": "bad"},
             path="/admin/settings", follow_redirects=True)
    assert b"valid support email" in r.data
    post(client, "/admin/settings", {"store_name": "Page Turner", "tagline": "Read more", "announcement": "Diwali week!",
                                     "free_above": "300", "ship_fee": "25", "low_stock": "8", "support_email": "a@b.co"}, path="/admin/settings")
    home = client.get("/").get_data(as_text=True)
    assert "Page Turner" in home and "Diwali week!" in home and "Free delivery above ₹300" in home
    r = post(client, "/admin/settings", {"free_above": "-5", "ship_fee": "x", "low_stock": "5"}, path="/admin/settings", follow_redirects=True)
    assert b"must be between" in r.data
    # shipping rules reach the cart: a very high threshold means the new Rs 25 fee applies
    post(client, "/admin/settings", {"free_above": "100000", "ship_fee": "25", "low_stock": "8"}, path="/admin/settings")
    client.post("/logout", data={"_csrf": token(client)})
    post(client, "/cart/add/5", path="/")
    assert "₹25" in client.get("/cart").get_data(as_text=True)


def test_customers_detail_roles_and_reset(client, app):
    _order_as_customer(client, 5, 1, "cust")
    _admin(client)
    assert b"cust" in client.get("/admin/users?q=cust").data
    page = client.get("/admin/users/2").get_data(as_text=True)
    assert "Lifetime spend" in page and "RD-000001" in page
    r = post(client, "/admin/users/2/reset-link", path="/admin/users/2", follow_redirects=True)
    assert b"One-hour reset link" in r.data
    # promote, then self-demotion is blocked
    post(client, "/admin/users/2/role", path="/admin/users/2")
    with app.app_context():
        assert get_db().execute("SELECT is_admin FROM users WHERE id=2").fetchone()[0] == 1
    assert b"can&#39;t change your own" in post(client, "/admin/users/1/role", path="/admin/users/1", follow_redirects=True).data
    assert client.get("/admin/users/999").status_code == 404


def test_departments_admin(client):
    _admin(client)
    post(client, "/admin/categories", {"name": "Poetry", "group_name": "Fiction"}, path="/admin/categories")
    assert b"Poetry" in client.get("/").data
    post(client, "/admin/categories/16/update", {"name": "Verse", "group_name": "Fiction", "sort_order": "99"}, path="/admin/categories")
    assert b"Verse" in client.get("/admin/categories").data
    # departments with books can't be deleted; empty ones can
    assert b"Move or delete the books" in post(client, "/admin/categories/1/delete", path="/admin/categories", follow_redirects=True).data
    post(client, "/admin/categories/16/delete", path="/admin/categories")
    assert b"Verse" not in client.get("/admin/categories").data


def test_v3_database_upgrades_in_place(tmp_path):
    import sqlite3
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "x.sqlite"), "SECRET_KEY": "x"})
    with app.app_context():
        db = get_db()
        db.execute("DROP TABLE settings"); db.execute("DROP TABLE admin_log"); db.execute("PRAGMA user_version = 3")
        db.execute("UPDATE books SET name='MY EDIT' WHERE id=1"); db.commit()
    app2 = create_app({"TESTING": True, "DATABASE": str(tmp_path / "x.sqlite"), "SECRET_KEY": "x"})
    assert not list(tmp_path.glob("*.bak")), "a v3 database should be upgraded without a rebuild"
    with app2.app_context():
        db = get_db()
        assert db.execute("SELECT name FROM books WHERE id=1").fetchone()[0] == "MY EDIT"
        db.execute("SELECT * FROM settings"); db.execute("SELECT * FROM admin_log")
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
