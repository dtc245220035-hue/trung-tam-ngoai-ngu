"""Test module học phí (yêu cầu đề bài)."""
import pytest

from app.models import ClassRoom, Enrollment, Invoice, Payment, Student


def _get_unpaid_invoice(db):
    """Lấy 1 hóa đơn chưa đóng đủ."""
    return (db.query(Invoice)
            .filter(Invoice.status != "paid")
            .order_by(Invoice.invoice_id)
            .first())


# ============ TC-PAY-01: Thanh toán một phần ============
def test_payment_partial(admin_client, db):
    inv = _get_unpaid_invoice(db)
    if not inv:
        pytest.skip("Không có hóa đơn chưa đóng")

    iid = inv.invoice_id
    remaining = inv.remaining_amount
    paid_before = inv.paid_amount
    if remaining <= 0:
        pytest.skip("Hóa đơn đã đủ")

    half = remaining / 2
    r = admin_client.post(f"/invoices/{iid}/pay", data={
        "amount": half,
        "method": "cash",
        "note": "Test partial",
    }, follow_redirects=False)
    assert r.status_code == 303

    db.expire_all()
    inv = db.get(Invoice, iid)
    assert inv.status == "partial"
    assert abs(inv.paid_amount - (paid_before + half)) < 0.01

# ============ TC-PAY-02: Thanh toán đủ ============
def test_payment_full(admin_client, db):
    inv = _get_unpaid_invoice(db)
    if not inv:
        pytest.skip("Không có hóa đơn chưa đóng")

    iid = inv.invoice_id
    remaining = inv.remaining_amount

    r = admin_client.post(f"/invoices/{iid}/pay", data={
        "amount": remaining,
        "method": "transfer",
        "note": "Test full",
    }, follow_redirects=False)
    assert r.status_code == 303

    db.expire_all()
    inv = db.get(Invoice, iid)
    assert inv.status == "paid"
    assert abs(inv.paid_amount - inv.total_amount) < 0.01


# ============ TC-PAY-03: Thanh toán vượt số nợ → bị chặn ============
def test_payment_over_remaining(admin_client, db):
    inv = _get_unpaid_invoice(db)
    if not inv:
        pytest.skip("Không có hóa đơn chưa đóng")

    iid = inv.invoice_id
    over = inv.remaining_amount + 1000

    paid_before = inv.paid_amount
    r = admin_client.post(f"/invoices/{iid}/pay", data={
        "amount": over,
        "method": "cash",
        "note": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    db.expire_all()
    inv = db.get(Invoice, iid)
    assert abs(inv.paid_amount - paid_before) < 0.01, "Không được cộng tiền khi vượt"


# ============ TC-PAY-04: Thanh toán số âm → bị chặn ============
def test_payment_negative(admin_client, db):
    inv = _get_unpaid_invoice(db)
    if not inv:
        pytest.skip("Không có hóa đơn chưa đóng")

    paid_before = inv.paid_amount
    r = admin_client.post(f"/invoices/{inv.invoice_id}/pay", data={
        "amount": -50000,
        "method": "cash",
        "note": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    db.expire_all()
    inv = db.get(Invoice, inv.invoice_id)
    assert abs(inv.paid_amount - paid_before) < 0.01


# ============ TC-PAY-05: Thanh toán hóa đơn đã đủ → bị chặn ============
def test_payment_on_paid_invoice(admin_client, db):
    inv = db.query(Invoice).filter(Invoice.status == "paid").first()
    if not inv:
        pytest.skip("Không có hóa đơn đã đủ")

    paid_before = inv.paid_amount
    r = admin_client.post(f"/invoices/{inv.invoice_id}/pay", data={
        "amount": 100000,
        "method": "cash",
        "note": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    db.expire_all()
    inv = db.get(Invoice, inv.invoice_id)
    assert abs(inv.paid_amount - paid_before) < 0.01


# ============ TC-PAY-06: Phương thức không hợp lệ → bị chặn ============
def test_payment_invalid_method(admin_client, db):
    inv = _get_unpaid_invoice(db)
    if not inv:
        pytest.skip("Không có hóa đơn chưa đóng")

    paid_before = inv.paid_amount
    r = admin_client.post(f"/invoices/{inv.invoice_id}/pay", data={
        "amount": 100000,
        "method": "bitcoin",  # không hợp lệ
        "note": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    db.expire_all()
    inv = db.get(Invoice, inv.invoice_id)
    assert abs(inv.paid_amount - paid_before) < 0.01