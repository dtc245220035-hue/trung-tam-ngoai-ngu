from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import ClassRoom, Course, User
from .utils import LEVEL_ORDER
from .web import flash, render

router = APIRouter(prefix="/courses", tags=["courses"])

VALID_LEVELS = set(LEVEL_ORDER)


def _next_course_code(db: Session) -> str:
    n = db.query(Course).count() + 1
    while db.query(Course).filter(Course.course_code == f"KH{n:04d}").first():
        n += 1
    return f"KH{n:04d}"


def _validate(db: Session, course_name: str, level: str,
              tuition_fee: str, duration: str,
              exclude_course_id: int | None = None) -> list[str]:
    errors: list[str] = []
    if not course_name or len(course_name.strip()) < 3:
        errors.append("Tên khóa học phải có ít nhất 3 ký tự")
    if level not in VALID_LEVELS:
        errors.append("Trình độ không hợp lệ (A1-C2)")

    try:
        fee = float(tuition_fee)
        if fee <= 0:
            errors.append("Học phí phải lớn hơn 0")
    except (ValueError, TypeError):
        errors.append("Học phí không hợp lệ")

    try:
        dur = int(duration)
        if dur <= 0:
            errors.append("Thời lượng phải lớn hơn 0")
    except (ValueError, TypeError):
        errors.append("Thời lượng không hợp lệ")

    if course_name:
        q = db.query(Course).filter(Course.course_name == course_name.strip())
        if exclude_course_id:
            q = q.filter(Course.course_id != exclude_course_id)
        if q.first():
            errors.append("Tên khóa học đã tồn tại")

    return errors


@router.get("")
def list_courses(request: Request,
                 q: str = "",
                 level: str = "",
                 user: User = Depends(require_roles("admin")),
                 db: Session = Depends(get_db)):
    query = db.query(Course)

    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Course.course_name.ilike(like),
            Course.course_code.ilike(like),
        ))
    if level and level in VALID_LEVELS:
        query = query.filter(Course.level == level)

    courses = query.order_by(Course.course_code).all()
    return render(request, "courses_list.html", user=user,
                  courses=courses, q=q, level=level, levels=LEVEL_ORDER)


@router.get("/new")
def new_course_form(request: Request,
                    user: User = Depends(require_roles("admin"))):
    return render(request, "course_form.html", user=user,
                  mode="new", form={}, levels=LEVEL_ORDER)


@router.post("/new")
def create_course(request: Request,
                  course_name: str = Form(""),
                  level: str = Form(""),
                  tuition_fee: str = Form(""),
                  duration: str = Form(""),
                  description: str = Form(""),
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    course_name = course_name.strip()
    form = {"course_name": course_name, "level": level,
            "tuition_fee": tuition_fee, "duration": duration,
            "description": description}

    errors = _validate(db, course_name, level, tuition_fee, duration)
    if errors:
        return render(request, "course_form.html", user=user,
                      mode="new", form=form, levels=LEVEL_ORDER,
                      error="; ".join(errors), status_code=400)

    c = Course(course_code=_next_course_code(db),
               course_name=course_name,
               level=level,
               tuition_fee=float(tuition_fee),
               duration=int(duration),
               description=description.strip() or None)
    db.add(c)
    db.commit()

    flash(request, f"Đã thêm khóa học {course_name}")
    return RedirectResponse("/courses", status_code=303)


@router.get("/{course_id}/edit")
def edit_course_form(course_id: int,
                     request: Request,
                     user: User = Depends(require_roles("admin")),
                     db: Session = Depends(get_db)):
    c = db.get(Course, course_id)
    if not c:
        return render(request, "404.html", user=user, status_code=404)

    form = {
        "course_name": c.course_name,
        "level": c.level,
        "tuition_fee": f"{c.tuition_fee:.0f}",
        "duration": c.duration,
        "description": c.description or "",
    }
    return render(request, "course_form.html", user=user,
                  mode="edit", course=c, form=form, levels=LEVEL_ORDER)


@router.post("/{course_id}/edit")
def update_course(course_id: int,
                  request: Request,
                  course_name: str = Form(""),
                  level: str = Form(""),
                  tuition_fee: str = Form(""),
                  duration: str = Form(""),
                  description: str = Form(""),
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    c = db.get(Course, course_id)
    if not c:
        return render(request, "404.html", user=user, status_code=404)

    course_name = course_name.strip()
    form = {"course_name": course_name, "level": level,
            "tuition_fee": tuition_fee, "duration": duration,
            "description": description}

    errors = _validate(db, course_name, level, tuition_fee, duration,
                       exclude_course_id=course_id)
    if errors:
        return render(request, "course_form.html", user=user,
                      mode="edit", course=c, form=form, levels=LEVEL_ORDER,
                      error="; ".join(errors), status_code=400)

    c.course_name = course_name
    c.level = level
    c.tuition_fee = float(tuition_fee)
    c.duration = int(duration)
    c.description = description.strip() or None
    db.commit()

    flash(request, f"Đã cập nhật khóa học {course_name}")
    return RedirectResponse("/courses", status_code=303)


@router.post("/{course_id}/delete")
def delete_course(course_id: int,
                  request: Request,
                  user: User = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    c = db.get(Course, course_id)
    if not c:
        return render(request, "404.html", user=user, status_code=404)

    active_classes = [cl for cl in c.classes if cl.status == "open"]
    if active_classes:
        flash(request, f"Không thể xóa: khóa học {c.course_name} đang có "
                       f"{len(active_classes)} lớp hoạt động.", kind="err")
        return RedirectResponse("/courses", status_code=303)

    db.delete(c)
    db.commit()
    flash(request, f"Đã xóa khóa học {c.course_name}")
    return RedirectResponse("/courses", status_code=303)