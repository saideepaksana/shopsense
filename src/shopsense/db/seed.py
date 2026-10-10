from contextlib import closing
from datetime import timedelta
from pathlib import Path

from shopsense.clock import today
from shopsense.db.connection import connect, init_db

PRODUCTS = (
    ("P1", "Wireless Earbuds", "electronics", 299900, 1),
    ("P2", "Running Shoes", "footwear", 349900, 1),
    ("P3", "Cotton T-Shirt", "apparel", 79900, 1),
    ("P4", "Innerwear Pack", "innerwear", 59900, 0),
    ("P5", "Protein Powder", "perishables", 189900, 0),
    ("P6", "Laptop 15 inch", "electronics", 1250000, 1),
    ("P7", "Backpack", "accessories", 199900, 1),
    ("P8", "E-book Bundle", "digital", 49900, 0),
    ("P9", "Water Bottle", "home", 39900, 1),
)
CUSTOMERS = (
    ("C1", "Asha Rao"),
    ("C2", "Vikram Singh"),
    ("C3", "Meera Iyer"),
    ("C4", "Rohan Das"),
    ("C5", "Neha Gupta"),
    ("C6", "Karan Shah"),
)
ORDERS = (
    ("ORD-10001", "C1", "placed", 1, None, None, (("P1", 1),)),
    ("ORD-10002", "C1", "shipped", 4, 2, None, (("P2", 1),)),
    ("ORD-10003", "C1", "delivered", 8, 6, 3, (("P3", 2), ("P9", 1))),
    ("ORD-10004", "C2", "delivered", 26, 24, 20, (("P7", 1),)),
    ("ORD-10005", "C2", "delivered", 6, 4, 2, (("P4", 1),)),
    ("ORD-10006", "C2", "delivered", 9, 7, 4, (("P1", 1),)),
    ("ORD-10007", "C3", "delivered", 10, 8, 5, (("P6", 1),)),
    ("ORD-10008", "C3", "cancelled", 9, None, None, (("P5", 1),)),
    ("ORD-10009", "C3", "return_requested", 14, 12, 6, (("P2", 1),)),
    ("ORD-10010", "C4", "delivered", 18, 16, 8, (("P1", 1), ("P7", 1))),
    ("ORD-10011", "C4", "delivered", 17, 15, 12, (("P3", 1),)),
    ("ORD-10012", "C5", "delivered", 5, 3, 2, (("P9", 1),)),
    ("ORD-10013", "C5", "returned", 50, 48, 44, (("P3", 1),)),
    ("ORD-10014", "C5", "returned", 60, 58, 54, (("P9", 1),)),
    ("ORD-10015", "C5", "returned", 75, 73, 70, (("P7", 1),)),
    ("ORD-10016", "C6", "placed", 2, None, None, (("P5", 1), ("P3", 1))),
    ("ORD-10017", "C6", "delivered", 4, 3, 1, (("P2", 1),)),
)
RETURNS = (
    ("RET-9001", "ORD-10009", "changed_mind", "approved", 5, None),
    ("RET-9002", "ORD-10013", "changed_mind", "received", 43, None),
    ("RET-9003", "ORD-10014", "changed_mind", "received", 53, None),
    ("RET-9004", "ORD-10015", "changed_mind", "received", 69, None),
)
REFUNDS = (
    ("ORD-10008", None, 189900, "cancellation", 8, None),
    ("ORD-10010", None, 199900, "goodwill", 5, None),
    ("ORD-10013", "RET-9002", 79900, "return", 30, None),
    ("ORD-10014", "RET-9003", 39900, "return", 45, None),
    ("ORD-10015", "RET-9004", 199900, "return", 60, None),
)


def seed(db_path):
    path = Path(db_path)
    if path.exists():
        path.unlink()
    init_db(db_path)
    prices = {product[0]: product[3] for product in PRODUCTS}
    with closing(connect(db_path)) as conn, conn:
        _insert_customers(conn)
        conn.executemany("INSERT INTO products VALUES(?,?,?,?,?)", PRODUCTS)
        _insert_orders(conn, prices)
        _insert_returns(conn)
        _insert_refunds(conn)


def _date_days_ago(days):
    return (today() - timedelta(days=days)).isoformat()


def _insert_customers(conn):
    rows = [
        (customer_id, name, f"{name.split()[0].lower()}@example.com")
        for customer_id, name in CUSTOMERS
    ]
    conn.executemany("INSERT INTO customers VALUES(?,?,?)", rows)


def _insert_orders(conn, prices):
    for index, order in enumerate(ORDERS):
        order_id, customer_id, status, placed, shipped, delivered, items = order
        total = sum(prices[product_id] * quantity for product_id, quantity in items)
        conn.execute(
            "INSERT INTO orders VALUES(?,?,?,?,?,?,?)",
            (
                order_id,
                customer_id,
                status,
                _date_days_ago(placed),
                _date_days_ago(shipped) if shipped else None,
                _date_days_ago(delivered) if delivered else None,
                total,
            ),
        )
        conn.executemany(
            "INSERT INTO order_items(order_id,product_id,qty,unit_price_minor) VALUES(?,?,?,?)",
            [
                (order_id, product_id, quantity, prices[product_id])
                for product_id, quantity in items
            ],
        )
        payment_status = _payment_status(order_id)
        payment_method = "card" if index % 2 == 0 else "upi"
        conn.execute(
            "INSERT INTO payments VALUES(?,?,?,?)",
            (order_id, total, payment_method, payment_status),
        )


def _payment_status(order_id):
    if order_id in {"ORD-10008", "ORD-10013", "ORD-10014", "ORD-10015"}:
        return "refunded"
    if order_id == "ORD-10010":
        return "partially_refunded"
    return "paid"


def _insert_returns(conn):
    rows = [
        (return_id, order_id, reason, status, _date_days_ago(days), key)
        for return_id, order_id, reason, status, days, key in RETURNS
    ]
    conn.executemany("INSERT INTO returns VALUES(?,?,?,?,?,?)", rows)


def _insert_refunds(conn):
    rows = [
        (order_id, return_id, amount, kind, _date_days_ago(days), key)
        for order_id, return_id, amount, kind, days, key in REFUNDS
    ]
    conn.executemany(
        "INSERT INTO refunds(order_id,return_id,amount_minor,kind,created_at,idempotency_key) "
        "VALUES(?,?,?,?,?,?)",
        rows,
    )


if __name__ == "__main__":
    from shopsense.config import load_settings

    seed(load_settings().db_path)
