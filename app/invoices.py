from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import ClassRoom, Invoice, Payment, Policy, Student, User
from .web import flash, render

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _invoice_query(db: Session, q: str = "", status: str = ""):
    query = (db.query(Invoice)
             .join(Student, Invoice.student_id == Student.student_id)
             .join(User, Student.user_id == User.user_id)
             .join(ClassRoom, Invoice.class_id == ClassRoom.class_id))
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            User.full_name.ilike(like),
            Student.student_code.ilike(like),
            Invoice.invoice_code.ilike(like),
            ClassRoom.class_code.ilike(like),
        ))
    if status in ("unpaid", "partial", "paid"):
        query = query.filter(Invoice.status == status)
    return query


@router.get("")
def list_invoices(request: Request,
                  q: str = "",
                  status: str = "",
                  user: User = Depends(require_roles("admin", "consultant")),
                  db: Session = Depends(get_db)):
    invoices = (_invoice_query(db, q, status)
                .order_by(Invoice.created_at.desc()).all())
    return render(request, "invoices_list.html", user=user,
                  invoices=invoices, q=q, status=status)


@router.get("/{invoice_id}")
def invoice_detail(invoice_id: int,
                   request: Request,
                   user: User = Depends(require_roles("admin", "consultant")),
                   db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        return render(request, "404.html", user=user, status_code=404)

    # Danh sách policy active để áp dụng
    policies = (db.query(Policy)
                .filter(Policy.status == "active")
                .order_by(Policy.policy_code).all())

    return render(request, "invoice_detail.html", user=user,
                  inv=inv, policies=policies)


@router.post("/{invoice_id}/pay")
def record_payment(invoice_id: int,
                   request: Request,
                   amount: float = Form(...),
                   method: str = Form(...),
                   note: str = Form(""),
                   user: User = Depends(require_roles("admin", "consultant")),
                   db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        return render(request, "404.html", user=user, status_code=404)

    errors: list[str] = []
    if amount <= 0:
        errors.append("Số tiền phải lớn hơn 0")
    elif amount > inv.remaining_amount:
        errors.append(f"Số tiền ({amount:,.0f} đ) vượt quá số còn lại "
                      f"({inv.remaining_amount:,.0f} đ)")
    if method not in ("cash", "transfer"):
        errors.append("Phương thức thanh toán không hợp lệ")

    if errors:
        flash(request, " | ".join(errors), kind="err")
        return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)

    pmt = Payment(invoice_id=invoice_id, amount=amount,
                  method=method, note=note.strip() or None,
                  created_by=user.user_id)
    db.add(pmt)

    inv.paid_amount += amount
    if inv.paid_amount >= inv.final_amount:
        inv.paid_amount = inv.final_amount
        inv.status = "paid"
    else:
        inv.status = "partial"

    db.commit()
    flash(request, f"Đã ghi nhận thanh toán {amount:,.0f} đ cho hóa đơn "
                   f"{inv.invoice_code}. "
                   f"{'Đã thanh toán đủ.' if inv.status == 'paid' else f'Còn lại: {inv.remaining_amount:,.0f} đ.'}")
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.post("/{invoice_id}/apply-policy")
def apply_policy(invoice_id: int,
                 request: Request,
                 policy_id: str = Form(""),
                 user: User = Depends(require_roles("admin", "consultant")),
                 db: Session = Depends(get_db)):
    """Áp dụng hoặc bỏ chính sách giảm giá cho hóa đơn."""
    inv = db.get(Invoice, invoice_id)
    if not inv:
        return render(request, "404.html", user=user, status_code=404)

    if inv.paid_amount > 0:
        flash(request, "Không thể đổi chính sách khi học viên đã thanh toán.", kind="err")
        return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)

    if not policy_id or policy_id == "none":
        inv.policy_id = None
        inv.discount_amount = 0
        inv.status = "unpaid"
        db.commit()
        flash(request, "Đã bỏ chính sách giảm giá.")
        return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)

    policy = db.get(Policy, int(policy_id))
    if not policy or policy.status != "active":
        flash(request, "Chính sách không hợp lệ.", kind="err")
        return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)

    discount = policy.apply_to(inv.total_amount)
    inv.policy_id = policy.policy_id
    inv.discount_amount = discount
    db.commit()

    flash(request, f"Đã áp dụng '{policy.policy_name}'. "
                   f"Giảm {discount:,.0f} đ. "
                   f"Số tiền phải thu: {inv.final_amount:,.0f} đ.")
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)