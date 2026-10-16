"""Rule tests for Invoice Pilot's data layer. Run:  python -m pytest tests.py -q

Every test uses a throwaway database (INVOICEPILOT_DATA_DIR), never your real data.
"""
from datetime import date, timedelta

import pytest

import database as db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("INVOICEPILOT_DATA_DIR", str(tmp_path))
    db.init_db()
    return tmp_path


# ----------------------------------------------------------------- helpers
def iso(offset_days=0):
    return (date.fromisoformat(db.today_iso()) + timedelta(days=offset_days)).isoformat()


def make_customer(name="Acme Traders"):
    return db.save_customer({"name": name, "phone": "0300-1234567", "email": "", "address": "Okara"})


def make_invoice(unit_price="1000", qty="1", issue=None, due=None, tax=None, draft=False, **extra):
    cid = extra.pop("customer_id", None) or make_customer()
    data = {"customer_id": cid, "issue_date": issue or iso(0), "due_date": due or iso(14)}
    data.update(extra)
    item = {"description": "Design work", "qty": qty, "unit_price_rs": unit_price, "tax_rate": tax}
    return db.save_invoice(data, [item], as_draft=draft)


def make_quote(unit_price="2500"):
    cid = make_customer("Quote Client")
    data = {"customer_id": cid, "issue_date": iso(0), "valid_until": iso(30)}
    return db.save_estimate(data, [{"description": "Website", "qty": "1", "unit_price_rs": unit_price}])


def pay(inv_id, rupees, ref=""):
    return db.add_payment(inv_id, db.to_minor(rupees), iso(0), "Cash", reference=ref)


# ------------------------------------------------------------------- money
def test_to_minor_rounds_half_up_and_accepts_commas():
    assert db.to_minor("10.005") == 1001
    assert db.to_minor("1,234.50") == 123450
    assert db.to_minor(0) == 0


def test_money_formatting():
    assert db.money(123456) == "Rs. 1,234.56"
    assert db.money(-500) == "-Rs. 5.00"
    assert db.plain(5) == "0.05"


def test_short_num():
    assert db.short_num(150000) == "2K" or db.short_num(150000) == "1.5K"
    assert db.short_num(0) == "0"


def test_totals_with_percent_discount_and_tax():
    items = [{"qty": "2", "unit_price": 50000, "tax_rate": "10"}]   # 2 x 500.00 = 1000.00
    t = db.calculate_totals(items, "percent", "10")                   # -100.00 -> taxable 900.00
    assert t["subtotal"] == 100000
    assert t["discount_amount"] == 10000
    assert t["tax_amount"] == 9000                                    # 10% of 900.00
    assert t["total"] == 100000 - 10000 + 9000


def test_totals_fixed_discount_and_limits():
    items = [{"qty": "1", "unit_price": 100000, "tax_rate": None}]
    assert db.calculate_totals(items, "fixed", "250")["total"] == 75000
    with pytest.raises(db.ValidationError):
        db.calculate_totals(items, "fixed", "1500")                   # more than subtotal
    with pytest.raises(db.ValidationError):
        db.calculate_totals(items, "percent", "101")


def test_fractional_quantity_rounds_per_line():
    assert db.line_total("1.5", 33333) == 50000                       # 499.995 -> 500.00


# ------------------------------------------------------------------ status
def test_compute_status_rules():
    today = "2026-06-15"
    assert db.compute_status(1000, 0, "2026-06-30", "unpaid", today) == "unpaid"
    assert db.compute_status(1000, 400, "2026-06-30", "unpaid", today) == "partial"
    assert db.compute_status(1000, 1000, "2026-06-01", "unpaid", today) == "paid"
    assert db.compute_status(1000, 0, "2026-06-01", "unpaid", today) == "overdue"
    assert db.compute_status(1000, 400, "2026-06-01", "partial", today) == "overdue"
    assert db.compute_status(1000, 0, "2026-06-01", "draft", today) == "draft"
    assert db.compute_status(1000, 0, "2026-06-01", "void", today) == "void"
    assert db.compute_status(1000, 0, "2026-06-15", "unpaid", today) == "unpaid"   # due today is not overdue


# ---------------------------------------------------------------- payments
def test_invoice_to_partial_to_full_payment():
    inv_id = make_invoice("1000")
    inv = db.get_invoice(inv_id)
    assert inv["status"] == "unpaid" and inv["total"] == 100000 and inv["balance"] == 100000

    pay(inv_id, "400")
    inv = db.get_invoice(inv_id)
    assert inv["status"] == "partial"
    assert inv["amount_paid"] == 40000 and inv["balance"] == 60000

    pay(inv_id, "600")
    inv = db.get_invoice(inv_id)
    assert inv["status"] == "paid"
    assert inv["amount_paid"] == 100000 and inv["balance"] == 0


def test_overpayment_zero_and_future_date_blocked():
    inv_id = make_invoice("1000")
    with pytest.raises(db.ValidationError):
        pay(inv_id, "1000.01")
    with pytest.raises(db.ValidationError):
        db.add_payment(inv_id, 0, iso(0), "Cash")
    with pytest.raises(db.ValidationError):
        db.add_payment(inv_id, 100, iso(1), "Cash")
    assert db.get_invoice(inv_id)["amount_paid"] == 0


