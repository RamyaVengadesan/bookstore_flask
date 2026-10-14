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
    html = client.get("/books?min_price=700").get_data(as_text=True)
    assert "Digital Signal Processing" in html and "Computer Networks" not in html
    assert "No books match" in client.get("/books?q=zzzzzz").get_data(as_text=True)
    # SQL wildcard characters are treated literally
    assert "No books match" in client.get("/books?q=%25").get_data(as_text=True)


def test_csrf_required(client):
    assert client.post("/login", data={"username": "a", "password": "b"}).status_code == 400
    assert client.post("/cart/add/1").status_code == 400


def test_register_validation_and_login(client):
    r = post(client, "/register", dict(fullname="A", username="x", email="bad", password="short", confirm="no"), path="/register")
    assert b"at least 3 characters" in r.data and b"valid email" in r.data
    assert b"Welcome to PU Book Store" in register(client).data
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
