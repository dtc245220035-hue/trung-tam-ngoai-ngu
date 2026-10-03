from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import (ClassRoom, Course, Enrollment, Invoice, Schedule,
                     Student, Teacher, User)
from .web import render

router = APIRouter(prefix="/lookup", tags=["lookup"])

VALID_TYPES = ("class", "student", "invoice")


def _get_teacher(db: Session, user: User) -> Teacher | None:
    return db.query(Teacher).filter(Teacher.user_id == user.user_id).first()


@router.get("")
def lookup(request: Request,
           q: str = "",
           type: str = "class",
           user: User = Depends(require_roles("admin", "consultant", "teacher")),
           db: Session = Depends(get_db)):
    q = (q or "").strip()
    if type not in VALID_TYPES:
        type = "class"

    # GV bị giới hạn — không xem invoice, chỉ xem lớp mình
    teacher = _get_teacher(db, user) if user.role == "teacher" else None
    if user.role == "teacher" and type == "invoice":
        type = "class"

    results = []
    total = 0

    if q:
        like = f"%{q}%"

        if type == "class":
            query = (db.query(ClassRoom)
                     .join(Course, ClassRoom.course_id == Course.course_id))
            if teacher:
                query = query.filter(ClassRoom.teacher_id == teacher.teacher_id)
            query = query.filter(or_(
                ClassRoom.class_code.ilike(like),
                Course.course_name.ilike(like),
                ClassRoom.room.ilike(like),
            ))
            results = query.order_by(ClassRoom.class_code).all()
            total = len(results)

        elif type == "student":
            query = (db.query(Student)
                     .join(User, Student.user_id == User.user_id)
                     .filter(Student.is_deleted.is_(False)))
            if teacher:
                # GV chỉ thấy HV trong lớp mình dạy
                sub = (db.query(Enrollment.student_id)
                       .join(ClassRoom, Enrollment.class_id == ClassRoom.class_id)
                       .filter(ClassRoom.teacher_id == teacher.teacher_id,
                               Enrollment.status == "active")
                       .subquery())
                query = query.filter(Student.student_id.in_(sub))
            query = query.filter(or_(
                User.full_name.ilike(like),
                User.phone.ilike(like),
                User.email.ilike(like),
                Student.student_code.ilike(like),
            ))
            results = query.order_by(Student.student_code).all()
            total = len(results)

        elif type == "invoice":
            query = (db.query(Invoice)
                     .join(Student, Invoice.student_id == Student.student_id)
                     .join(User, Student.user_id == User.user_id)
                     .join(ClassRoom, Invoice.class_id == ClassRoom.class_id))
            query = query.filter(or_(
                Invoice.invoice_code.ilike(like),
                User.full_name.ilike(like),
                Student.student_code.ilike(like),
                ClassRoom.class_code.ilike(like),
            ))
            results = query.order_by(Invoice.created_at.desc()).all()
            total = len(results)

    return render(request, "lookup.html", user=user,
                  q=q, type=type, results=results, total=total)