def test_identical_payment_twice_is_blocked_as_duplicate():
    inv_id = make_invoice("1000")
    pay(inv_id, "100", ref="X1")
    with pytest.raises(db.ValidationError):
        pay(inv_id, "100", ref="X1")
    pay(inv_id, "100", ref="X2")                                      # different reference is fine
    assert db.get_invoice(inv_id)["amount_paid"] == 20000


def test_cannot_pay_draft_or_void_invoice():
    draft = make_invoice("500", draft=True)
    with pytest.raises(db.ValidationError):
        pay(draft, "100")
    inv_id = make_invoice("500")
    db.void_invoice(inv_id)
    with pytest.raises(db.ValidationError):
        pay(inv_id, "100")


def test_receipt_numbers_are_unique_and_sequential():
    inv_id = make_invoice("1000")
    p1, p2 = pay(inv_id, "100"), pay(inv_id, "200")
    r1, r2 = db.get_receipt_data(p1)["receipt_no"], db.get_receipt_data(p2)["receipt_no"]
    assert r1 != r2 and r1 < r2


def test_reversing_a_payment_restores_balance_and_status():
    inv_id = make_invoice("1000")
    p1 = pay(inv_id, "400")
    p2 = pay(inv_id, "600")
    assert db.get_invoice(inv_id)["status"] == "paid"

    db.void_payment(p2)
    inv = db.get_invoice(inv_id)
    assert inv["status"] == "partial" and inv["balance"] == 60000

    db.void_payment(p1)
    inv = db.get_invoice(inv_id)
    assert inv["status"] == "unpaid" and inv["amount_paid"] == 0 and inv["balance"] == 100000
    with pytest.raises(db.ValidationError):
        db.void_payment(p1)                                           # cannot reverse twice


# ----------------------------------------------------------------- overdue
def test_overdue_detection_and_recovery():
    inv_id = make_invoice("1000", issue=iso(-30), due=iso(-5))
    assert db.get_invoice(inv_id)["status"] == "overdue"             # set at creation
    assert [r["number"] for r in db.list_invoices(status="Overdue")] == [db.get_invoice(inv_id)["number"]]

    p = pay(inv_id, "300")
    assert db.get_invoice(inv_id)["status"] == "overdue"             # partial payment does not clear it
    pay(inv_id, "700")
    assert db.get_invoice(inv_id)["status"] == "paid"

    db.void_payment(db.list_payments()[0]["id"])                     # newest payment reversed
    assert db.get_invoice(inv_id)["status"] == "overdue"


def test_stored_unpaid_invoice_flips_to_overdue_on_refresh():
    inv_id = make_invoice("1000")
    with db.transaction() as c:                                       # simulate the due date passing
        c.execute("UPDATE invoices SET due_date=? WHERE id=?", (iso(-1), inv_id))
    db.refresh_statuses()
    assert db.get_invoice(inv_id)["status"] == "overdue"
    assert db.analytics()["overdue_count"] == 1


# --------------------------------------------------------------- lifecycle
def test_draft_mark_sent_void_and_delete_rules():
    draft = make_invoice("500", draft=True)
    assert db.get_invoice(draft)["status"] == "draft"
    db.mark_sent(draft)
    assert db.get_invoice(draft)["status"] == "unpaid"
    with pytest.raises(db.ValidationError):
        db.mark_sent(draft)
    with pytest.raises(db.ValidationError):
        db.delete_draft_invoice(draft)                                # no longer a draft
    db.void_invoice(draft)
    with pytest.raises(db.ValidationError):
        db.void_invoice(draft)

    d2 = make_invoice("500", draft=True)
    db.delete_draft_invoice(d2)
    assert db.get_invoice(d2) is None


def test_editing_total_below_paid_amount_is_rejected():
    inv_id = make_invoice("1000")
    pay(inv_id, "800")
    inv = db.get_invoice(inv_id)
    data = {"customer_id": inv["customer_id"], "issue_date": inv["issue_date"], "due_date": inv["due_date"]}
    with pytest.raises(db.ValidationError):
        db.save_invoice(data, [{"description": "x", "qty": "1", "unit_price_rs": "500"}], invoice_id=inv_id)


def test_invoice_numbers_increment():
    a, b = make_invoice("10"), make_invoice("10")
    assert db.get_invoice(a)["number"] != db.get_invoice(b)["number"]
    assert db.get_invoice(b)["number"].endswith("0002")


