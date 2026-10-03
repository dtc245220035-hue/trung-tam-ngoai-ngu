from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import (ClassRoom, Course, Enrollment, Invoice, Student, User)
from .web import flash, render

router = APIRouter(prefix="/enroll", tags=["enrollments"])


def _next_invoice_code(db: Session) -> str:
    n = db.query(Invoice).count() + 1
    while db.query(Invoice).filter(Invoice.invoice_code == f"HD{n:04d}").first():
        n += 1
    return f"HD{n:04d}"


def _active_students(db: Session):
    return (db.query(Student)
            .join(User, Student.user_id == User.user_id)
            .filter(Student.is_deleted.is_(False))
            .order_by(Student.student_code).all())


def _open_classes(db: Session):
    return (db.query(ClassRoom)
            .filter(ClassRoom.status == "open")
            .order_by(ClassRoom.class_code).all())


@router.get("")
def list_enrollments(request: Request,
                     q: str = "",
                     class_id: str = "",
                     status: str = "",
                     user: User = Depends(require_roles("admin", "consultant")),
                     db: Session = Depends(get_db)):
    query = (db.query(Enrollment)
             .join(Student, Enrollment.student_id == Student.student_id)
             .join(User, Student.user_id == User.user_id)
             .join(ClassRoom, Enrollment.class_id == ClassRoom.class_id))

    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            User.full_name.ilike(like),
            Student.student_code.ilike(like),
            ClassRoom.class_code.ilike(like),
        ))
    if class_id and class_id.isdigit():
        query = query.filter(Enrollment.class_id == int(class_id))
    if status in ("active", "cancelled"):
        query = query.filter(Enrollment.status == status)
    else:
        query = query.filter(Enrollment.status == "active")

    enrolls = query.order_by(Enrollment.enroll_date.desc()).all()
    return render(request, "enroll_list.html", user=user,
                  enrolls=enrolls, q=q, class_id=class_id, status=status,
                  classes=_open_classes(db))


@router.get("/new")
def new_enroll_form(request: Request,
                    student_id: str = "",
                    class_id: str = "",
                    user: User = Depends(require_roles("admin", "consultant")),
                    db: Session = Depends(get_db)):
    return render(request, "enroll_form.html", user=user,
                  students=_active_students(db),
                  classes=_open_classes(db),
                  form={"student_id": student_id, "class_id": class_id})


@router.post("/new")
def create_enrollment(request: Request,
                      student_id: int = Form(...),
                      class_id: int = Form(...),
                      user: User = Depends(require_roles("admin", "consultant")),
                      db: Session = Depends(get_db)):
    errors: list[str] = []

    student = db.get(Student, student_id)
    if not student or student.is_deleted:
        errors.append("Học viên không tồn tại")

    classroom = db.get(ClassRoom, class_id)
    if not classroom:
        errors.append("Lớp không tồn tại")
    elif classroom.status != "open":
        errors.append(f"Lớp {classroom.class_code} đã đóng, không nhận đăng ký")
    elif classroom.seats_left <= 0:
        errors.append(f"Lớp {classroom.class_code} đã đủ sĩ số "
                      f"({classroom.current_students}/{classroom.max_students})")

    if student and classroom:
        existing = (db.query(Enrollment)
                    .filter(Enrollment.student_id == student_id,
                            Enrollment.class_id == class_id,
                            Enrollment.status == "active").first())
        if existing:
            errors.append(f"Học viên {student.user.full_name} đã đăng ký lớp "
                          f"{classroom.class_code}")

    if errors:
        return render(request, "enroll_form.html", user=user,
                      students=_active_students(db),
                      classes=_open_classes(db),
                      form={"student_id": student_id, "class_id": class_id},
                      error=" | ".join(errors), status_code=400)

    # Tạo đăng ký
    e = Enrollment(student_id=student_id, class_id=class_id, status="active")
    db.add(e)
    classroom.current_students += 1
    db.flush()

    # Tự sinh hóa đơn (discount=0 mặc định)
    total = classroom.course.tuition_fee
    inv = Invoice(invoice_code=_next_invoice_code(db),
                  student_id=student_id,
                  class_id=class_id,
                  total_amount=total,
                  discount_amount=0,
                  paid_amount=0,
                  policy_id=None,
                  status="unpaid")
    db.add(inv)
    db.commit()

    warning = ""
    if student.level and student.level != classroom.course.level:
        warning = (f" Lưu ý: trình độ HV ({student.level}) khác trình độ khóa "
                   f"({classroom.course.level}).")

    flash(request, f"Đã đăng ký {student.user.full_name} vào lớp "
                   f"{classroom.class_code}. Hóa đơn {inv.invoice_code}: "
                   f"{total:,.0f} đ.{warning}")
    return RedirectResponse("/enroll", status_code=303)


@router.post("/{enrollment_id}/cancel")
def cancel_enrollment(enrollment_id: int,
                      request: Request,
                      user: User = Depends(require_roles("admin", "consultant")),
                      db: Session = Depends(get_db)):
    e = db.get(Enrollment, enrollment_id)
    if not e or e.status != "active":
        return render(request, "404.html", user=user, status_code=404)

    inv = (db.query(Invoice)
           .filter(Invoice.student_id == e.student_id,
                   Invoice.class_id == e.class_id)
           .first())

    if inv and inv.paid_amount > 0:
        flash(request, f"Không thể hủy: học viên {e.student.user.full_name} đã đóng "
                       f"{inv.paid_amount:,.0f} đ cho hóa đơn {inv.invoice_code}. "
                       f"Vui lòng xử lý hoàn tiền trước.", kind="err")
        return RedirectResponse("/enroll", status_code=303)

    e.status = "cancelled"
    e.classroom.current_students = max(0, e.classroom.current_students - 1)
    if inv and inv.paid_amount == 0:
        db.delete(inv)
    db.commit()

    flash(request, f"Đã hủy đăng ký của {e.student.user.full_name} "
                   f"khỏi lớp {e.classroom.class_code}")
    return RedirectResponse("/enroll", status_code=303)