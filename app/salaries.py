from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import Salary, Teacher, User
from .web import flash, render

router = APIRouter(prefix="/salaries", tags=["salaries"])


def _validate(month: str, base: str, hours: str, rate: str,
              bonus: str, deduction: str) -> list[str]:
    errors = []
    # month format YYYY-MM
    if len(month) != 7 or month[4] != "-":
        errors.append("Tháng phải có định dạng YYYY-MM")
    try:
        float(base)
        float(hours)
        float(rate)
        float(bonus)
        float(deduction)
    except (ValueError, TypeError):
        errors.append("Các trường số không hợp lệ")
    return errors


@router.get("")
def list_salaries(request: Request,
                  q: str = "",
                  month: str = "",
                  status: str = "",
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    query = (db.query(Salary)
             .join(Teacher, Salary.teacher_id == Teacher.teacher_id)
             .join(User, Teacher.user_id == User.user_id))

    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            User.full_name.ilike(like),
            Teacher.teacher_code.ilike(like),
        ))
    if month:
        query = query.filter(Salary.month == month)
    if status in ("pending", "paid"):
        query = query.filter(Salary.status == status)

    salaries = query.order_by(Salary.month.desc(), Teacher.teacher_code).all()

    total_paid = sum(s.total_salary for s in salaries if s.status == "paid")
    total_pending = sum(s.total_salary for s in salaries if s.status == "pending")

    # Danh sách tháng có sẵn để filter
    months = sorted({s.month for s in db.query(Salary).all()}, reverse=True)

    return render(request, "salaries_list.html", user=user,
                  salaries=salaries, q=q, month=month, status=status,
                  months=months, total_paid=total_paid, total_pending=total_pending)


@router.get("/new")
def new_form(request: Request,
             user: User = Depends(require_roles("admin")),
             db: Session = Depends(get_db)):
    teachers = (db.query(Teacher).filter(Teacher.status == "active")
                .join(User, Teacher.user_id == User.user_id)
                .order_by(Teacher.teacher_code).all())
    return render(request, "salary_form.html", user=user,
                  mode="new", form={}, teachers=teachers)


