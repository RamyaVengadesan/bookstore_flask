# Readora: online bookstore (Flask)

A complete, production-style online bookstore built with **Flask, SQLite, Jinja templates, plain CSS and vanilla JavaScript**. It has a customer storefront with 15 departments and 145 books, and a full admin console with analytics, reports, bulk tools and a returns workflow.

> **Demo project.** Prices, stock, ratings and orders are sample data. Payments are simulated: no card details are collected and no money moves.


## Contents
- [Highlights](#highlights)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Customer storefront](#customer-storefront)
- [Admin console](#admin-console)
- [Data model](#data-model)
- [Project structure](#project-structure)
- [Routes](#routes)
- [Security](#security)
- [Testing](#testing)
- [Deploying](#deploying)
- [Customising](#customising)
- [Roadmap](#roadmap)
- [License](#license)

## Highlights
- **145 books in 15 departments** across Engineering, Science and Maths, Business, Exam Prep, Fiction, Non-Fiction and Kids, with discounts, ratings and English and Hindi titles.
- **Real-store storefront:** department mega menu, hero banners, deals of the day, faceted filters, live search suggestions, PIN-code delivery estimate, reviews with helpful votes, wishlist, recently viewed, mobile tab bar and dark mode.
- **Complete order flow:** guest and saved carts, coupons, address book, Cash on Delivery or demo UPI and card, five-step tracking, invoices, cancellation, 7-day returns and reorder.
- **Admin console:** KPI dashboard and charts, date-range reports, CSV export and import, bulk book and order actions, returns, review moderation, inbox, banners, coupons, settings and an activity log.
- **No front-end build step.** One dependency: Flask. The database is created and filled automatically on first run.

## Quick start
Requires **Python 3.10 or newer**.

```bash
git clone <your-repo-url>
cd bookstore_flask

python -m venv venv
# Windows:      venv\Scripts\activate
# macOS/Linux:  source venv/bin/activate

python -m pip install -r requirements.txt
python run.py
```

Open <http://127.0.0.1:5000>.

| Role | How to log in |
|---|---|
| **Admin** | <http://127.0.0.1:5000/admin>, user `admin`, password `admin123` |
| **Customer** | Use **Sign up** on the site |

**Change the admin password** before using it for anything real. Set `ADMIN_PASSWORD` before the first run, or run `flask --app run create-admin <username>`.

Useful commands:

```bash
flask --app run init-db            # rebuild the database from scratch (erases data)
flask --app run create-admin NAME  # create or promote an admin
python -m pytest                   # run the test suite
```

Coupon codes to try: `WELCOME10` (10% off above ₹300), `BOOKS20` (20% off above ₹1,000), `STUDENT5` (5% off).

## Configuration
Set these environment variables before starting the app. All are optional.

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | generated and stored in `instance/secret_key` | Signs session cookies. Set your own in production. |
| `ADMIN_PASSWORD` | `admin123` | Password of the `admin` account created on first run. |
| `STORE_NAME` | `Readora` | Store name (also editable in Admin, then Settings). |
| `STORE_TAGLINE` | `Books for every reader` | Tagline. |
| `ORDER_PREFIX` | `RD` | Prefix of order numbers, e.g. `RD-000012`. |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM` | empty | SMTP settings. With no `MAIL_SERVER`, emails are printed to the server console. |
| `DEMO_SHOW_RESET_LINK` | `1` | Shows the password-reset link on screen. Set to `0` in production so links are only emailed. |

Settings that shop owners change often live in **Admin, then Settings** and apply immediately: store name, tagline, top-bar announcement, free-delivery threshold (default ₹500), delivery fee (default ₹40), low-stock level and support email.

## Customer storefront
**Browsing**
- Department mega menu grouped by section, plus a mobile drawer and bottom tab bar
- Hero banner carousel (managed in Admin), deals of the day with countdown, bestsellers, new arrivals, top rated, recently viewed
- Catalogue filters: department, price range, rating, discount, language, format and in-stock. Seven sort options, removable filter chips and pagination
- Live search suggestions by title, author or ISBN, with keyboard navigation
- `/deals`, `/bestsellers` and `/new-arrivals` pages

**Book page**
- Discount against list price, stock warnings, author, publisher, ISBN, language and format
- Delivery estimate from a PIN code (demo zones)
- Reviews with star distribution, verified-purchase badge, helpful votes and one editable review per customer
- Wishlist, related books, sticky add-to-cart bar on mobile

**Buying**
- Cart for guests and members (a guest cart merges on login), quantity limits tied to stock, free-delivery progress bar
- Coupons with minimum cart value, maximum discount and expiry
- Checkout with a saved address book and Cash on Delivery, demo UPI or demo card
- Stock is reserved atomically, so two buyers cannot oversell the last copy

**After the order**
- Order history with a five-step tracking timeline (Pending, Confirmed, Shipped, Out for Delivery, Delivered) and a printable invoice
- Cancel before shipping (restocks books and marks paid orders refunded)
- Return request within 7 days of delivery, once per order, with status updates
- One-click reorder

**Accounts and information**
- Register, log in, profile, change password, address book, forgot and reset password (one-hour links)
- Help and FAQ, shipping, returns policy, privacy, terms, about, contact form and newsletter sign-up
- `robots.txt` and `sitemap.xml`, light and dark theme, accessible focus states, friendly error pages

## Admin console
Open `/admin` while logged in as an admin. Every admin route is protected on the server.

| Area | What you can do |
|---|---|
| **Dashboard** | Revenue, orders, average order value and new customers for 7, 30 or 90 days with change against the previous period. Revenue-per-day chart, orders by status, sales by department, top sellers, low stock, recent orders. A "needs attention" strip for orders to confirm, return requests, unread messages and low or sold-out stock. |
| **Reports** | Any date range with daily, department, best-seller, payment-method and coupon breakdowns. **CSV export** for orders, sales lines, books, customers, returns and subscribers (cells that start with `=`, `+`, `-` or `@` are neutralised so spreadsheets cannot run them as formulas). |
| **Books** | Search and filter by department or stock level. Add and edit with cover upload or URL. Inline stock edits. Bulk move to another department, change prices by a percentage, or delete. |
| **Import books** | Upload a CSV to add or update many books. A **check-only mode** reports problems per row before saving. Rows with an existing ISBN update that book instead of duplicating it. Template download included. |
| **Orders** | Status tabs with counts, search, date and payment filters, bulk status update, and a single-order page with customer-visible notes. Orders only move forward, and cancelling restocks. |
| **Returns** | Approve, reject (a note is required) or mark refunded, optionally putting the books back in stock. The customer is emailed. |
| **Customers** | Search, sort by spend or orders, detail page with orders and addresses, make or remove an admin (you cannot change your own access), create a one-hour password-reset link. |
| **Reviews** | Search and remove reviews. The book rating is recalculated. |
| **Inbox and subscribers** | Read and resolve contact messages, reply by email, export newsletter subscribers. |
| **Banners** | Add, edit, reorder, hide or delete home-page hero slides, with colour themes and cover art from a department. |
| **Coupons** | Create, pause and delete codes, and see how often each was used. |
| **Departments** | Rename, set the menu group and order, add, and delete when empty. |
| **Settings** | Store name, tagline, announcement, delivery rules, low-stock level and support email. |
| **Activity log** | Who changed what, and when. |

**CSV import columns** (header names are not case sensitive):

```
name, author, publisher, category, isbn, price, mrp, stock, language, format, description
```
Required: `name`, `author`, `publisher`, `category` (a department name or URL name), `price`, `stock`. `mrp` must not be lower than `price`. Import up to 2,000 rows at a time, saved as UTF-8 CSV.

## Data model
SQLite, created from `bookstore/schema.sql`. Schema version **4**, tracked with `PRAGMA user_version`.

| Table | Purpose |
|---|---|
| `users`, `addresses` | Accounts (with an `is_admin` flag) and saved delivery addresses |
| `categories` | Departments, with a menu group and sort order |
| `books` | Catalogue: price, MRP, stock, rating, language, format, cover |
| `cart_items`, `wishlist` | Saved carts and wishlists for logged-in users |
| `reviews`, `review_votes` | Reviews and "helpful" votes |
| `coupons` | Discount codes |
| `orders`, `order_items`, `order_events` | Orders, line items (title and price are snapshotted) and the status timeline |
| `returns` | Return requests, one per order |
| `banners` | Home-page hero slides |
| `password_resets` | Hashed, expiring reset tokens |
| `subscribers`, `messages` | Newsletter and contact-form inboxes |
| `settings`, `admin_log` | Editable store settings and the admin activity log |

**Upgrades.** On start the app compares `user_version` with the code. A database one version behind (3 to 4) is upgraded in place with no data loss. An older layout is renamed to `*.bak` and rebuilt, so nothing is silently destroyed.

## Project structure
```
run.py                      start the development server
requirements.txt            Flask and pytest
bookstore/
  __init__.py               app factory, config, error pages, security headers
  db.py                     SQLite helpers, seeding, upgrade logic, CLI commands
  schema.sql                all tables
  catalog.py                categories, 125 added books, coupons, banners
  data/books.json           the original 20 books
  utils.py                  auth, CSRF, cart and pricing, delivery, email, settings, log
  routes/
    shop.py                 home, catalogue, book page, search API, reviews, wishlist, info pages
    cart.py                 cart and coupons
    orders.py               checkout, orders, invoice, cancel, returns, reorder
    auth.py                 register, login, reset password, account, addresses
    admin.py                the whole admin console
  templates/                Jinja templates (storefront, auth, pages, admin/)
  static/                   css (style.css, admin.css), js (app.js, admin.js), logo
tests/test_app.py           37 tests
docs/screenshots/           images used in this README
```

## Routes
**Storefront:** `/`, `/books`, `/deals`, `/bestsellers`, `/new-arrivals`, `/book/<id>`, `/cart`, `/checkout`, `/orders`, `/orders/<id>`, `/orders/<id>/return`, `/wishlist`, `/account`, `/login`, `/register`, `/forgot`, `/contact`, `/info/<page>`.
**JSON helpers:** `/api/search?q=`, `/api/delivery?pincode=`.
**Admin:** `/admin/`, `/admin/reports`, `/admin/export/<kind>.csv`, `/admin/books`, `/admin/books/import`, `/admin/orders`, `/admin/returns`, `/admin/reviews`, `/admin/users`, `/admin/messages`, `/admin/subscribers`, `/admin/banners`, `/admin/coupons`, `/admin/categories`, `/admin/settings`, `/admin/activity`.

## Security
- Passwords hashed with Werkzeug. Password rules: 8 or more characters with letters and numbers.
- Every `POST` requires a CSRF token. All SQL is parameterised.
- Redirects after login are restricted to local paths.
- Admin routes are enforced server-side (guests are redirected, customers get 403).
- Uploads are limited to image types and 2 MB, with random file names.
- Reset tokens are stored hashed, expire after an hour and work once.
- CSV exports neutralise spreadsheet formulas.
- Session cookies are `HttpOnly` and `SameSite=Lax`.

Before going live: set `SECRET_KEY`, change the admin password, set `DEMO_SHOW_RESET_LINK=0`, configure SMTP, use HTTPS, and replace the simulated payment step with a real gateway.

## Testing
```bash
python -m pytest
```
37 tests cover the storefront, cart and coupons, checkout and stock safety, cancellation, returns, password reset, reviews, the admin console (access control, dashboard, CSV export and import, bulk actions, order rules, returns workflow, banners, settings, customers, departments) and database upgrades.

## Deploying
The built-in server is for development only. For production use a WSGI server:

```bash
pip install gunicorn
SECRET_KEY=change-me ADMIN_PASSWORD=choose-one gunicorn "bookstore:create_app()" -w 3 -b 0.0.0.0:8000
```
Put it behind a reverse proxy (Nginx, Caddy) with HTTPS. Keep the `instance/` folder (database and secret key) on persistent storage and back it up. SQLite suits a small store. For heavy traffic, move to PostgreSQL or MySQL.

## Customising
- **Rename the store:** Admin, then Settings, or the `STORE_NAME` variable.
- **Colours and fonts:** CSS variables at the top of `bookstore/static/css/style.css`.
- **Logo:** `bookstore/static/img/mark.svg`.
- **Add books:** Admin, then Books, or bulk import a CSV.
- **Change the starting catalogue:** edit `bookstore/catalog.py` and rebuild with `flask --app run init-db`.

## Roadmap
Real payment gateway (Razorpay or Stripe), order emails, partial returns, stock alerts to the wishlist, multi-image galleries, PostgreSQL support and admin roles with finer permissions.

## License
Released under the [MIT License](LICENSE).
