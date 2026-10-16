"""Invoice Pilot data layer: SQLite schema, business rules, analytics, reports, backup and PDF documents."""
import csv
import os
import re
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
from xml.sax.saxutils import escape

APP_NAME = "InvoicePilot"          # keep: existing data folder / database stay in place
APP_TITLE = "Invoice Pilot"
APP_VERSION = "2.0.0"
TAGLINE = "Smart invoicing, ready for take-off"
PAYMENT_METHODS = ("Cash", "Bank Transfer", "Easypaisa", "JazzCash", "Card", "Cheque", "Other")
STATUS_LABELS = {"draft": "Draft", "unpaid": "Sent", "partial": "Partially Paid", "paid": "Paid",
                 "overdue": "Overdue", "void": "Void"}
QUOTE_LABELS = {"draft": "Draft", "sent": "Sent", "accepted": "Accepted", "declined": "Declined",
                "expired": "Expired", "converted": "Converted"}
EXPENSE_CATEGORIES = ("Rent", "Utilities", "Salaries", "Marketing", "Software", "Supplies", "Travel",
                      "Maintenance", "Taxes & Fees", "Other")


# ------------------------------------------------------------------ paths
def data_dir() -> Path:
    override = os.environ.get("INVOICEPILOT_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    else:
        base = Path.home() / f".{APP_NAME.lower()}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "invoicepilot.db"


def sub_dir(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


# ------------------------------------------------------------------ money
D0 = Decimal("0")
CENT = Decimal("1")


def to_decimal(value, default=None) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        if default is not None:
            return default
        raise ValueError(f"Invalid number: {value!r}")


def to_minor(amount) -> int:
    return int((to_decimal(amount) * 100).quantize(CENT, rounding=ROUND_HALF_UP))


def from_minor(minor) -> Decimal:
    return (Decimal(int(minor)) / 100).quantize(Decimal("0.01"))


def money(minor, symbol="Rs.") -> str:
    v = from_minor(minor)
    return f"{'-' if v < 0 else ''}{symbol} {abs(v):,.2f}"


def plain(minor) -> str:
    return f"{from_minor(minor):.2f}"


def round_minor(value: Decimal) -> int:
    return int(value.quantize(CENT, rounding=ROUND_HALF_UP))


def short_num(minor) -> str:
    v = abs(float(from_minor(minor)))
    sign = "-" if minor < 0 else ""
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= lim:
            return f"{sign}{v / lim:.1f}".rstrip("0").rstrip(".") + suf
    return f"{sign}{v:.0f}"


# ------------------------------------------------------------- validation
class ValidationError(ValueError):
    pass


def today_iso() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Karachi")).date().isoformat()
    except Exception:
        return date.today().isoformat()


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_date(text, field="Date") -> str:
    text = (text or "").strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValidationError(f"{field} must be in DD-MM-YYYY format.")


def fmt_date(iso) -> str:
    if not iso:
        return ""
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        return iso


def positive_decimal(text, field, allow_zero=False) -> Decimal:
    try:
        v = to_decimal(text)
    except ValueError:
        raise ValidationError(f"{field} must be a number.")
    if v < 0 or (v == 0 and not allow_zero):
        raise ValidationError(f"{field} must be greater than zero." if not allow_zero else f"{field} cannot be negative.")
    return v


def optional_rate(text, field="Tax rate"):
    text = (str(text) if text is not None else "").strip().rstrip("%")
    if text == "":
        return None
    v = positive_decimal(text, field, allow_zero=True)
    if v > 100:
        raise ValidationError(f"{field} cannot exceed 100%.")
    return str(v.normalize() if v != 0 else Decimal("0"))


def required(text, field) -> str:
    text = (text or "").strip()
    if not text:
        raise ValidationError(f"{field} is required.")
    return text


def check_email(text) -> str:
    text = (text or "").strip()
    if text and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text):
        raise ValidationError("Email address looks invalid.")
    return text


# ----------------------------------------------------------------- schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, phone TEXT DEFAULT '', email TEXT DEFAULT '', address TEXT DEFAULT '',
    ntn TEXT DEFAULT '', strn TEXT DEFAULT '', notes TEXT DEFAULT '',
    archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, sku TEXT DEFAULT '', description TEXT DEFAULT '',
    unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
    category TEXT DEFAULT '', tax_rate TEXT,
    archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    cust_name TEXT NOT NULL, cust_phone TEXT DEFAULT '', cust_email TEXT DEFAULT '',
    cust_address TEXT DEFAULT '', cust_ntn TEXT DEFAULT '', cust_strn TEXT DEFAULT '',
    issue_date TEXT NOT NULL, due_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unpaid'
        CHECK (status IN ('draft','unpaid','partial','paid','overdue','void')),
    discount_type TEXT NOT NULL DEFAULT 'none' CHECK (discount_type IN ('none','fixed','percent')),
    discount_value TEXT NOT NULL DEFAULT '0',
    discount_amount INTEGER NOT NULL DEFAULT 0,
    subtotal INTEGER NOT NULL DEFAULT 0, tax_amount INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0, amount_paid INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '', terms TEXT DEFAULT '', payment_instructions TEXT DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    position INTEGER NOT NULL, product_id INTEGER REFERENCES products(id),
    description TEXT NOT NULL, qty TEXT NOT NULL, unit_price INTEGER NOT NULL,
    tax_rate TEXT, line_total INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    receipt_no TEXT NOT NULL UNIQUE,
    amount INTEGER NOT NULL CHECK (amount > 0),
    paid_date TEXT NOT NULL, method TEXT NOT NULL,
    reference TEXT DEFAULT '', notes TEXT DEFAULT '',
    voided INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS estimates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    cust_name TEXT NOT NULL, cust_phone TEXT DEFAULT '', cust_email TEXT DEFAULT '',
    cust_address TEXT DEFAULT '', cust_ntn TEXT DEFAULT '', cust_strn TEXT DEFAULT '',
    issue_date TEXT NOT NULL, valid_until TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','sent','accepted','declined','expired','converted')),
    discount_type TEXT NOT NULL DEFAULT 'none', discount_value TEXT NOT NULL DEFAULT '0',
    discount_amount INTEGER NOT NULL DEFAULT 0, subtotal INTEGER NOT NULL DEFAULT 0,
    tax_amount INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '', terms TEXT DEFAULT '', converted_invoice_id INTEGER,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS estimate_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_id INTEGER NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,
    position INTEGER NOT NULL, product_id INTEGER,
    description TEXT NOT NULL, qty TEXT NOT NULL, unit_price INTEGER NOT NULL,
    tax_rate TEXT, line_total INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_date TEXT NOT NULL, category TEXT NOT NULL, vendor TEXT DEFAULT '',
    description TEXT DEFAULT '', amount INTEGER NOT NULL CHECK (amount > 0), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, entity TEXT NOT NULL, entity_id INTEGER, action TEXT NOT NULL, details TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_inv_customer ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_inv_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_pay_invoice ON payments(invoice_id);
CREATE INDEX IF NOT EXISTS idx_exp_date ON expenses(expense_date);
"""

DEFAULT_SETTINGS = {
    "business_name": "My Business", "business_address": "", "business_phone": "", "business_whatsapp": "",
    "business_email": "", "business_ntn": "", "business_strn": "", "logo_path": "",
    "currency_symbol": "Rs.", "date_format": "DD-MM-YYYY", "invoice_prefix": "INV", "invoice_next": "1",
    "quote_prefix": "QTN", "quote_valid_days": "30", "default_tax_rate": "0", "tax_label": "Tax",
    "default_due_days": "14", "theme": "dark",
    "payment_instructions": "Bank: ______  Title: ______  Account/IBAN: ______\nEasypaisa / JazzCash: ______",
    "invoice_terms": "Payment is due by the due date shown. Goods/services once delivered are non-refundable.",
    "invoice_footer": "Thank you for your business!",
}


def connect(path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or db_path()), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(path=None):
    conn = connect(path)
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _use(conn=None):
    """Use the caller's transaction if given, else open (and commit) our own."""
    if conn is not None:
        yield conn
    else:
        with transaction() as c:
            yield c


def init_db(path=None) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
        conn.commit()
    finally:
        conn.close()


def get_settings(path=None, conn=None) -> dict:
    c = conn or connect(path)
    try:
        s = dict(DEFAULT_SETTINGS)
        s.update({r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")})
        return s
    finally:
        if conn is None:
            c.close()


def save_settings(values: dict, path=None) -> None:
    with transaction(path) as conn:
        for k, v in values.items():
            conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, str(v)))
        audit(conn, "settings", None, "update", ", ".join(values))


def audit(conn, entity, entity_id, action, details="") -> None:
    conn.execute("INSERT INTO audit_events(ts, entity, entity_id, action, details) VALUES (?,?,?,?,?)",
                 (now_ts(), entity, entity_id, action, details))


def _q(sql, args=()):
    c = connect()
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


def _one(sql, args=()):
    rows = _q(sql, args)
    return (list(rows[0].values())[0] or 0) if rows else 0


def _rng(col, a, b):
    sql, args = "", []
    if a:
        sql += f" AND {col} >= ?"
        args.append(a)
    if b:
        sql += f" AND {col} <= ?"
        args.append(b)
    return sql, args


# ------------------------------------------------------------ calculations
def line_total(qty, unit_price_minor) -> int:
    return round_minor(to_decimal(qty) * Decimal(int(unit_price_minor)))


def calculate_totals(items, discount_type="none", discount_value="0") -> dict:
    lines = [line_total(i["qty"], i["unit_price"]) for i in items]
    subtotal = sum(lines)
    dv = to_decimal(discount_value or "0")
    if discount_type == "percent":
        if dv < 0 or dv > 100:
            raise ValidationError("Percentage discount must be between 0 and 100.")
        discount = round_minor(Decimal(subtotal) * dv / 100)
    elif discount_type == "fixed":
        if dv < 0:
            raise ValidationError("Discount cannot be negative.")
        discount = to_minor(dv)
    else:
        discount = 0
    if discount > subtotal:
        raise ValidationError("Discount cannot exceed the subtotal.")
    tax = D0
    if subtotal > 0:
        for item, lt in zip(items, lines):
            rate = item.get("tax_rate")
            if rate in (None, ""):
                continue
            taxable = Decimal(lt) - Decimal(discount) * Decimal(lt) / Decimal(subtotal)
            tax += taxable * to_decimal(rate) / 100
    tax_minor = round_minor(tax)
    return {"lines": lines, "subtotal": subtotal, "discount_amount": discount, "tax_amount": tax_minor,
            "total": subtotal - discount + tax_minor}


def compute_status(total, paid, due_iso, current, today=None) -> str:
    if current in ("void", "draft"):
        return current
    today = today or today_iso()
    if total - paid <= 0:
        return "paid"
    if due_iso < today:
        return "overdue"
    return "partial" if paid > 0 else "unpaid"


def refresh_statuses() -> None:
    today = today_iso()
    with transaction() as c:
        for r in c.execute("SELECT id, total, amount_paid, due_date, status FROM invoices "
                           "WHERE status NOT IN ('draft','void')").fetchall():
            new = compute_status(r["total"], r["amount_paid"], r["due_date"], r["status"], today)
            if new != r["status"]:
                c.execute("UPDATE invoices SET status=? WHERE id=?", (new, r["id"]))
        c.execute("UPDATE estimates SET status='expired' WHERE status='sent' AND valid_until < ?", (today,))


def _next_number(c, table, prefix_key, default_prefix, start_key=None) -> str:
    s = get_settings(conn=c)
    prefix = re.sub(r"[^A-Za-z0-9]", "", s.get(prefix_key) or "") or default_prefix
    stem = f"{prefix}-{today_iso()[:4]}-"
    last = 0
    for (num,) in c.execute(f"SELECT number FROM {table} WHERE number LIKE ?", (stem + "%",)):
        try:
            last = max(last, int(num[len(stem):]))
        except ValueError:
            pass
    if start_key:
        try:
            last = max(last, int(s.get(start_key) or 1) - 1)
        except ValueError:
            pass
    return f"{stem}{last + 1:04d}"


def peek_number(kind="invoice") -> str:
    c = connect()
    try:
        if kind == "quote":
            return _next_number(c, "estimates", "quote_prefix", "QTN")
        return _next_number(c, "invoices", "invoice_prefix", "INV", "invoice_next")
    finally:
        c.close()


def _clean_items(raw_items) -> list:
    if not raw_items:
        raise ValidationError("Add at least one line item.")
    out = []
    for n, it in enumerate(raw_items, 1):
        desc = (it.get("description") or "").strip()
        if not desc:
            raise ValidationError(f"Item {n}: description is required.")
        qty = positive_decimal(it.get("qty"), f"Item {n} quantity")
        if "unit_price_rs" in it:
            price = to_minor(positive_decimal(it["unit_price_rs"], f"Item {n} unit price", allow_zero=True))
        else:
            price = int(it["unit_price"])
        out.append({"description": desc, "qty": str(qty), "unit_price": price,
                    "tax_rate": optional_rate(it.get("tax_rate"), f"Item {n} tax rate"),
                    "product_id": it.get("product_id")})
    return out


def _snapshot(cust):
    return (cust["name"], cust["phone"], cust["email"], cust["address"], cust["ntn"], cust["strn"])


# ----------------------------------------------------------------- invoices
def save_invoice(data, raw_items, invoice_id=None, as_draft=False, conn=None) -> int:
    items = _clean_items(raw_items)
    issue, due = data["issue_date"], data["due_date"]
    if due < issue:
        raise ValidationError("Due date cannot be earlier than the issue date.")
    dtype = data.get("discount_type", "none")
    totals = calculate_totals(items, dtype, data.get("discount_value", "0"))
    dval = str(data.get("discount_value") or "0") if dtype != "none" else "0"
    with _use(conn) as c:
        cust = c.execute("SELECT * FROM customers WHERE id=?", (data.get("customer_id"),)).fetchone()
        if not cust:
            raise ValidationError("Please select a customer.")
        now = now_ts()
        if invoice_id:
            inv = c.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if not inv:
                raise ValidationError("Invoice not found.")
            if inv["status"] == "void":
                raise ValidationError("A void invoice cannot be edited.")
            if totals["total"] < inv["amount_paid"]:
                raise ValidationError("New total is lower than the amount already paid on this invoice.")
            if as_draft and inv["amount_paid"] > 0:
                raise ValidationError("An invoice with payments cannot be turned back into a draft.")
            snap = (_snapshot(cust) if cust["id"] != inv["customer_id"] else
                    (inv["cust_name"], inv["cust_phone"], inv["cust_email"], inv["cust_address"],
                     inv["cust_ntn"], inv["cust_strn"]))
            if as_draft:
                status = "draft"
            else:
                base = "unpaid" if inv["status"] == "draft" else inv["status"]
                status = compute_status(totals["total"], inv["amount_paid"], due, base)
            c.execute("""UPDATE invoices SET customer_id=?, cust_name=?, cust_phone=?, cust_email=?, cust_address=?,
                         cust_ntn=?, cust_strn=?, issue_date=?, due_date=?, status=?, discount_type=?,
                         discount_value=?, discount_amount=?, subtotal=?, tax_amount=?, total=?, notes=?, terms=?,
                         payment_instructions=?, updated_at=? WHERE id=?""",
                      (cust["id"],) + snap + (issue, due, status, dtype, dval, totals["discount_amount"],
                       totals["subtotal"], totals["tax_amount"], totals["total"], data.get("notes", ""),
                       data.get("terms", ""), data.get("payment_instructions", ""), now, invoice_id))
            c.execute("DELETE FROM invoice_items WHERE invoice_id=?", (invoice_id,))
            inv_id, action, number = invoice_id, "update", inv["number"]
        else:
            number = _next_number(c, "invoices", "invoice_prefix", "INV", "invoice_next")
            status = "draft" if as_draft else compute_status(totals["total"], 0, due, "unpaid")
            cur = c.execute("""INSERT INTO invoices(number, customer_id, cust_name, cust_phone, cust_email,
                         cust_address, cust_ntn, cust_strn, issue_date, due_date, status, discount_type, discount_value,
                         discount_amount, subtotal, tax_amount, total, amount_paid, notes, terms, payment_instructions,
                         created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?)""",
                            (number, cust["id"]) + _snapshot(cust) + (issue, due, status, dtype, dval,
                             totals["discount_amount"], totals["subtotal"], totals["tax_amount"], totals["total"],
                             data.get("notes", ""), data.get("terms", ""), data.get("payment_instructions", ""),
                             now, now))
            inv_id, action = cur.lastrowid, "create"
        for pos, (it, lt) in enumerate(zip(items, totals["lines"])):
            c.execute("INSERT INTO invoice_items(invoice_id, position, product_id, description, qty, unit_price, "
                      "tax_rate, line_total) VALUES (?,?,?,?,?,?,?,?)",
                      (inv_id, pos, it["product_id"], it["description"], it["qty"], it["unit_price"],
                       it["tax_rate"], lt))
        audit(c, "invoice", inv_id, action, f"{number} total={totals['total']} status={status}")
        return inv_id


def get_invoice(invoice_id):
    c = connect()
    try:
        r = c.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not r:
            return None
        inv = dict(r)
        inv["balance"] = inv["total"] - inv["amount_paid"]
        inv["items"] = [dict(i) for i in c.execute(
            "SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY position", (invoice_id,))]
        inv["payments"] = [dict(p) for p in c.execute(
            "SELECT * FROM payments WHERE invoice_id=? ORDER BY paid_date, id", (invoice_id,))]
        return inv
    finally:
        c.close()


def list_invoices(search="", status="All", date_from=None, date_to=None) -> list:
    refresh_statuses()
    like = f"%{search.strip()}%"
    sql = "SELECT *, (total - amount_paid) AS balance FROM invoices WHERE (number LIKE ? OR cust_name LIKE ?)"
    args = [like, like]
    if status and status != "All":
        key = {v.lower(): k for k, v in STATUS_LABELS.items()}.get(status.lower(), status.lower())
        sql += " AND status = ?"
        args.append(key)
    rs, ra = _rng("issue_date", date_from, date_to)
    return _q(sql + rs + " ORDER BY issue_date DESC, id DESC", args + ra)


def open_invoices_for_payment() -> list:
    refresh_statuses()
    return _q("SELECT *, (total - amount_paid) AS balance FROM invoices "
              "WHERE status IN ('unpaid','partial','overdue') AND total > amount_paid ORDER BY issue_date, id")


def duplicate_invoice(invoice_id) -> int:
    inv = get_invoice(invoice_id)
    if not inv:
        raise ValidationError("Invoice not found.")
    s = get_settings()
    issue = today_iso()
    due = (date.fromisoformat(issue) + timedelta(days=int(s.get("default_due_days") or 14))).isoformat()
    data = {k: inv[k] for k in ("customer_id", "discount_type", "discount_value", "notes", "terms",
                                "payment_instructions")}
    data.update(issue_date=issue, due_date=due)
    items = [{k: i[k] for k in ("description", "qty", "unit_price", "tax_rate", "product_id")} for i in inv["items"]]
    return save_invoice(data, items, as_draft=True)


def mark_sent(invoice_id) -> None:
    with transaction() as c:
        inv = c.execute("SELECT number, status, total, amount_paid, due_date FROM invoices WHERE id=?",
                        (invoice_id,)).fetchone()
        if not inv:
            raise ValidationError("Invoice not found.")
        if inv["status"] != "draft":
            raise ValidationError("Only draft invoices can be marked as sent.")
        st = compute_status(inv["total"], inv["amount_paid"], inv["due_date"], "unpaid")
        c.execute("UPDATE invoices SET status=?, updated_at=? WHERE id=?", (st, now_ts(), invoice_id))
        audit(c, "invoice", invoice_id, "mark_sent", inv["number"])


def void_invoice(invoice_id, reason="") -> None:
    with transaction() as c:
        inv = c.execute("SELECT number, status FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValidationError("Invoice not found.")
        if inv["status"] == "void":
            raise ValidationError("Invoice is already void.")
        c.execute("UPDATE invoices SET status='void', updated_at=? WHERE id=?", (now_ts(), invoice_id))
        audit(c, "invoice", invoice_id, "void", f"{inv['number']} {reason}".strip())


def delete_draft_invoice(invoice_id) -> None:
    with transaction() as c:
        inv = c.execute("SELECT number, status, amount_paid FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValidationError("Invoice not found.")
        if inv["status"] != "draft" or inv["amount_paid"] > 0:
            raise ValidationError("Only draft invoices without payments can be deleted. Use Void instead.")
        c.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
        audit(c, "invoice", invoice_id, "delete", inv["number"])


# ----------------------------------------------------------------- payments
def _next_receipt(conn) -> str:
    stem = f"RCT-{today_iso()[:4]}-"
    last = 0
    for (n,) in conn.execute("SELECT receipt_no FROM payments WHERE receipt_no LIKE ?", (stem + "%",)):
        try:
            last = max(last, int(n[len(stem):]))
        except ValueError:
            pass
    return f"{stem}{last + 1:04d}"


def _sync_invoice(conn, invoice_id) -> None:
    paid = conn.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE invoice_id=? AND voided=0",
                        (invoice_id,)).fetchone()[0]
    inv = conn.execute("SELECT total, due_date, status FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    status = compute_status(inv["total"], paid, inv["due_date"], "unpaid" if inv["status"] == "draft" else inv["status"])
    conn.execute("UPDATE invoices SET amount_paid=?, status=?, updated_at=? WHERE id=?",
                 (paid, status, now_ts(), invoice_id))


def add_payment(invoice_id, amount_minor, paid_date, method, reference="", notes="") -> int:
    if amount_minor <= 0:
        raise ValidationError("Payment amount must be greater than zero.")
    if method not in PAYMENT_METHODS:
        raise ValidationError("Choose a valid payment method.")
    if paid_date > today_iso():
        raise ValidationError("Payment date cannot be in the future.")
    with transaction() as c:
        inv = c.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValidationError("Invoice not found.")
        if inv["status"] in ("void", "draft"):
            raise ValidationError(f"Payments cannot be recorded against a {inv['status']} invoice.")
        if amount_minor > inv["total"] - inv["amount_paid"]:
            raise ValidationError("This payment is more than the outstanding balance (overpayment blocked).")
        cutoff = (datetime.now() - timedelta(seconds=8)).strftime("%Y-%m-%d %H:%M:%S")
        if c.execute("SELECT 1 FROM payments WHERE invoice_id=? AND amount=? AND paid_date=? AND method=? "
                     "AND reference=? AND voided=0 AND created_at >= ?",
                     (invoice_id, amount_minor, paid_date, method, reference.strip(), cutoff)).fetchone():
            raise ValidationError("An identical payment was just recorded - duplicate blocked.")
        receipt = _next_receipt(c)
        cur = c.execute("INSERT INTO payments(invoice_id, receipt_no, amount, paid_date, method, reference, notes, "
                        "created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (invoice_id, receipt, amount_minor, paid_date, method, reference.strip(), notes.strip(), now_ts()))
        _sync_invoice(c, invoice_id)
        audit(c, "payment", cur.lastrowid, "create", f"{receipt} {inv['number']} amount={amount_minor}")
        return cur.lastrowid


def void_payment(payment_id) -> None:
    with transaction() as c:
        p = c.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        if not p:
            raise ValidationError("Payment not found.")
        if p["voided"]:
            raise ValidationError("Payment is already reversed.")
        c.execute("UPDATE payments SET voided=1 WHERE id=?", (payment_id,))
        _sync_invoice(c, p["invoice_id"])
        audit(c, "payment", payment_id, "void", p["receipt_no"])


def list_payments(search="", date_from=None, date_to=None, include_voided=True) -> list:
    like = f"%{search.strip()}%"
    sql = """SELECT p.*, i.number AS invoice_number, i.cust_name FROM payments p JOIN invoices i ON i.id = p.invoice_id
             WHERE (i.number LIKE ? OR i.cust_name LIKE ? OR p.reference LIKE ? OR p.receipt_no LIKE ?)"""
    if not include_voided:
        sql += " AND p.voided = 0"
    rs, ra = _rng("p.paid_date", date_from, date_to)
    return _q(sql + rs + " ORDER BY p.paid_date DESC, p.id DESC", [like] * 4 + ra)


def get_receipt_data(payment_id):
    r = _q("""SELECT p.*, i.number AS invoice_number, i.cust_name, i.cust_phone, i.total AS invoice_total,
              i.amount_paid AS invoice_paid FROM payments p JOIN invoices i ON i.id = p.invoice_id WHERE p.id=?""",
           (payment_id,))
    return r[0] if r else None


# --------------------------------------------------------- customers/products
def save_customer(data, customer_id=None) -> int:
    name = required(data.get("name"), "Client name")
    email = check_email(data.get("email", ""))
    vals = (name, data.get("phone", "").strip(), email, data.get("address", "").strip(),
            data.get("ntn", "").strip(), data.get("strn", "").strip(), data.get("notes", "").strip())
    with transaction() as c:
        if customer_id:
            c.execute("UPDATE customers SET name=?, phone=?, email=?, address=?, ntn=?, strn=?, notes=? WHERE id=?",
                      vals + (customer_id,))
            audit(c, "customer", customer_id, "update", name)
            return customer_id
        cur = c.execute("INSERT INTO customers(name, phone, email, address, ntn, strn, notes, created_at) "
                        "VALUES (?,?,?,?,?,?,?,?)", vals + (now_ts(),))
        audit(c, "customer", cur.lastrowid, "create", name)
        return cur.lastrowid


def set_customer_archived(customer_id, archived) -> None:
    with transaction() as c:
        c.execute("UPDATE customers SET archived=? WHERE id=?", (1 if archived else 0, customer_id))
        audit(c, "customer", customer_id, "archive" if archived else "restore")


def list_customers(search="", include_archived=False) -> list:
    like = f"%{search.strip()}%"
    sql = """SELECT cu.*,
               COALESCE((SELECT SUM(i.total - i.amount_paid) FROM invoices i WHERE i.customer_id = cu.id
                         AND i.status NOT IN ('draft','void')), 0) AS balance,
               COALESCE((SELECT SUM(i.total) FROM invoices i WHERE i.customer_id = cu.id
                         AND i.status NOT IN ('draft','void')), 0) AS billed,
               (SELECT COUNT(*) FROM invoices i WHERE i.customer_id = cu.id) AS invoice_count
             FROM customers cu WHERE (cu.name LIKE ? OR cu.phone LIKE ? OR cu.email LIKE ? OR cu.ntn LIKE ?)"""
    if not include_archived:
        sql += " AND cu.archived = 0"
    return _q(sql + " ORDER BY cu.name COLLATE NOCASE", (like,) * 4)


def customer_invoices(customer_id) -> list:
    return _q("SELECT * FROM invoices WHERE customer_id=? ORDER BY issue_date DESC, id DESC", (customer_id,))


def save_product(data, product_id=None) -> int:
    name = required(data.get("name"), "Item name")
    price = to_minor(positive_decimal(data.get("unit_price", ""), "Unit price", allow_zero=True))
    rate = optional_rate(data.get("tax_rate", ""))
    vals = (name, data.get("sku", "").strip(), data.get("description", "").strip(), price,
            data.get("category", "").strip(), rate)
    with transaction() as c:
        if product_id:
            c.execute("UPDATE products SET name=?, sku=?, description=?, unit_price=?, category=?, tax_rate=? "
                      "WHERE id=?", vals + (product_id,))
            audit(c, "product", product_id, "update", name)
            return product_id
        cur = c.execute("INSERT INTO products(name, sku, description, unit_price, category, tax_rate, created_at) "
                        "VALUES (?,?,?,?,?,?,?)", vals + (now_ts(),))
        audit(c, "product", cur.lastrowid, "create", name)
        return cur.lastrowid


def set_product_archived(product_id, archived) -> None:
    with transaction() as c:
        c.execute("UPDATE products SET archived=? WHERE id=?", (1 if archived else 0, product_id))
        audit(c, "product", product_id, "archive" if archived else "restore")


def list_products(search="", include_archived=False) -> list:
    like = f"%{search.strip()}%"
    sql = "SELECT * FROM products WHERE (name LIKE ? OR sku LIKE ? OR category LIKE ? OR description LIKE ?)"
    if not include_archived:
        sql += " AND archived = 0"
    return _q(sql + " ORDER BY name COLLATE NOCASE", (like,) * 4)


# ---------------------------------------------------------------- estimates
def save_estimate(data, raw_items, estimate_id=None) -> int:
    items = _clean_items(raw_items)
    issue, valid = data["issue_date"], data["valid_until"]
    if valid < issue:
        raise ValidationError("'Valid until' cannot be earlier than the issue date.")
    dtype = data.get("discount_type", "none")
    totals = calculate_totals(items, dtype, data.get("discount_value", "0"))
    dval = str(data.get("discount_value") or "0") if dtype != "none" else "0"
    with transaction() as c:
        cust = c.execute("SELECT * FROM customers WHERE id=?", (data.get("customer_id"),)).fetchone()
        if not cust:
            raise ValidationError("Please select a client.")
        now = now_ts()
        if estimate_id:
            est = c.execute("SELECT * FROM estimates WHERE id=?", (estimate_id,)).fetchone()
            if not est:
                raise ValidationError("Quotation not found.")
            if est["status"] == "converted":
                raise ValidationError("A converted quotation cannot be edited.")
            snap = (_snapshot(cust) if cust["id"] != est["customer_id"] else
                    (est["cust_name"], est["cust_phone"], est["cust_email"], est["cust_address"],
                     est["cust_ntn"], est["cust_strn"]))
            c.execute("""UPDATE estimates SET customer_id=?, cust_name=?, cust_phone=?, cust_email=?, cust_address=?,
                         cust_ntn=?, cust_strn=?, issue_date=?, valid_until=?, discount_type=?, discount_value=?,
                         discount_amount=?, subtotal=?, tax_amount=?, total=?, notes=?, terms=?, updated_at=?
                         WHERE id=?""",
                      (cust["id"],) + snap + (issue, valid, dtype, dval, totals["discount_amount"], totals["subtotal"],
                       totals["tax_amount"], totals["total"], data.get("notes", ""), data.get("terms", ""), now,
                       estimate_id))
            c.execute("DELETE FROM estimate_items WHERE estimate_id=?", (estimate_id,))
            eid, action, number = estimate_id, "update", est["number"]
        else:
            number = _next_number(c, "estimates", "quote_prefix", "QTN")
            cur = c.execute("""INSERT INTO estimates(number, customer_id, cust_name, cust_phone, cust_email, cust_address,
                         cust_ntn, cust_strn, issue_date, valid_until, status, discount_type, discount_value,
                         discount_amount, subtotal, tax_amount, total, notes, terms, created_at, updated_at)
                         VALUES (?,?,?,?,?,?,?,?,?,?,'draft',?,?,?,?,?,?,?,?,?,?)""",
                            (number, cust["id"]) + _snapshot(cust) + (issue, valid, dtype, dval,
                             totals["discount_amount"], totals["subtotal"], totals["tax_amount"], totals["total"],
                             data.get("notes", ""), data.get("terms", ""), now, now))
            eid, action = cur.lastrowid, "create"
        for pos, (it, lt) in enumerate(zip(items, totals["lines"])):
            c.execute("INSERT INTO estimate_items(estimate_id, position, product_id, description, qty, unit_price, "
                      "tax_rate, line_total) VALUES (?,?,?,?,?,?,?,?)",
                      (eid, pos, it["product_id"], it["description"], it["qty"], it["unit_price"], it["tax_rate"], lt))
        audit(c, "estimate", eid, action, f"{number} total={totals['total']}")
        return eid


def get_estimate(estimate_id):
    c = connect()
    try:
        r = c.execute("SELECT * FROM estimates WHERE id=?", (estimate_id,)).fetchone()
        if not r:
            return None
        e = dict(r)
        e["items"] = [dict(i) for i in c.execute(
            "SELECT * FROM estimate_items WHERE estimate_id=? ORDER BY position", (estimate_id,))]
        return e
    finally:
        c.close()


def list_estimates(search="", status="All") -> list:
    refresh_statuses()
    like = f"%{search.strip()}%"
    sql, args = "SELECT * FROM estimates WHERE (number LIKE ? OR cust_name LIKE ?)", [like, like]
    if status and status != "All":
        sql += " AND status = ?"
        args.append(status.lower())
    return _q(sql + " ORDER BY issue_date DESC, id DESC", args)


def set_estimate_status(estimate_id, status) -> None:
    if status not in ("draft", "sent", "accepted", "declined"):
        raise ValidationError("Invalid quotation status.")
    with transaction() as c:
        e = c.execute("SELECT number, status FROM estimates WHERE id=?", (estimate_id,)).fetchone()
        if not e:
            raise ValidationError("Quotation not found.")
        if e["status"] == "converted":
            raise ValidationError("This quotation was already converted to an invoice.")
        c.execute("UPDATE estimates SET status=?, updated_at=? WHERE id=?", (status, now_ts(), estimate_id))
        audit(c, "estimate", estimate_id, "status", f"{e['number']} -> {status}")


def convert_estimate(estimate_id) -> int:
    with transaction() as c:
        e = c.execute("SELECT * FROM estimates WHERE id=?", (estimate_id,)).fetchone()
        if not e:
            raise ValidationError("Quotation not found.")
        if e["status"] == "converted":
            raise ValidationError("This quotation was already converted to an invoice.")
        if e["status"] != "accepted":
            raise ValidationError("Only accepted quotations can be converted. Mark it as Accepted first.")
        s = get_settings(conn=c)
        issue = today_iso()
        due = (date.fromisoformat(issue) + timedelta(days=int(s.get("default_due_days") or 14))).isoformat()
        items = [{k: i[k] for k in ("description", "qty", "unit_price", "tax_rate", "product_id")} for i in
                 c.execute("SELECT * FROM estimate_items WHERE estimate_id=? ORDER BY position", (estimate_id,))]
        data = {"customer_id": e["customer_id"], "issue_date": issue, "due_date": due,
                "discount_type": e["discount_type"], "discount_value": e["discount_value"],
                "notes": e["notes"], "terms": e["terms"] or s.get("invoice_terms", ""),
                "payment_instructions": s.get("payment_instructions", "")}
        inv_id = save_invoice(data, items, conn=c)
        c.execute("UPDATE estimates SET status='converted', converted_invoice_id=?, updated_at=? WHERE id=?",
                  (inv_id, now_ts(), estimate_id))
        audit(c, "estimate", estimate_id, "convert", f"{e['number']} -> invoice id {inv_id}")
        return inv_id


def delete_estimate(estimate_id) -> None:
    with transaction() as c:
        e = c.execute("SELECT number, status FROM estimates WHERE id=?", (estimate_id,)).fetchone()
        if not e:
            raise ValidationError("Quotation not found.")
        if e["status"] == "converted":
            raise ValidationError("Converted quotations are kept as a record and cannot be deleted.")
        c.execute("DELETE FROM estimates WHERE id=?", (estimate_id,))
        audit(c, "estimate", estimate_id, "delete", e["number"])


# ----------------------------------------------------------------- expenses
def save_expense(data, expense_id=None) -> int:
    amount = to_minor(positive_decimal(data.get("amount"), "Amount"))
    day = parse_date(data.get("expense_date"), "Date")
    cat = required(data.get("category"), "Category")
    vals = (day, cat, (data.get("vendor") or "").strip(), (data.get("description") or "").strip(), amount)
    with transaction() as c:
        if expense_id:
            c.execute("UPDATE expenses SET expense_date=?, category=?, vendor=?, description=?, amount=? WHERE id=?",
                      vals + (expense_id,))
            audit(c, "expense", expense_id, "update", f"{cat} {amount}")
            return expense_id
        cur = c.execute("INSERT INTO expenses(expense_date, category, vendor, description, amount, created_at) "
                        "VALUES (?,?,?,?,?,?)", vals + (now_ts(),))
        audit(c, "expense", cur.lastrowid, "create", f"{cat} {amount}")
        return cur.lastrowid


def delete_expense(expense_id) -> None:
    with transaction() as c:
        c.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
        audit(c, "expense", expense_id, "delete")


def list_expenses(search="", category="All", date_from=None, date_to=None) -> list:
    like = f"%{search.strip()}%"
    sql, args = "SELECT * FROM expenses WHERE (description LIKE ? OR vendor LIKE ? OR category LIKE ?)", [like] * 3
    if category and category != "All":
        sql += " AND category = ?"
        args.append(category)
    rs, ra = _rng("expense_date", date_from, date_to)
    return _q(sql + rs + " ORDER BY expense_date DESC, id DESC", args + ra)


# ---------------------------------------------------------------- analytics
def _months_between(a, b, earliest, cap=12) -> list:
    end = date.fromisoformat(b or today_iso())
    if a:
        start = date.fromisoformat(a)
    elif earliest:
        start = date.fromisoformat(earliest + "-01")
    else:
        y, m = end.year, end.month - 5
        if m < 1:
            y, m = y - 1, m + 12
        start = date(y, m, 1)
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out[-cap:]


AGING_BUCKETS = ("Not yet due", "1-30 days", "31-60 days", "61-90 days", "90+ days")


def _bucket(days_over) -> int:
    return 0 if days_over <= 0 else 1 if days_over <= 30 else 2 if days_over <= 60 else 3 if days_over <= 90 else 4


def analytics(a=None, b=None) -> dict:
    """Dashboard numbers from stored records only. a/b = ISO date range (None = open)."""
    refresh_statuses()
    today = today_iso()
    live = "status NOT IN ('draft','void')"
    ri, ai = _rng("issue_date", a, b)
    rp, ap = _rng("p.paid_date", a, b)
    re_, ae = _rng("expense_date", a, b)
    pay_sql = "FROM payments p JOIN invoices i ON i.id=p.invoice_id WHERE p.voided=0 AND i.status <> 'void'"
    month = today[:7]
    out = {
        "revenue": _one(f"SELECT SUM(total) FROM invoices WHERE {live}{ri}", ai),
        "collected": _one(f"SELECT SUM(p.amount) {pay_sql}{rp}", ap),
        "expenses": _one(f"SELECT SUM(amount) FROM expenses WHERE 1=1{re_}", ae),
        "outstanding": _one("SELECT SUM(total - amount_paid) FROM invoices WHERE status IN ('unpaid','partial','overdue')"),
        "overdue_count": _one("SELECT COUNT(*) FROM invoices WHERE status='overdue'"),
        "overdue_amount": _one("SELECT SUM(total - amount_paid) FROM invoices WHERE status='overdue'"),
        "paid_count": _one(f"SELECT COUNT(*) FROM invoices WHERE status='paid'{ri}", ai),
        "paid_amount": _one(f"SELECT SUM(total) FROM invoices WHERE status='paid'{ri}", ai),
        "unpaid_count": _one(f"SELECT COUNT(*) FROM invoices WHERE status IN ('unpaid','partial','overdue'){ri}", ai),
        "unpaid_amount": _one(f"SELECT SUM(total - amount_paid) FROM invoices "
                              f"WHERE status IN ('unpaid','partial','overdue'){ri}", ai),
        "month_income": _one(f"SELECT SUM(p.amount) {pay_sql} AND p.paid_date LIKE ?", (month + "%",)),
        "month_expenses": _one("SELECT SUM(amount) FROM expenses WHERE expense_date LIKE ?", (month + "%",)),
        "client_count": _one("SELECT COUNT(*) FROM customers WHERE archived=0"),
    }
    out["net_profit"] = (out["collected"] - out["expenses"]) if (out["collected"] or out["expenses"]) else None
    out["has_data"] = bool(_one("SELECT COUNT(*) FROM invoices") or _one("SELECT COUNT(*) FROM expenses"))

    inv_m = {r["m"]: r["t"] for r in _q(f"SELECT substr(issue_date,1,7) m, SUM(total) t FROM invoices "
                                         f"WHERE {live}{ri} GROUP BY m", ai)}
    pay_m = {r["m"]: r["t"] for r in _q(f"SELECT substr(p.paid_date,1,7) m, SUM(p.amount) t {pay_sql}{rp} GROUP BY m", ap)}
    exp_m = {r["m"]: r["t"] for r in _q(f"SELECT substr(expense_date,1,7) m, SUM(amount) t FROM expenses "
                                         f"WHERE 1=1{re_} GROUP BY m", ae)}
    seen = sorted(set(inv_m) | set(pay_m) | set(exp_m))
    months = _months_between(a, b, seen[0] if seen else None)
    out["series"] = [{"month": m, "revenue": inv_m.get(m, 0), "collected": pay_m.get(m, 0),
                      "expenses": exp_m.get(m, 0)} for m in months]

    out["status_counts"] = {r["status"]: r["n"] for r in _q(
        f"SELECT status, COUNT(*) n FROM invoices WHERE status <> 'void'{ri} GROUP BY status", ai)}

    buckets = [[name, 0, 0] for name in AGING_BUCKETS]
    for r in _q("SELECT total, amount_paid, due_date FROM invoices WHERE status IN ('unpaid','partial','overdue') "
                "AND total > amount_paid"):
        i = _bucket((date.fromisoformat(today) - date.fromisoformat(r["due_date"])).days)
        buckets[i][1] += r["total"] - r["amount_paid"]
        buckets[i][2] += 1
    out["aging"] = buckets

    out["top_clients"] = _q(f"SELECT MAX(cust_name) name, SUM(total) total, COUNT(*) n FROM invoices WHERE {live}{ri} "
                            f"GROUP BY customer_id ORDER BY total DESC LIMIT 5", ai)
    out["recent"] = _q("""SELECT * FROM (
        SELECT 'Invoice' AS kind, number AS ref, cust_name AS party, total AS amount, issue_date AS day,
               status AS status, created_at AS ts FROM invoices
        UNION ALL
        SELECT 'Payment', p.receipt_no, i.cust_name, p.amount, p.paid_date,
               CASE p.voided WHEN 1 THEN 'reversed' ELSE 'received' END, p.created_at
        FROM payments p JOIN invoices i ON i.id = p.invoice_id) ORDER BY ts DESC LIMIT 8""")
    return out


# ------------------------------------------------------------------ reports
# Each report: {"title", "headers", "rows" (display strings), "totals" [(label, text)]}
def _sym():
    return get_settings().get("currency_symbol", "Rs.") or "Rs."


def sales_report(a=None, b=None) -> dict:
    refresh_statuses()
    s = _sym()
    rng, args = _rng("issue_date", a, b)
    rows = _q(f"SELECT * FROM invoices WHERE status NOT IN ('draft','void'){rng} ORDER BY issue_date, id", args)
    return {"title": "Revenue Report (Invoiced)",
            "headers": ["Invoice", "Date", "Customer", "Total", "Paid", "Balance", "Status"],
            "rows": [[r["number"], fmt_date(r["issue_date"]), r["cust_name"], money(r["total"], s),
                      money(r["amount_paid"], s), money(r["total"] - r["amount_paid"], s),
                      STATUS_LABELS[r["status"]]] for r in rows],
            "totals": [("Total invoiced", money(sum(r["total"] for r in rows), s)),
                       ("Of which paid so far", money(sum(r["amount_paid"] for r in rows), s)),
                       ("Still outstanding", money(sum(r["total"] - r["amount_paid"] for r in rows), s))]}


def payments_report(a=None, b=None) -> dict:
    s = _sym()
    rng, args = _rng("p.paid_date", a, b)
    rows = _q(f"""SELECT p.*, i.number, i.cust_name FROM payments p JOIN invoices i ON i.id=p.invoice_id
                  WHERE p.voided=0 AND i.status <> 'void'{rng} ORDER BY p.paid_date, p.id""", args)
    by = {}
    for r in rows:
        by[r["method"]] = by.get(r["method"], 0) + r["amount"]
    return {"title": "Payments Received (Cash Collected)",
            "headers": ["Receipt", "Date", "Invoice", "Customer", "Method", "Reference", "Amount"],
            "rows": [[r["receipt_no"], fmt_date(r["paid_date"]), r["number"], r["cust_name"], r["method"],
                      r["reference"], money(r["amount"], s)] for r in rows],
            "totals": [("Total received", money(sum(r["amount"] for r in rows), s))] +
                      [(f"  {m}", money(v, s)) for m, v in sorted(by.items())]}


def outstanding_report() -> dict:
    refresh_statuses()
    s = _sym()
    rows = _q("SELECT * FROM invoices WHERE status IN ('unpaid','partial','overdue') AND total > amount_paid "
              "ORDER BY due_date, id")
    return {"title": "Outstanding Payments",
            "headers": ["Invoice", "Customer", "Issued", "Due", "Total", "Paid", "Balance", "Status"],
            "rows": [[r["number"], r["cust_name"], fmt_date(r["issue_date"]), fmt_date(r["due_date"]),
                      money(r["total"], s), money(r["amount_paid"], s), money(r["total"] - r["amount_paid"], s),
                      STATUS_LABELS[r["status"]]] for r in rows],
            "totals": [("Total outstanding", money(sum(r["total"] - r["amount_paid"] for r in rows), s))]}


def overdue_report() -> dict:
    refresh_statuses()
    s, today = _sym(), date.fromisoformat(today_iso())
    rows = _q("SELECT * FROM invoices WHERE status='overdue' ORDER BY due_date, id")
    return {"title": "Overdue Invoices",
            "headers": ["Invoice", "Customer", "Phone", "Due", "Days Overdue", "Balance"],
            "rows": [[r["number"], r["cust_name"], r["cust_phone"], fmt_date(r["due_date"]),
                      str((today - date.fromisoformat(r["due_date"])).days), money(r["total"] - r["amount_paid"], s)]
                     for r in rows],
            "totals": [("Total overdue", money(sum(r["total"] - r["amount_paid"] for r in rows), s))]}


def aging_report() -> dict:
    refresh_statuses()
    s, today = _sym(), date.fromisoformat(today_iso())
    rows = _q("SELECT * FROM invoices WHERE status IN ('unpaid','partial','overdue') AND total > amount_paid "
              "ORDER BY due_date, id")
    tot = [0] * 5
    out = []
    for r in rows:
        over = (today - date.fromisoformat(r["due_date"])).days
        i, bal = _bucket(over), r["total"] - r["amount_paid"]
        tot[i] += bal
        out.append([r["number"], r["cust_name"], fmt_date(r["due_date"]), str(max(over, 0)), AGING_BUCKETS[i], money(bal, s)])
    return {"title": "Receivables Aging", "headers": ["Invoice", "Customer", "Due", "Days Overdue", "Bucket", "Balance"],
            "rows": out, "totals": [(n, money(v, s)) for n, v in zip(AGING_BUCKETS, tot)] + [("Total", money(sum(tot), s))]}


def expenses_report(a=None, b=None) -> dict:
    s = _sym()
    rows = list_expenses("", "All", a, b)
    by = {}
    for r in rows:
        by[r["category"]] = by.get(r["category"], 0) + r["amount"]
    return {"title": "Expenses Report", "headers": ["Date", "Category", "Vendor", "Description", "Amount"],
            "rows": [[fmt_date(r["expense_date"]), r["category"], r["vendor"], r["description"], money(r["amount"], s)]
                     for r in rows],
            "totals": [("Total expenses", money(sum(r["amount"] for r in rows), s))] +
                      [(f"  {k}", money(v, s)) for k, v in sorted(by.items(), key=lambda x: -x[1])]}


def tax_report(a=None, b=None) -> dict:
    s = _sym()
    rng, args = _rng("issue_date", a, b)
    rows = _q(f"SELECT substr(issue_date,1,7) m, COUNT(*) n, SUM(subtotal - discount_amount) base, SUM(tax_amount) tax, "
              f"SUM(total) total FROM invoices WHERE status NOT IN ('draft','void'){rng} GROUP BY m ORDER BY m", args)
    return {"title": "Tax Summary", "headers": ["Month", "Invoices", "Taxable Sales", "Tax Charged", "Total Billed"],
            "rows": [[f"{r['m'][5:]}-{r['m'][:4]}", str(r["n"]), money(r["base"], s), money(r["tax"], s),
                      money(r["total"], s)] for r in rows],
            "totals": [("Taxable sales", money(sum(r["base"] for r in rows), s)),
                       ("Total tax charged", money(sum(r["tax"] for r in rows), s))]}


def client_report(a=None, b=None) -> dict:
    refresh_statuses()
    s = _sym()
    rng, args = _rng("issue_date", a, b)
    rows = _q(f"SELECT MAX(cust_name) name, COUNT(*) n, SUM(total) t, SUM(amount_paid) p FROM invoices "
              f"WHERE status NOT IN ('draft','void'){rng} GROUP BY customer_id ORDER BY t DESC", args)
    grand = sum(r["t"] for r in rows) or 1
    return {"title": "Client Performance", "headers": ["Client", "Invoices", "Invoiced", "Paid", "Outstanding", "Share"],
            "rows": [[r["name"], str(r["n"]), money(r["t"], s), money(r["p"], s), money(r["t"] - r["p"], s),
                      f"{r['t'] * 100 / grand:.1f}%"] for r in rows],
            "totals": [("Clients billed", str(len(rows))), ("Total invoiced", money(sum(r["t"] for r in rows), s))]}


def customer_statement(customer_id, a=None, b=None) -> dict:
    refresh_statuses()
    s = _sym()
    cust = _q("SELECT name FROM customers WHERE id=?", (customer_id,))
    name = cust[0]["name"] if cust else "Client"
    invs = _q("SELECT number, issue_date, total FROM invoices WHERE customer_id=? AND status NOT IN ('draft','void')",
              (customer_id,))
    pays = _q("""SELECT p.receipt_no, p.paid_date, p.amount, p.method, i.number FROM payments p
                 JOIN invoices i ON i.id=p.invoice_id WHERE i.customer_id=? AND p.voided=0
                 AND i.status NOT IN ('draft','void')""", (customer_id,))
    ledger = sorted([(r["issue_date"], 0, f"Invoice {r['number']}", r["total"], 0) for r in invs] +
                    [(r["paid_date"], 1, f"Payment {r['receipt_no']} ({r['method']}) for {r['number']}", 0, r["amount"])
                     for r in pays])
    opening = sum(d - c for (day, _, _, d, c) in ledger if a and day < a)
    balance, rows = opening, []
    if a:
        rows.append([fmt_date(a), "Opening balance", "", "", money(opening, s)])
    td = tc = 0
    for day, _, desc, debit, credit in ledger:
        if (a and day < a) or (b and day > b):
            continue
        balance += debit - credit
        td += debit
        tc += credit
        rows.append([fmt_date(day), desc, money(debit, s) if debit else "", money(credit, s) if credit else "",
                     money(balance, s)])
    return {"title": f"Client Statement - {name}", "headers": ["Date", "Description", "Invoiced", "Paid", "Balance"],
            "rows": rows, "totals": [("Total invoiced", money(td, s)), ("Total paid", money(tc, s)),
                                     ("Closing balance", money(balance, s))]}


def monthly_summary(a=None, b=None) -> dict:
    s = _sym()
    an = analytics(a, b)
    rows = [[f"{m['month'][5:]}-{m['month'][:4]}", money(m["revenue"], s), money(m["collected"], s),
             money(m["expenses"], s), money(m["collected"] - m["expenses"], s)] for m in an["series"]
            if m["revenue"] or m["collected"] or m["expenses"]]
    return {"title": "Monthly Summary", "headers": ["Month", "Invoiced", "Collected", "Expenses", "Net (collected - expenses)"],
            "rows": rows, "totals": [("Total invoiced", money(an["revenue"], s)), ("Total collected", money(an["collected"], s)),
                                     ("Total expenses", money(an["expenses"], s))]}


def export_csv(report, path) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([report["title"]])
        w.writerow(report["headers"])
        w.writerows(report["rows"])
        w.writerow([])
        for label, val in report["totals"]:
            w.writerow([label.strip(), val])


# ------------------------------------------------------------------- backup
REQUIRED_TABLES = {"settings", "customers", "products", "invoices", "invoice_items", "payments", "audit_events"}


class BackupError(Exception):
    pass


def default_backup_name() -> str:
    return f"InvoicePilot_backup_{datetime.now():%Y%m%d_%H%M%S}.db"


def backup_database(dest) -> Path:
    dest = Path(dest)
    src = connect()
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    except Exception as exc:
        raise BackupError(f"Backup failed: {exc}") from exc
    finally:
        src.close()
    return dest


def validate_backup(path) -> None:
    path = Path(path)
    if not path.is_file():
        raise BackupError("Backup file not found.")
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("The file failed the SQLite integrity check.")
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"Not a valid SQLite database: {exc}") from exc
    if REQUIRED_TABLES - tables:
        raise BackupError("Not an Invoice Pilot backup (missing: " + ", ".join(sorted(REQUIRED_TABLES - tables)) + ").")


def restore_database(src):
    """Validate, keep a safety copy of the current DB, replace it, then upgrade its schema."""
    validate_backup(src)
    live, safety = db_path(), None
    if live.exists():
        safety = sub_dir("backups") / f"pre_restore_{datetime.now():%Y%m%d_%H%M%S}.db"
        backup_database(safety)
    try:
        tmp = live.with_suffix(".restoring")
        shutil.copyfile(src, tmp)
        for ext in ("-wal", "-shm"):
            Path(str(live) + ext).unlink(missing_ok=True)
        tmp.replace(live)
    except Exception as exc:
        raise BackupError(f"Restore failed: {exc}") from exc
    init_db()
    return safety


# ---------------------------------------------------------------------- PDF
from reportlab.lib import colors                                   # noqa: E402
from reportlab.lib.enums import TA_RIGHT                           # noqa: E402
from reportlab.lib.pagesizes import A4, landscape                  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm                                 # noqa: E402
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

NAVY, BLUE, CYAN = colors.HexColor("#0B1530"), colors.HexColor("#2563EB"), colors.HexColor("#06B6D4")
LIGHT, GRID, MUTED = colors.HexColor("#F1F5F9"), colors.HexColor("#E2E8F0"), colors.HexColor("#64748B")
_ss = getSampleStyleSheet()


def _style(name, **kw):
    base = dict(parent=_ss["Normal"], fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#0F172A"))
    base.update(kw)
    return ParagraphStyle(name, **base)


ST = {"n": _style("n"), "muted": _style("muted", textColor=MUTED, fontSize=8.5), "b": _style("b", fontName="Helvetica-Bold"),
      "right": _style("right", alignment=TA_RIGHT), "rightb": _style("rightb", alignment=TA_RIGHT, fontName="Helvetica-Bold"),
      "h": _style("h", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white),
      "hr": _style("hr", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, alignment=TA_RIGHT),
      "title": _style("title", fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=BLUE, alignment=TA_RIGHT),
      "biz": _style("biz", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=NAVY),
      "label": _style("label", fontName="Helvetica-Bold", fontSize=7.5, textColor=BLUE, leading=10)}


def P(text, style="n"):
    return Paragraph(escape(str(text if text is not None else "")).replace("\n", "<br/>"), ST[style])


def _logo(path, max_w=38 * mm, max_h=22 * mm):
    if not path or not os.path.isfile(path):
        return None
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            w, h = im.size
        k = min(max_w / w, max_h / h)
        return Image(path, width=w * k, height=h * k)
    except Exception:
        return None


def _business_block(s):
    lines = [P(s.get("business_name", ""), "biz")]
    for key, pre in (("business_address", ""), ("business_phone", "Phone: "), ("business_whatsapp", "WhatsApp: "),
                     ("business_email", "Email: ")):
        if s.get(key):
            lines.append(P(pre + s[key], "muted"))
    ids = ["NTN: " + s["business_ntn"]] if s.get("business_ntn") else []
    ids += ["STRN: " + s["business_strn"]] if s.get("business_strn") else []
    if ids:
        lines.append(P("   ".join(ids), "muted"))
    return lines


def _header(s, right_rows, width):
    logo = _logo(s.get("logo_path"))
    left = ([logo, Spacer(1, 3 * mm)] if logo else []) + _business_block(s)
    t = Table([[left, right_rows]], colWidths=[width * 0.55, width * 0.45])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _footer_factory(s, label, watermark=None):
    def draw(canvas, doc):
        canvas.saveState()
        w, h = doc.pagesize
        canvas.setFillColor(NAVY)
        canvas.rect(0, h - 6 * mm, w, 6 * mm, stroke=0, fill=1)
        canvas.setFillColor(CYAN)
        canvas.rect(0, h - 6 * mm, w * 0.18, 6 * mm, stroke=0, fill=1)
        canvas.setStrokeColor(GRID)
        canvas.line(15 * mm, 16 * mm, w - 15 * mm, 16 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(15 * mm, 11 * mm, (s.get("invoice_footer") or "").replace("\n", "  ")[:110])
        canvas.drawRightString(w - 15 * mm, 11 * mm, f"{label}  |  Page {doc.page}  |  Invoice Pilot")
        if watermark:
            canvas.setFont("Helvetica-Bold", 90)
            canvas.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.12))
            canvas.translate(w / 2, h / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, watermark)
        canvas.restoreState()
    return draw


def _doc(path, pagesize=A4, title="Document"):
    return SimpleDocTemplate(str(path), pagesize=pagesize, leftMargin=15 * mm, rightMargin=15 * mm,
                             topMargin=14 * mm, bottomMargin=22 * mm, title=title, author=APP_TITLE)


def _fmt_qty(q):
    t = f"{Decimal(str(q)):f}"
    return t.rstrip("0").rstrip(".") if "." in t else t


def generate_doc_pdf(d, s, path, kind="invoice") -> str:
    """Invoice or quotation PDF. d = get_invoice()/get_estimate() dict."""
    quote = kind == "quote"
    sym = s.get("currency_symbol", "Rs.") or "Rs."
    m = lambda v: money(v, sym)
    doc = _doc(path, title=f"{'Quotation' if quote else 'Invoice'} {d['number']}")
    W = doc.width
    if quote:
        status = QUOTE_LABELS[d["status"]].upper()
        rows = [("Quote No.", d["number"], True), ("Issue Date", fmt_date(d["issue_date"]), False),
                ("Valid Until", fmt_date(d["valid_until"]), False), ("Status", status, True)]
    else:
        status = {"unpaid": "UNPAID", "partial": "PARTIALLY PAID"}.get(d["status"], d["status"].upper())
        rows = [("Invoice No.", d["number"], True), ("Issue Date", fmt_date(d["issue_date"]), False),
                ("Due Date", fmt_date(d["due_date"]), False), ("Status", status, True)]
    right = [Paragraph("QUOTATION" if quote else "INVOICE", ST["title"]), Spacer(1, 2 * mm)]
    meta = Table([[P(a, "muted"), P(b, "rightb" if bold else "right")] for a, b, bold in rows],
                 colWidths=[22 * mm, 40 * mm], hAlign="RIGHT")
    meta.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    right.append(meta)
    story = [_header(s, right, W), Spacer(1, 7 * mm)]

    bill = [P("QUOTATION FOR" if quote else "BILL TO", "label"), P(d["cust_name"], "b")]
    for v, pre in ((d["cust_address"], ""), (d["cust_phone"], "Phone: "), (d["cust_email"], "Email: ")):
        if v:
            bill.append(P(pre + v, "muted"))
    ids = " ".join(x for x in (f"NTN: {d['cust_ntn']}" if d["cust_ntn"] else "", f"STRN: {d['cust_strn']}" if d["cust_strn"] else "") if x)
    if ids:
        bill.append(P(ids, "muted"))
    bt = Table([[bill]], colWidths=[W * 0.6])
    bt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                            ("LINEBEFORE", (0, 0), (0, -1), 3, BLUE)]))
    bt.hAlign = "LEFT"
    story += [bt, Spacer(1, 6 * mm)]

    show_tax = any(i["tax_rate"] not in (None, "") for i in d["items"])
    head = [P("#", "h"), P("DESCRIPTION", "h"), P("QTY", "hr"), P("UNIT PRICE", "hr")]
    widths = [9 * mm, None, 18 * mm, 30 * mm]
    if show_tax:
        head.append(P(s.get("tax_label", "Tax").upper() + " %", "hr"))
        widths.append(17 * mm)
    head.append(P("AMOUNT", "hr"))
    widths.append(32 * mm)
    widths[1] = W - sum(w for w in widths if w)
    data = [head]
    for n, it in enumerate(d["items"], 1):
        row = [P(n), P(it["description"]), P(_fmt_qty(it["qty"]), "right"), P(m(it["unit_price"]), "right")]
        if show_tax:
            row.append(P(f"{it['tax_rate']}%" if it["tax_rate"] not in (None, "") else "-", "right"))
        row.append(P(m(it["line_total"]), "right"))
        data.append(row)
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.4, GRID), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [t, Spacer(1, 4 * mm)]

    rows = [[P("Subtotal", "muted"), P(m(d["subtotal"]), "right")]]
    if d["discount_amount"]:
        lab = f"Discount ({_fmt_qty(d['discount_value'])}%)" if d["discount_type"] == "percent" else "Discount"
        rows.append([P(lab, "muted"), P("- " + m(d["discount_amount"]), "right")])
    if d["tax_amount"] or show_tax:
        rows.append([P(s.get("tax_label", "Tax"), "muted"), P(m(d["tax_amount"]), "right")])
    rows.append([P("Grand Total" if not quote else "Quotation Total", "b"), P(m(d["total"]), "rightb")])
    if not quote:
        rows.append([P("Amount Paid", "muted"), P(m(d["amount_paid"]), "right")])
        rows.append([P("Balance Due", "b"), P(m(d["total"] - d["amount_paid"]), "rightb")])
    tt = Table(rows, colWidths=[38 * mm, 42 * mm], hAlign="RIGHT")
    k = len(rows)
    style = [("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
             ("BACKGROUND", (0, k - 1), (-1, k - 1), colors.HexColor("#DBEAFE"))]
    style.append(("LINEABOVE", (0, k - (1 if quote else 3)), (-1, k - (1 if quote else 3)), 0.8, NAVY))
    tt.setStyle(TableStyle(style))
    story.append(KeepTogether(tt))

    live_pay = [p for p in d.get("payments", []) if not p["voided"]]
    if live_pay:
        pr = [[P("PAYMENT", "h"), P("DATE", "h"), P("METHOD", "h"), P("REFERENCE", "h"), P("AMOUNT", "hr")]]
        for p in live_pay:
            pr.append([P(p["receipt_no"]), P(fmt_date(p["paid_date"])), P(p["method"]), P(p["reference"]), P(m(p["amount"]), "right")])
        pt = Table(pr, colWidths=[32 * mm, 26 * mm, 30 * mm, W - 120 * mm, 32 * mm], repeatRows=1)
        pt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE), ("LINEBELOW", (0, 1), (-1, -1), 0.4, GRID),
                                ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [Spacer(1, 6 * mm), P("Payments received", "b"), Spacer(1, 1.5 * mm), pt]

    blocks = [("NOTES", d.get("notes")), ("PAYMENT INSTRUCTIONS", d.get("payment_instructions") if not quote else ""),
              ("TERMS & CONDITIONS", d.get("terms"))]
    for title, text in blocks:
        if (text or "").strip():
            story.append(KeepTogether([Spacer(1, 5 * mm), P(title, "label"), Spacer(1, 1 * mm), P(text, "muted")]))
    if quote:
        story += [Spacer(1, 5 * mm), P(f"This quotation is valid until {fmt_date(d['valid_until'])}.", "muted")]

    wm = "VOID" if d["status"] == "void" else ("DRAFT" if d["status"] == "draft" else None)
    f = _footer_factory(s, d["number"], wm)
    doc.build(story, onFirstPage=f, onLaterPages=f)
    return str(path)