# -------------------------------------------------------------- quotations
def test_quote_must_be_accepted_then_converts_exactly_once():
    qid = make_quote("2500")
    with pytest.raises(db.ValidationError):
        db.convert_estimate(qid)                                      # still a draft

    db.set_estimate_status(qid, "accepted")
    inv_id = db.convert_estimate(qid)

    q, inv = db.get_estimate(qid), db.get_invoice(inv_id)
    assert q["status"] == "converted" and q["converted_invoice_id"] == inv_id
    assert inv["total"] == q["total"] == 250000
    assert inv["status"] == "unpaid" and inv["customer_id"] == q["customer_id"]
    assert [i["description"] for i in inv["items"]] == ["Website"]

    with pytest.raises(db.ValidationError):
        db.convert_estimate(qid)                                      # second conversion blocked
    assert len(db.list_invoices()) == 1                               # and no duplicate invoice appeared
    with pytest.raises(db.ValidationError):
        db.set_estimate_status(qid, "declined")
    with pytest.raises(db.ValidationError):
        db.delete_estimate(qid)


def test_declined_quote_cannot_convert():
    qid = make_quote()
    db.set_estimate_status(qid, "declined")
    with pytest.raises(db.ValidationError):
        db.convert_estimate(qid)


# ------------------------------------------------- expenses and dashboard
def test_expenses_drive_dashboard_and_net_profit():
    assert db.analytics()["net_profit"] is None                       # nothing yet

    inv_id = make_invoice("1000")
    pay(inv_id, "600")
    db.save_expense({"amount": "250", "expense_date": iso(0), "category": "Rent", "vendor": "Landlord"})
    a = db.analytics()
    assert a["revenue"] == 100000 and a["collected"] == 60000
    assert a["expenses"] == 25000 and a["net_profit"] == 35000
    assert a["outstanding"] == 40000
    assert a["series"][-1]["expenses"] == 25000

    exp_id = db.list_expenses()[0]["id"]
    db.delete_expense(exp_id)
    assert db.analytics()["net_profit"] == 60000


def test_voided_payments_and_invoices_leave_the_numbers():
    inv_id = make_invoice("1000")
    p = pay(inv_id, "1000")
    assert db.analytics()["collected"] == 100000
    db.void_payment(p)
    assert db.analytics()["collected"] == 0

    other = make_invoice("700")
    pay(other, "100")
    db.void_invoice(other)
    a = db.analytics()
    assert a["collected"] == 0 and a["revenue"] == 100000


def test_date_range_filters_dashboard():
    make_invoice("1000", issue=iso(-90), due=iso(-80))
    make_invoice("300", issue=iso(0), due=iso(14))
    assert db.analytics(iso(-10), iso(0))["revenue"] == 30000
    assert db.analytics(iso(-100), iso(-60))["revenue"] == 100000
    assert db.analytics()["revenue"] == 130000


def test_aging_buckets_total_matches_outstanding():
    make_invoice("100", issue=iso(-100), due=iso(-95))
    make_invoice("200", issue=iso(-40), due=iso(-35))
    make_invoice("300")
    a = db.analytics()
    assert sum(b[1] for b in a["aging"]) == a["outstanding"] == 60000


# ---------------------------------------------- reports, CSV, PDF, backup
def test_csv_export_and_reports(tmp_path):
    inv_id = make_invoice("1000")
    pay(inv_id, "250")
    for rep in (db.sales_report(), db.payments_report(), db.outstanding_report(), db.overdue_report(),
                db.monthly_summary()):
        assert rep["title"] and rep["headers"]
    out = tmp_path / "sales.csv"
    db.export_csv(db.sales_report(), out)
    text = out.read_text(encoding="utf-8-sig")
    assert "Total invoiced" in text and "1,000.00" in text


def test_pdfs_are_generated(tmp_path):
    inv_id = make_invoice("1000", tax="17")
    pid = pay(inv_id, "400")
    s = db.get_settings()
    inv_pdf = db.generate_doc_pdf(db.get_invoice(inv_id), s, str(tmp_path / "inv.pdf"), kind="invoice")
    qt_pdf = db.generate_doc_pdf(db.get_estimate(make_quote()), s, str(tmp_path / "qt.pdf"), kind="quote")
    rc_pdf = db.generate_receipt_pdf(db.get_receipt_data(pid), s, str(tmp_path / "rc.pdf"))
    rp_pdf = db.generate_report_pdf(db.sales_report(), s, str(tmp_path / "rp.pdf"), period="All time")
    for path in (inv_pdf, qt_pdf, rc_pdf, rp_pdf):
        data = open(path, "rb").read()
        assert data.startswith(b"%PDF") and len(data) > 1000


def test_backup_and_restore_round_trip(tmp_path):
    inv_id = make_invoice("1000")
    pay(inv_id, "300")
    backup = db.backup_database(tmp_path / "backup.db")
    db.validate_backup(backup)

    pay(inv_id, "200")                                                # change after the backup
    assert db.get_invoice(inv_id)["amount_paid"] == 50000
    db.restore_database(backup)
    assert db.get_invoice(inv_id)["amount_paid"] == 30000
    assert any(db.sub_dir("backups").glob("pre_restore_*.db"))        # safety copy kept


def test_restore_rejects_garbage(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_text("not a database")
    with pytest.raises(db.BackupError):
        db.restore_database(junk)
    with pytest.raises(db.BackupError):
        db.restore_database(tmp_path / "missing.db")
