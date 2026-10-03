from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import ClassRoom, Teacher, User
from .security import hash_password
from .web import flash, render

router = APIRouter(prefix="/teachers", tags=["teachers"])

DEFAULT_PASSWORD = "gv123"


def _next_username(db: Session) -> str:
    n = db.query(User).filter(User.role == "teacher").count() + 1
    while db.query(User).filter(User.username == f"gv{n}").first():
        n += 1
    return f"gv{n}"


def _next_teacher_code(db: Session) -> str:
    n = db.query(Teacher).count() + 1
    while db.query(Teacher).filter(Teacher.teacher_code == f"GV{n:04d}").first():
        n += 1
    return f"GV{n:04d}"


def _validate(db: Session, full_name: str, phone: str, email: str,
              exclude_user_id: int | None = None) -> list[str]:
    errors: list[str] = []
    if not full_name or len(full_name.strip()) < 2:
        errors.append("Họ tên phải có ít nhất 2 ký tự")
    if not phone or not phone.isdigit() or len(phone) != 10:
        errors.append("Số điện thoại phải gồm đúng 10 chữ số")
    if not email or "@" not in email or "." not in email:
        errors.append("Email không hợp lệ")
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


@router.get("")
def list_teachers(request: Request,
                  q: str = "",
                  status: str = "",
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    query = (db.query(Teacher)
             .join(User, Teacher.user_id == User.user_id))

    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            User.full_name.ilike(like),
            User.phone.ilike(like),
            User.email.ilike(like),
            Teacher.teacher_code.ilike(like),
            Teacher.specialization.ilike(like),
        ))
    if status in ("active", "inactive"):
        query = query.filter(Teacher.status == status)

    teachers = query.order_by(Teacher.teacher_code).all()
    return render(request, "teachers_list.html", user=user,
                  teachers=teachers, q=q, status=status)


@router.get("/new")
def new_teacher_form(request: Request,
                     user: User = Depends(require_roles("admin"))):
    return render(request, "teacher_form.html", user=user,
                  mode="new", form={})


@router.post("/new")
def create_teacher(request: Request,
                   full_name: str = Form(""),
                   phone: str = Form(""),
                   email: str = Form(""),
                   specialization: str = Form(""),
                   degree: str = Form(""),
                   user: User = Depends(require_roles("admin")),
                   db: Session = Depends(get_db)):
    full_name = full_name.strip()
    phone = phone.strip()
    email = email.strip().lower()
    specialization = specialization.strip()
    degree = degree.strip()

    errors = _validate(db, full_name, phone, email)
    form = {"full_name": full_name, "phone": phone, "email": email,
            "specialization": specialization, "degree": degree}
    if errors:
        return render(request, "teacher_form.html", user=user,
                      mode="new", form=form,
                      error="; ".join(errors), status_code=400)

    username = _next_username(db)
    u = User(username=username, password_hash=hash_password(DEFAULT_PASSWORD),
             full_name=full_name, email=email, phone=phone,
             role="teacher", status="active")
    db.add(u)
    db.flush()

    t = Teacher(user_id=u.user_id,
                teacher_code=_next_teacher_code(db),
                specialization=specialization or None,
                degree=degree or None,
                status="active")
    db.add(t)
    db.commit()

    flash(request, f"Đã thêm giáo viên {full_name} (tài khoản: {username} / {DEFAULT_PASSWORD})")
    return RedirectResponse("/teachers", status_code=303)


@router.get("/{teacher_id}")
def teacher_detail(teacher_id: int,
                   request: Request,
                   user: User = Depends(require_roles("admin")),
                   db: Session = Depends(get_db)):
    t = db.get(Teacher, teacher_id)
    if not t:
        return render(request, "404.html", user=user, status_code=404)

    classes = (db.query(ClassRoom)
               .filter(ClassRoom.teacher_id == teacher_id)
               .order_by(ClassRoom.class_code).all())
    total_students = sum(c.current_students for c in classes)

    return render(request, "teacher_detail.html", user=user,
                  teacher=t, classes=classes, total_students=total_students)


@router.get("/{teacher_id}/edit")
def edit_teacher_form(teacher_id: int,
                      request: Request,
                      user: User = Depends(require_roles("admin")),
                      db: Session = Depends(get_db)):
    t = db.get(Teacher, teacher_id)
    if not t:
        return render(request, "404.html", user=user, status_code=404)

    form = {
        "full_name": t.user.full_name,
        "phone": t.user.phone,
        "email": t.user.email,
        "specialization": t.specialization or "",
        "degree": t.degree or "",
        "status": t.status,
    }
    return render(request, "teacher_form.html", user=user,
                  mode="edit", teacher=t, form=form)


@router.post("/{teacher_id}/edit")
def update_teacher(teacher_id: int,
                   request: Request,
                   full_name: str = Form(""),
                   phone: str = Form(""),
                   email: str = Form(""),
                   specialization: str = Form(""),
                   degree: str = Form(""),
                   status: str = Form("active"),
                   user: User = Depends(require_roles("admin")),
                   db: Session = Depends(get_db)):
    t = db.get(Teacher, teacher_id)
    if not t:
        return render(request, "404.html", user=user, status_code=404)

    full_name = full_name.strip()
    phone = phone.strip()
    email = email.strip().lower()
    specialization = specialization.strip()
    degree = degree.strip()

    form = {"full_name": full_name, "phone": phone, "email": email,
            "specialization": specialization, "degree": degree, "status": status}

    errors = _validate(db, full_name, phone, email, exclude_user_id=t.user_id)
    if errors:
        return render(request, "teacher_form.html", user=user,
                      mode="edit", teacher=t, form=form,
                      error="; ".join(errors), status_code=400)

    t.user.full_name = full_name
    t.user.phone = phone
    t.user.email = email
    t.specialization = specialization or None
    t.degree = degree or None
    t.status = status if status in ("active", "inactive") else "active"
    db.commit()

    flash(request, f"Đã cập nhật giáo viên {full_name}")
    return RedirectResponse("/teachers", status_code=303)


@router.post("/{teacher_id}/toggle")
def toggle_teacher(teacher_id: int,
                   request: Request,
                   user: User = Depends(require_roles("admin")),
                   db: Session = Depends(get_db)):
    t = db.get(Teacher, teacher_id)
    if not t:
        return render(request, "404.html", user=user, status_code=404)
    t.status = "inactive" if t.status == "active" else "active"
    db.commit()
    label = "ngừng hoạt động" if t.status == "inactive" else "kích hoạt"
    flash(request, f"Đã {label} giáo viên {t.user.full_name}")
    return RedirectResponse("/teachers", status_code=303)


@router.post("/{teacher_id}/delete")
def delete_teacher(teacher_id: int,
                   request: Request,
                   user: User = Depends(require_roles("admin")),
                   db: Session = Depends(get_db)):
    t = db.get(Teacher, teacher_id)
    if not t:
        return render(request, "404.html", user=user, status_code=404)

    active_classes = [c for c in t.classes if c.status == "open"]
    if active_classes:
        flash(request, f"Không thể xóa: giáo viên {t.user.full_name} đang dạy "
                       f"{len(active_classes)} lớp. Hãy chuyển lớp hoặc đóng lớp trước.",
              kind="err")
        return RedirectResponse("/teachers", status_code=303)

    name = t.user.full_name
    t.user.status = "inactive"
    db.delete(t)
    db.commit()
    flash(request, f"Đã xóa giáo viên {name}")
    return RedirectResponse("/teachers", status_code=303)