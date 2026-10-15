"""SQLite helpers + CLI commands (flask init-db / create-admin)."""
import json
import math
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash

from .catalog import (BANNERS, CATEGORIES, COUPONS, NEW_BOOKS, ORIGINAL_CATEGORY_SLUG,
                      ORIGINAL_DESCRIPTIONS)

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


SCHEMA_VERSION = 4

# Additive upgrades keep existing data (v3 -> v4 only adds tables).
MIGRATIONS = {
    4: """
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS admin_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        action TEXT NOT NULL, detail TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """,
}


def init_db(seed=True):
    db = get_db()
    db.executescript((HERE / "schema.sql").read_text())
    if seed:
        seed_db(db)
    db.commit()


def ensure_db(app):
    """Create the database on first run. If an older schema is found, keep a backup and rebuild."""
    path = Path(app.config["DATABASE"])
    if path.exists():
        con = sqlite3.connect(path)
        version = con.execute("PRAGMA user_version").fetchone()[0]
        con.close()
        if version >= SCHEMA_VERSION:
            return
        if version == 3:     # same layout plus new tables: upgrade in place and keep all data
            con = sqlite3.connect(path)
            for v in sorted(MIGRATIONS):
                if v > version:
                    con.executescript(MIGRATIONS[v])
            con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            con.commit(); con.close()
            return
        backup = path.with_suffix(f".v{version}.{datetime.now():%Y%m%d%H%M%S}.bak")
        path.rename(backup)
        print(f"* Database schema updated. Your old data was saved to {backup.name}")
    with app.app_context():
        init_db()
        create_admin("admin", os.environ.get("ADMIN_PASSWORD", "admin123"))


def _mrp(book_id, price):
    """Demo list price: 10-25% above the selling price, rounded up to the next Rs 10."""
    pct = 10 + (book_id * 7) % 16
    return math.ceil(price / (1 - pct / 100) / 10) * 10


def seed_db(db):
    for slug, name, group, order in CATEGORIES:
        db.execute("INSERT INTO categories (slug, name, group_name, sort_order) VALUES (?,?,?,?)",
                   (slug, name, group, order))
    cat = {r["slug"]: r["id"] for r in db.execute("SELECT id, slug FROM categories")}

    insert = """INSERT INTO books (id, category_id, name, author, publisher, isbn, price, mrp, stock,
                                  rating, sold_count, description, language)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    # 1) the 20 books from the original project keep their ids and data
    for b in json.loads((HERE / "data" / "books.json").read_text())["books"]:
        price = float(b["price"])
        db.execute(insert, (b["id"], cat[ORIGINAL_CATEGORY_SLUG[b["category"]]], b["name"], b["author"],
                            b["publisher"], b["isbn"], price, _mrp(b["id"], price), b["stock"], b["rating"],
                            (b["id"] * 37) % 180 + 5, ORIGINAL_DESCRIPTIONS.get(b["id"], ""), "English"))
    # 2) the expanded catalogue
    for n, row in enumerate(NEW_BOOKS, start=21):
        slug, title, author, publisher, price, rating, desc, isbn = row[:8]
        lang = row[8] if len(row) > 8 else "English"
        stock = (n * 13) % 31 + 4
        if n % 23 == 0:
            stock = 0          # a couple of sold-out titles
        elif n % 17 == 0:
            stock = 3          # and a few running low
        db.execute(insert, (n, cat[slug], title, author, publisher, isbn, float(price), _mrp(n, price),
                            stock, rating, (n * 37) % 180 + 5, desc, lang))
    for code, percent, min_amt, max_disc in COUPONS:
        db.execute("INSERT INTO coupons (code, percent, min_amount, max_discount) VALUES (?,?,?,?)",
                   (code, percent, min_amt, max_disc))
    for n, (title, sub, cta, link, theme, slug) in enumerate(BANNERS):
        db.execute("""INSERT INTO banners (title, subtitle, cta_text, link, theme, category_slug, sort_order)
                      VALUES (?,?,?,?,?,?,?)""", (title, sub, cta, link, theme, slug, n))


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
