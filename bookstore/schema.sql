PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS order_events;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS wishlist;
DROP TABLE IF EXISTS cart_items;
DROP TABLE IF EXISTS addresses;
DROP TABLE IF EXISTS coupons;
DROP TABLE IF EXISTS books;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fullname      TEXT NOT NULL,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password      TEXT NOT NULL,
    phone         TEXT,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE categories (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    slug  TEXT NOT NULL UNIQUE,
    name  TEXT NOT NULL
);

CREATE TABLE books (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id   INTEGER NOT NULL REFERENCES categories(id),
    name          TEXT NOT NULL,
    author        TEXT NOT NULL,
    publisher     TEXT NOT NULL,
    isbn          TEXT UNIQUE,
    price         REAL NOT NULL CHECK (price >= 0),
    mrp           REAL,                      -- list price, to show a discount
    stock         INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    rating        REAL NOT NULL DEFAULT 0,
    review_count  INTEGER NOT NULL DEFAULT 0,
    sold_count    INTEGER NOT NULL DEFAULT 0,
    description   TEXT,
    image         TEXT,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_books_category ON books(category_id);
CREATE INDEX idx_books_name ON books(name);

CREATE TABLE addresses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    full_name  TEXT NOT NULL,
    phone      TEXT NOT NULL,
    line1      TEXT NOT NULL,
    line2      TEXT,
    city       TEXT NOT NULL,
    state      TEXT NOT NULL,
    pincode    TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE cart_items (
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id  INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    qty      INTEGER NOT NULL CHECK (qty > 0),
    PRIMARY KEY (user_id, book_id)
);

CREATE TABLE wishlist (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, book_id)
);

CREATE TABLE reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    rating     INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title      TEXT,
    comment    TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, book_id)
);

CREATE TABLE coupons (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE COLLATE NOCASE,
    percent       INTEGER NOT NULL CHECK (percent BETWEEN 1 AND 90),
    min_amount    REAL NOT NULL DEFAULT 0,
    max_discount  REAL,
    expires_on    TEXT,                      -- YYYY-MM-DD, NULL = never
    active        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    status          TEXT NOT NULL DEFAULT 'Pending',
    payment_method  TEXT NOT NULL,
    payment_status  TEXT NOT NULL DEFAULT 'Pending',
    subtotal        REAL NOT NULL,
    discount        REAL NOT NULL DEFAULT 0,
    shipping_fee    REAL NOT NULL DEFAULT 0,
    total           REAL NOT NULL,
    coupon_code     TEXT,
    ship_name       TEXT NOT NULL,
    ship_phone      TEXT NOT NULL,
    ship_address    TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_orders_user ON orders(user_id);

CREATE TABLE order_items (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id  INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    book_id   INTEGER REFERENCES books(id) ON DELETE SET NULL,
    title     TEXT NOT NULL,              -- snapshot, survives book edits/deletes
    author    TEXT,
    price     REAL NOT NULL,
    qty       INTEGER NOT NULL
);

CREATE TABLE order_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    status     TEXT NOT NULL,
    note       TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
