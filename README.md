# Readora

A full-featured online bookstore built with Flask and SQLite. It includes a customer storefront and a complete admin console for managing books, orders, returns, customers and reports.

## Features

### Storefront

- 15 departments with a mega menu, hero carousel, deals, bestsellers and new arrivals
- Faceted catalogue: department, price, rating, language, publisher, stock, sorting and search suggestions
- Book pages with discounts, delivery check by PIN code, reviews with helpful votes and a wishlist
- Guest and saved carts, coupons and free shipping above a set amount
- Checkout with COD, demo UPI and demo card, order tracking, invoices, cancellation, 7-day returns and reorder
- Accounts, saved addresses, password reset, light/dark theme and a mobile tab bar

### Admin Console (`/admin`)

- **Dashboard:** revenue, orders, average order value and new customers with period comparison, plus charts, top sellers and low-stock alerts
- **Reports:** date-range breakdowns and CSV export (formula-safe) for orders, sales, books, customers, returns and subscribers
- **Books:** search, bulk edit, cover upload and bulk CSV import with a check-only mode
- **Orders and returns:** status workflow, customer-visible notes, approve/reject/refund and optional restocking
- **Customers, reviews, inbox, subscribers, banners, coupons, departments and store settings**
- **Activity log** of every admin change

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, Flask 3 (blueprints) |
| Database | SQLite |
| Frontend | Jinja2 templates, HTML5, CSS3, vanilla JavaScript |
| Testing | pytest |

## Project Structure

```text
bookstore_flask/
├── run.py                    # App entry point
├── requirements.txt
├── bookstore/
│   ├── __init__.py           # App factory and configuration
│   ├── db.py                 # Database setup and migrations
│   ├── schema.sql            # Database schema
│   ├── catalog.py            # Departments, books, banners, coupons (seed data)
│   ├── utils.py              # Helpers, CSRF, email
│   ├── routes/               # shop, auth, cart, orders, admin
│   ├── templates/            # Storefront, auth, pages and admin templates
│   └── static/               # CSS, JS and uploads
└── tests/
    └── test_app.py
```

## Getting Started

**Requirements:** Python 3.10 or newer.

```bash
git clone https://github.com/RamyaVengadesan/Readora.git
cd Readora/bookstore_flask   # adjust if your repo root is the project folder

python -m pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:5000. The database is created automatically in `instance/` on first run.

**Admin panel:** http://127.0.0.1:5000/admin

| Username | Password |
|---|---|
| `admin` | `admin123` |

Set the `ADMIN_PASSWORD` environment variable before the first run to use a different password.

## Configuration

All settings are optional environment variables.

| Variable | Purpose | Default |
|---|---|---|
| `STORE_NAME` | Store name | `Readora` |
| `STORE_TAGLINE` | Tagline | `Books for every reader` |
| `ORDER_PREFIX` | Order ID prefix | `RD` |
| `ADMIN_PASSWORD` | Initial admin password | `admin123` |
| `SECRET_KEY` | Session secret | Generated and stored in `instance/` |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM` | SMTP email (emails print to the console if `MAIL_SERVER` is empty) | empty |
| `DEMO_SHOW_RESET_LINK` | Show password-reset link on screen (set to `0` in production) | `1` |

## Running Tests

```bash
python -m pytest
```

## Demo Coupons

`WELCOME10` · `BOOKS20` · `STUDENT5`

## Notes

This is a demo project. Prices, stock and ratings are sample data, and payments are simulated. Before any real deployment, change the admin password, set a `SECRET_KEY`, disable `DEMO_SHOW_RESET_LINK` and add a real payment gateway.

## License

[MIT](LICENSE)

## Author

Ramya Vengadesan · [@RamyaVengadesan](https://github.com/RamyaVengadesan)
