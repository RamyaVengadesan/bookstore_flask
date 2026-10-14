# PU Book Store (Flask)

An online bookstore for engineering textbooks, rebuilt from the original PHP/frameset project with **Flask, SQLite, HTML, CSS and JavaScript**. Your original 20 books (`books.json`) are loaded into the database on first run.

## Run it

```bash
python -m venv venv
venv\Scripts\activate          # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:5000. On first run the database (`instance/bookstore.sqlite`) is created and filled automatically.

| Role     | Login                                                                   |
|----------|-------------------------------------------------------------------------|
| Admin    | `admin` / `admin123` (change it: `flask --app run create-admin <name>`) |
| Customer | register on the site                                                    |

Reset the database any time with `flask --app run init-db`. Run the tests with `pytest`.

## Features

**Shopping**
- Catalogue with search (title, author, publisher, ISBN), department filter, price range, in-stock filter, 6 sort options and pagination
- Live search suggestions in the header (keyboard friendly)
- Book pages with description, discount/MRP, stock warnings, related books, star ratings and written reviews ("verified purchase" badge)
- Wishlist (heart on every book)
- Cart for guests and members: the guest cart is merged into your saved cart when you log in; quantities update without reloading; stock limits enforced
- Coupons (`WELCOME10`, `BOOKS20`, `STUDENT5`) with minimum cart value, caps and expiry; free delivery above ₹500
- Checkout with saved addresses, Cash on Delivery or demo UPI/Card (no real payment, no card data collected)
- Orders with a 5-step tracking timeline, activity log, cancellation (restocks books, refunds paid orders) and a printable invoice

**Accounts:** register/login/logout, profile, change password, address book.

**Admin panel (`/admin`):** revenue and order dashboard, low-stock alerts, top sellers; add/edit/delete books with cover upload; quick stock edits; update order status with a customer-visible note; customers list; coupon and category management.

**Quality:** responsive layout, light/dark theme, accessible focus states, generated covers when a cover image is missing or blocked, friendly 400/403/404/500 pages.

## Security notes
- Passwords hashed (Werkzeug); all SQL is parameterised; CSRF token on every POST; safe redirect handling after login; admin routes protected server-side; uploads restricted to image types with random names.
- Stock is reserved with an atomic `UPDATE ... WHERE stock >= qty`, so two buyers can't oversell the last copy.
- Before deploying: set a `SECRET_KEY` environment variable, change the admin password, and run behind a real server (e.g. `gunicorn "bookstore:create_app()"`).

## Layout
```
run.py                  start the app
bookstore/
  __init__.py           app factory, error pages, security headers
  schema.sql, db.py     database tables + helpers + CLI
  seed.py, data/        categories, coupons, descriptions, books.json
  utils.py              auth, CSRF, cart and pricing logic
  routes/               shop, auth, cart, orders, admin
  templates/, static/   HTML, CSS, JS
tests/test_app.py       13 tests covering the main flows
```

## Ideas for next steps
Password reset by email, a real payment gateway (Razorpay/Stripe), MySQL via SQLAlchemy, order emails, and a book "return" flow.
