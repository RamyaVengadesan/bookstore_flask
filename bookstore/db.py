"""SQLite helpers + CLI commands (flask init-db / create-admin)."""
import json
import sqlite3
from pathlib import Path

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash

from .seed import BOOK_DESCRIPTIONS, CATEGORIES, COUPONS

HERE = Path(__file__).parent


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid


def init_db(seed=True):
    db = get_db()
    db.executescript((HERE / "schema.sql").read_text())
    if seed:
        seed_db(db)
    db.commit()


def seed_db(db):
    for slug, name in CATEGORIES:
        db.execute("INSERT INTO categories (slug, name) VALUES (?, ?)", (slug, name))
    cat_ids = {r["slug"]: r["id"] for r in db.execute("SELECT id, slug FROM categories")}

    books = json.loads((HERE / "data" / "books.json").read_text())["books"]
    for b in books:
        price = float(b["price"])
        db.execute(
            """INSERT INTO books (id, category_id, name, author, publisher, isbn, price, mrp,
                                  stock, rating, sold_count, description, image)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (b["id"], cat_ids[b["category"]], b["name"], b["author"], b["publisher"],
             b["isbn"], price, round(price * 1.15, -1), b["stock"], b["rating"],
             (b["id"] * 7) % 23 + 3, BOOK_DESCRIPTIONS.get(b["id"], ""), b.get("image")),
        )
    for code, percent, min_amt, max_disc in COUPONS:
        db.execute(
            "INSERT INTO coupons (code, percent, min_amount, max_discount) VALUES (?,?,?,?)",
            (code, percent, min_amt, max_disc),
        )


def create_admin(username, password, email=None, fullname="Store Admin"):
    db = get_db()
    email = email or f"{username}@bookstore.local"
    row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    pw = generate_password_hash(password)
    if row:
        db.execute("UPDATE users SET password=?, is_admin=1 WHERE id=?", (pw, row["id"]))
    else:
        db.execute(
            "INSERT INTO users (fullname, username, email, password, is_admin) VALUES (?,?,?,?,1)",
            (fullname, username, email, pw),
        )
    db.commit()


@click.command("init-db")
@click.option("--admin-user", default="admin", show_default=True)
@click.option("--admin-password", default="admin123", show_default=True)
def init_db_command(admin_user, admin_password):
    """Create tables, load the book catalogue and create an admin account."""
    init_db()
    create_admin(admin_user, admin_password)
    click.echo(f"Database ready. Admin login: {admin_user} / {admin_password}  (change it!)")


@click.command("create-admin")
@click.argument("username")
@click.password_option()
def create_admin_command(username, password):
    """Create (or promote) an admin user."""
    create_admin(username, password)
    click.echo(f"Admin '{username}' saved.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_admin_command)
