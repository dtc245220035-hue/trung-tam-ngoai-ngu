from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import Student, User
from .security import hash_password
from .utils import LEVEL_ORDER
from .web import flash, render

router = APIRouter(prefix="/students", tags=["students"])

VALID_LEVELS = set(LEVEL_ORDER)
DEFAULT_PASSWORD = "hv123"


# ============ Helper ============

def _next_username(db: Session) -> str:
    n = db.query(User).filter(User.role == "student").count() + 1
    while db.query(User).filter(User.username == f"hv{n}").first():
        n += 1
    return f"hv{n}"


def _next_student_code(db: Session) -> str:
    n = db.query(Student).count() + 1
    while db.query(Student).filter(Student.student_code == f"HV{n:04d}").first():
        n += 1
    return f"HV{n:04d}"


def _validate(db: Session, full_name: str, phone: str, email: str,
              level: str, exclude_user_id: int | None = None) -> list[str]:
    errors: list[str] = []
    if not full_name or len(full_name.strip()) < 2:
        errors.append("Họ tên phải có ít nhất 2 ký tự")
    if not phone or not phone.isdigit() or len(phone) != 10:
        errors.append("Số điện thoại phải gồm đúng 10 chữ số")
    if not email or "@" not in email or "." not in email:
        errors.append("Email không hợp lệ")
    if level and level not in VALID_LEVELS:
        errors.append("Trình độ không hợp lệ (A1-C2)")
    if email:
        q = db.query(User).filter(User.email == email)
        if exclude_user_id:
            q = q.filter(User.user_id != exclude_user_id)
        if q.first():
            errors.append("Email đã được sử dụng")
    if phone:
        q = db.query(User).filter(User.phone == phone)
        if exclude_user_id:
            q = q.filter(User.user_id != exclude_user_id)
        if q.first():
            errors.append("Số điện thoại đã được sử dụng")
    return errors


def _parse_dob(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


# ============ Routes ============

@router.get("")
def list_students(request: Request,
                  q: str = "",
                  level: str = "",
                  user: User = Depends(require_roles("admin", "consultant")),
                  db: Session = Depends(get_db)):
    query = (db.query(Student)
             .join(User, Student.user_id == User.user_id)
             .filter(Student.is_deleted.is_(False)))

    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            User.full_name.ilike(like),
            User.phone.ilike(like),
            User.email.ilike(like),
            Student.student_code.ilike(like),
        ))
    if level and level in VALID_LEVELS:
        query = query.filter(Student.level == level)

    students = query.order_by(Student.student_code).all()
    return render(request, "students_list.html", user=user,
                  students=students, q=q, level=level, levels=LEVEL_ORDER)


@router.get("/new")
def new_student_form(request: Request,
                     user: User = Depends(require_roles("admin", "consultant"))):
    return render(request, "student_form.html", user=user,
                  mode="new", form={}, levels=LEVEL_ORDER)


@router.post("/new")
def create_student(request: Request,
                   full_name: str = Form(""),
                   phone: str = Form(""),
                   email: str = Form(""),
                   level: str = Form(""),
                   date_of_birth: str = Form(""),
                   note: str = Form(""),
                   user: User = Depends(require_roles("admin", "consultant")),
                   db: Session = Depends(get_db)):
    full_name = full_name.strip()
    phone = phone.strip()
    email = email.strip().lower()

    errors = _validate(db, full_name, phone, email, level)
    form = {"full_name": full_name, "phone": phone, "email": email,
            "level": level, "date_of_birth": date_of_birth, "note": note}
    if errors:
        return render(request, "student_form.html", user=user,
                      mode="new", form=form, levels=LEVEL_ORDER,
                      error="; ".join(errors), status_code=400)

    username = _next_username(db)
    u = User(username=username, password_hash=hash_password(DEFAULT_PASSWORD),
             full_name=full_name, email=email, phone=phone,
             role="student", status="active")
    db.add(u)
    db.flush()

    s = Student(user_id=u.user_id,
                student_code=_next_student_code(db),
                level=level or None,
                date_of_birth=_parse_dob(date_of_birth),
                note=note.strip() or None)
    db.add(s)
    db.commit()

    flash(request, f"Đã thêm học viên {full_name} (tài khoản: {username} / {DEFAULT_PASSWORD})")
    return RedirectResponse("/students", status_code=303)


@router.get("/{student_id}/edit")
def edit_student_form(student_id: int,
                      request: Request,
                      user: User = Depends(require_roles("admin", "consultant")),
                      db: Session = Depends(get_db)):
    s = db.get(Student, student_id)
    if not s or s.is_deleted:
        return render(request, "404.html", user=user, status_code=404)

    form = {
        "full_name": s.user.full_name,
        "phone": s.user.phone,
        "email": s.user.email,
        "level": s.level or "",
        "date_of_birth": s.date_of_birth.isoformat() if s.date_of_birth else "",
        "note": s.note or "",
    }
    return render(request, "student_form.html", user=user,
                  mode="edit", student=s, form=form, levels=LEVEL_ORDER)


@router.post("/{student_id}/edit")
def update_student(student_id: int,
                   request: Request,
                   full_name: str = Form(""),
                   phone: str = Form(""),
                   email: str = Form(""),
                   level: str = Form(""),
                   date_of_birth: str = Form(""),
                   note: str = Form(""),
                   user: User = Depends(require_roles("admin", "consultant")),
                   db: Session = Depends(get_db)):
    s = db.get(Student, student_id)
    if not s or s.is_deleted:
        return render(request, "404.html", user=user, status_code=404)

    full_name = full_name.strip()
    phone = phone.strip()
    email = email.strip().lower()
    form = {"full_name": full_name, "phone": phone, "email": email,
            "level": level, "date_of_birth": date_of_birth, "note": note}

    errors = _validate(db, full_name, phone, email, level,
                       exclude_user_id=s.user_id)
    if errors:
        return render(request, "student_form.html", user=user,
                      mode="edit", student=s, form=form, levels=LEVEL_ORDER,
                      error="; ".join(errors), status_code=400)

    s.user.full_name = full_name
    s.user.phone = phone
    s.user.email = email
    s.level = level or None
    s.date_of_birth = _parse_dob(date_of_birth)
    s.note = note.strip() or None
    db.commit()

    flash(request, f"Đã cập nhật học viên {full_name}")
    return RedirectResponse("/students", status_code=303)


@router.post("/{student_id}/delete")
def delete_student(student_id: int,
                   request: Request,
                   user: User = Depends(require_roles("admin", "consultant")),
                   db: Session = Depends(get_db)):
    s = db.get(Student, student_id)
    if not s or s.is_deleted:
        return render(request, "404.html", user=user, status_code=404)

    active_enrolls = [e for e in s.enrollments if e.status == "active"]
    if active_enrolls:
        flash(request, f"Không thể xóa: học viên {s.user.full_name} đang tham gia "
                       f"{len(active_enrolls)} lớp. Hãy hủy đăng ký trước.", kind="err")
        return RedirectResponse("/students", status_code=303)

    s.is_deleted = True
    s.user.status = "inactive"
    db.commit()
    flash(request, f"Đã xóa học viên {s.user.full_name}")
    return RedirectResponse("/students", status_code=303)