@router.post("/new")
def create_salary(request: Request,
                  teacher_id: int = Form(...),
                  month: str = Form(""),
                  base_salary: str = Form("0"),
                  teaching_hours: str = Form("0"),
                  hourly_rate: str = Form("0"),
                  bonus: str = Form("0"),
                  deduction: str = Form("0"),
                  note: str = Form(""),
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    month = month.strip()
    note = note.strip()
    errors = _validate(month, base_salary, teaching_hours, hourly_rate, bonus, deduction)

    # Check trùng
    existing = (db.query(Salary)
                .filter(Salary.teacher_id == teacher_id, Salary.month == month).first())
    if existing:
        errors.append(f"GV đã có bảng lương tháng {month}")

    teachers = (db.query(Teacher).filter(Teacher.status == "active")
                .join(User, Teacher.user_id == User.user_id)
                .order_by(Teacher.teacher_code).all())

    form = {"teacher_id": teacher_id, "month": month, "base_salary": base_salary,
            "teaching_hours": teaching_hours, "hourly_rate": hourly_rate,
            "bonus": bonus, "deduction": deduction, "note": note}

    if errors:
        return render(request, "salary_form.html", user=user,
                      mode="new", form=form, teachers=teachers,
                      error="; ".join(errors), status_code=400)

    base = float(base_salary)
    hours = float(teaching_hours)
    rate = float(hourly_rate)
    bn = float(bonus)
    ded = float(deduction)
    total = base + hours * rate + bn - ded

    s = Salary(
        teacher_id=teacher_id,
        month=month,
        base_salary=base,
        teaching_hours=hours,
        hourly_rate=rate,
        bonus=bn,
        deduction=ded,
        total_salary=total,
        status="pending",
        note=note or None,
    )
    db.add(s)
    db.commit()

    flash(request, f"Đã tạo bảng lương tháng {month} — tổng: {total:,.0f} đ")
    return RedirectResponse("/salaries", status_code=303)


@router.get("/{salary_id}/edit")
def edit_form(salary_id: int,
              request: Request,
              user: User = Depends(require_roles("admin")),
              db: Session = Depends(get_db)):
    s = db.get(Salary, salary_id)
    if not s:
        return render(request, "404.html", user=user, status_code=404)

    teachers = (db.query(Teacher).filter(Teacher.status == "active")
                .join(User, Teacher.user_id == User.user_id)
                .order_by(Teacher.teacher_code).all())

    form = {
        "teacher_id": s.teacher_id,
        "month": s.month,
        "base_salary": f"{s.base_salary:.0f}",
        "teaching_hours": s.teaching_hours,
        "hourly_rate": f"{s.hourly_rate:.0f}",
        "bonus": f"{s.bonus:.0f}",
        "deduction": f"{s.deduction:.0f}",
        "note": s.note or "",
    }
    return render(request, "salary_form.html", user=user,
                  mode="edit", salary=s, form=form, teachers=teachers)


@router.post("/{salary_id}/edit")
def update_salary(salary_id: int,
                  request: Request,
                  teacher_id: int = Form(...),
                  month: str = Form(""),
                  base_salary: str = Form("0"),
                  teaching_hours: str = Form("0"),
                  hourly_rate: str = Form("0"),
                  bonus: str = Form("0"),
                  deduction: str = Form("0"),
                  note: str = Form(""),
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    s = db.get(Salary, salary_id)
    if not s:
        return render(request, "404.html", user=user, status_code=404)

    if s.status == "paid":
        flash(request, "Không thể sửa bảng lương đã thanh toán.", kind="err")
        return RedirectResponse("/salaries", status_code=303)

    month = month.strip()
    note = note.strip()
    errors = _validate(month, base_salary, teaching_hours, hourly_rate, bonus, deduction)

    existing = (db.query(Salary)
                .filter(Salary.teacher_id == teacher_id,
                        Salary.month == month,
                        Salary.salary_id != salary_id).first())
    if existing:
        errors.append(f"GV đã có bảng lương tháng {month}")

    teachers = (db.query(Teacher).filter(Teacher.status == "active")
                .join(User, Teacher.user_id == User.user_id)
                .order_by(Teacher.teacher_code).all())

    form = {"teacher_id": teacher_id, "month": month, "base_salary": base_salary,
            "teaching_hours": teaching_hours, "hourly_rate": hourly_rate,
            "bonus": bonus, "deduction": deduction, "note": note}

    if errors:
        return render(request, "salary_form.html", user=user,
                      mode="edit", salary=s, form=form, teachers=teachers,
                      error="; ".join(errors), status_code=400)

    base = float(base_salary)
    hours = float(teaching_hours)
    rate = float(hourly_rate)
    bn = float(bonus)
    ded = float(deduction)

    s.teacher_id = teacher_id
    s.month = month
    s.base_salary = base
    s.teaching_hours = hours
    s.hourly_rate = rate
    s.bonus = bn
    s.deduction = ded
    s.total_salary = base + hours * rate + bn - ded
    s.note = note or None
    db.commit()

    flash(request, f"Đã cập nhật bảng lương tháng {month}")
    return RedirectResponse("/salaries", status_code=303)


@router.post("/{salary_id}/mark-paid")
def mark_paid(salary_id: int,
              request: Request,
              user: User = Depends(require_roles("admin")),
              db: Session = Depends(get_db)):
    s = db.get(Salary, salary_id)
    if not s:
        return render(request, "404.html", user=user, status_code=404)
    s.status = "paid"
    s.paid_date = datetime.now()
    db.commit()
    flash(request, f"Đã đánh dấu thanh toán lương tháng {s.month}")
    return RedirectResponse("/salaries", status_code=303)


@router.post("/{salary_id}/delete")
def delete_salary(salary_id: int,
                  request: Request,
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    s = db.get(Salary, salary_id)
    if not s:
        return render(request, "404.html", user=user, status_code=404)
    if s.status == "paid":
        flash(request, "Không thể xóa bảng lương đã thanh toán.", kind="err")
        return RedirectResponse("/salaries", status_code=303)
    month = s.month
    db.delete(s)
    db.commit()
    flash(request, f"Đã xóa bảng lương tháng {month}")
    return RedirectResponse("/salaries", status_code=303)