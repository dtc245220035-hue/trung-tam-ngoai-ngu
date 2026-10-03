from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import (ClassRoom, Enrollment, Invoice, Payment, Schedule,
                     Student, Teacher, User)
from .web import render

router = APIRouter(tags=["self-service"])


def _get_teacher(db: Session, user: User) -> Teacher | None:
    return db.query(Teacher).filter(Teacher.user_id == user.user_id).first()


def _get_student(db: Session, user: User) -> Student | None:
    return (db.query(Student)
            .filter(Student.user_id == user.user_id, Student.is_deleted.is_(False))
            .first())


# ========== GIÁO VIÊN: DS lớp dạy ==========

@router.get("/my_classes")
def my_classes(request: Request,
               user: User = Depends(require_roles("teacher")),
               db: Session = Depends(get_db)):
    teacher = _get_teacher(db, user)
    if not teacher:
        return render(request, "403.html", user=user, status_code=403)

    classes = (db.query(ClassRoom)
               .filter(ClassRoom.teacher_id == teacher.teacher_id)
               .order_by(ClassRoom.class_code).all())

    total_students = sum(c.current_students for c in classes)

    return render(request, "my_classes.html", user=user,
                  teacher=teacher, classes=classes,
                  total_students=total_students)


# ========== HỌC VIÊN: Lịch học ==========

@router.get("/my_schedule")
def my_schedule(request: Request,
                user: User = Depends(require_roles("student")),
                db: Session = Depends(get_db)):
    student = _get_student(db, user)
    if not student:
        return render(request, "403.html", user=user, status_code=403)

    enrolls = (db.query(Enrollment)
               .filter(Enrollment.student_id == student.student_id,
                       Enrollment.status == "active")
               .join(ClassRoom, Enrollment.class_id == ClassRoom.class_id)
               .order_by(ClassRoom.class_code).all())

    my_classes = [e.classroom for e in enrolls]

    # Sắp lịch theo thứ tự ngày trong tuần
    from .utils import DAY_ORDER
    day_idx = {d: i for i, d in enumerate(DAY_ORDER)}
    all_scheds = []
    for c in my_classes:
        for s in c.schedules:
            all_scheds.append((c, s))
    all_scheds.sort(key=lambda x: (day_idx.get(x[1].day_of_week, 99),
                                    x[1].start_time))

    return render(request, "my_schedule.html", user=user,
                  student=student, my_classes=my_classes,
                  all_scheds=all_scheds)


# ========== HỌC VIÊN: Hóa đơn ==========

@router.get("/my_invoices")
def my_invoices(request: Request,
                user: User = Depends(require_roles("student")),
                db: Session = Depends(get_db)):
    student = _get_student(db, user)
    if not student:
        return render(request, "403.html", user=user, status_code=403)

    invoices = (db.query(Invoice)
                .filter(Invoice.student_id == student.student_id)
                .join(ClassRoom, Invoice.class_id == ClassRoom.class_id)
                .order_by(Invoice.created_at.desc()).all())

    total_amount = sum(i.total_amount for i in invoices)
    total_paid = sum(i.paid_amount for i in invoices)
    total_owing = total_amount - total_paid

    return render(request, "my_invoices.html", user=user,
                  student=student, invoices=invoices,
                  total_amount=total_amount, total_paid=total_paid,
                  total_owing=total_owing)