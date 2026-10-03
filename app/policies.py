from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import Invoice, Policy, User
from .web import flash, render

router = APIRouter(prefix="/policies", tags=["policies"])

VALID_TYPES = ("percent", "fixed")


def _next_code(db: Session) -> str:
    n = db.query(Policy).count() + 1
    while db.query(Policy).filter(Policy.policy_code == f"CS{n:04d}").first():
        n += 1
    return f"CS{n:04d}"


def _validate(name: str, dtype: str, dvalue: str, status: str) -> list[str]:
    errors = []
    if not name or len(name.strip()) < 3:
        errors.append("Tên chính sách phải có ít nhất 3 ký tự")
    if dtype not in VALID_TYPES:
        errors.append("Loại giảm phải là 'percent' hoặc 'fixed'")
    if status not in ("active", "inactive"):
        errors.append("Trạng thái không hợp lệ")
    try:
        v = float(dvalue)
        if v <= 0:
            errors.append("Giá trị giảm phải lớn hơn 0")
        if dtype == "percent" and v > 100:
            errors.append("Giảm % không thể vượt quá 100")
    except (ValueError, TypeError):
        errors.append("Giá trị giảm không hợp lệ")
    return errors


@router.get("")
def list_policies(request: Request,
                  q: str = "",
                  status: str = "",
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    query = db.query(Policy)

    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Policy.policy_code.ilike(like),
            Policy.policy_name.ilike(like),
        ))
    if status in ("active", "inactive"):
        query = query.filter(Policy.status == status)

    policies = query.order_by(Policy.policy_code).all()

    # Thống kê số hóa đơn đang dùng mỗi policy
    usage = {}
    for p in policies:
        usage[p.policy_id] = (db.query(Invoice)
                              .filter(Invoice.policy_id == p.policy_id).count())

    return render(request, "policies_list.html", user=user,
                  policies=policies, q=q, status=status, usage=usage)


@router.get("/new")
def new_form(request: Request,
             user: User = Depends(require_roles("admin"))):
    return render(request, "policy_form.html", user=user,
                  mode="new", form={})


@router.post("/new")
def create_policy(request: Request,
                  policy_name: str = Form(""),
                  discount_type: str = Form("percent"),
                  discount_value: str = Form("0"),
                  description: str = Form(""),
                  status: str = Form("active"),
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    policy_name = policy_name.strip()
    description = description.strip()

    form = {"policy_name": policy_name, "discount_type": discount_type,
            "discount_value": discount_value, "description": description,
            "status": status}

    errors = _validate(policy_name, discount_type, discount_value, status)
    if errors:
        return render(request, "policy_form.html", user=user,
                      mode="new", form=form,
                      error="; ".join(errors), status_code=400)

    p = Policy(
        policy_code=_next_code(db),
        policy_name=policy_name,
        discount_type=discount_type,
        discount_value=float(discount_value),
        description=description or None,
        status=status,
    )
    db.add(p)
    db.commit()

    flash(request, f"Đã thêm chính sách {policy_name} ({p.policy_code})")
    return RedirectResponse("/policies", status_code=303)


@router.get("/{policy_id}/edit")
def edit_form(policy_id: int,
              request: Request,
              user: User = Depends(require_roles("admin")),
              db: Session = Depends(get_db)):
    p = db.get(Policy, policy_id)
    if not p:
        return render(request, "404.html", user=user, status_code=404)

    form = {
        "policy_name": p.policy_name,
        "discount_type": p.discount_type,
        "discount_value": f"{p.discount_value:.0f}",
        "description": p.description or "",
        "status": p.status,
    }
    return render(request, "policy_form.html", user=user,
                  mode="edit", policy=p, form=form)


@router.post("/{policy_id}/edit")
def update_policy(policy_id: int,
                  request: Request,
                  policy_name: str = Form(""),
                  discount_type: str = Form("percent"),
                  discount_value: str = Form("0"),
                  description: str = Form(""),
                  status: str = Form("active"),
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    p = db.get(Policy, policy_id)
    if not p:
        return render(request, "404.html", user=user, status_code=404)

    policy_name = policy_name.strip()
    description = description.strip()

    form = {"policy_name": policy_name, "discount_type": discount_type,
            "discount_value": discount_value, "description": description,
            "status": status}

    errors = _validate(policy_name, discount_type, discount_value, status)
    if errors:
        return render(request, "policy_form.html", user=user,
                      mode="edit", policy=p, form=form,
                      error="; ".join(errors), status_code=400)

    p.policy_name = policy_name
    p.discount_type = discount_type
    p.discount_value = float(discount_value)
    p.description = description or None
    p.status = status
    db.commit()

    flash(request, f"Đã cập nhật chính sách {policy_name}")
    return RedirectResponse("/policies", status_code=303)


@router.post("/{policy_id}/toggle")
def toggle_policy(policy_id: int,
                  request: Request,
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    p = db.get(Policy, policy_id)
    if not p:
        return render(request, "404.html", user=user, status_code=404)
    p.status = "inactive" if p.status == "active" else "active"
    db.commit()
    label = "kích hoạt" if p.status == "active" else "tắt"
    flash(request, f"Đã {label} chính sách {p.policy_name}")
    return RedirectResponse("/policies", status_code=303)


@router.post("/{policy_id}/delete")
def delete_policy(policy_id: int,
                  request: Request,
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    p = db.get(Policy, policy_id)
    if not p:
        return render(request, "404.html", user=user, status_code=404)

    # Không xóa nếu đang được dùng
    used = db.query(Invoice).filter(Invoice.policy_id == policy_id).count()
    if used > 0:
        flash(request, f"Không thể xóa: chính sách đang được áp dụng cho {used} hóa đơn. "
                       f"Hãy tắt (inactive) thay vì xóa.", kind="err")
        return RedirectResponse("/policies", status_code=303)

    name = p.policy_name
    db.delete(p)
    db.commit()
    flash(request, f"Đã xóa chính sách {name}")
    return RedirectResponse("/policies", status_code=303)