def generate_receipt_pdf(rc, s, path) -> str:
    sym = s.get("currency_symbol", "Rs.") or "Rs."
    doc = _doc(path, title=f"Receipt {rc['receipt_no']}")
    W = doc.width
    right = [Paragraph("PAYMENT RECEIPT", _style("rt", fontName="Helvetica-Bold", fontSize=18, leading=22,
                                                  textColor=BLUE, alignment=TA_RIGHT)),
             P(rc["receipt_no"], "rightb"), P("Date: " + fmt_date(rc["paid_date"]), "right")]
    story = [_header(s, right, W), Spacer(1, 10 * mm)]
    rows = [("Received from", rc["cust_name"]), ("Against invoice", rc["invoice_number"]), ("Payment method", rc["method"]),
            ("Reference", rc["reference"] or "-"), ("Amount received", money(rc["amount"], sym)),
            ("Invoice total", money(rc["invoice_total"], sym)), ("Total paid to date", money(rc["invoice_paid"], sym)),
            ("Balance remaining", money(rc["invoice_total"] - rc["invoice_paid"], sym))]
    if rc.get("notes"):
        rows.append(("Notes", rc["notes"]))
    t = Table([[P(a, "muted"), P(b, "b" if a == "Amount received" else "n")] for a, b in rows], colWidths=[50 * mm, W - 50 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, GRID), ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#DBEAFE"))]))
    story += [t, Spacer(1, 12 * mm), P("This is a computer-generated receipt and does not require a signature.", "muted")]
    if rc.get("voided"):
        story.append(P("NOTE: This payment has been reversed.", "b"))
    f = _footer_factory(s, rc["receipt_no"], "REVERSED" if rc.get("voided") else None)
    doc.build(story, onFirstPage=f, onLaterPages=f)
    return str(path)


def generate_report_pdf(report, s, path, period="") -> str:
    ps = landscape(A4) if len(report["headers"]) > 5 else A4
    doc = _doc(path, ps, report["title"])
    W = doc.width
    story = [_header(s, [P(report["title"], "rightb"), P(period, "right"), P("Generated " + fmt_date(today_iso()), "right")], W),
             Spacer(1, 6 * mm)]
    n = len(report["headers"])
    data = [[P(h, "h") for h in report["headers"]]] + [[P(c, "n") for c in r] for r in report["rows"]]
    if not report["rows"]:
        data.append([P("No records for this selection.", "muted")] + [P("")] * (n - 1))
    t = Table(data, colWidths=[W / n] * n, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.3, GRID), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [t, Spacer(1, 5 * mm)]
    if report["totals"]:
        tt = Table([[P(a.strip(), "b"), P(b, "rightb")] for a, b in report["totals"]], colWidths=[60 * mm, 45 * mm], hAlign="RIGHT")
        tt.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.8, NAVY), ("BACKGROUND", (0, 0), (-1, -1), LIGHT)]))
        story.append(KeepTogether(tt))
    f = _footer_factory(s, report["title"][:40])
    doc.build(story, onFirstPage=f, onLaterPages=f)
    return str(path)
