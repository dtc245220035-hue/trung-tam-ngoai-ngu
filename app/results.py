from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import ClassRoom, Enrollment, Result, Student, Teacher, User
from .utils import rank_for
from .web import flash, render

# Router cho giáo viên
teacher_router = APIRouter(prefix="/results", tags=["results-teacher"])

# Router cho học viên
student_router = APIRouter(prefix="/my_results", tags=["results-student"])


def _get_teacher(db: Session, user: User) -> Teacher | None:
    return db.query(Teacher).filter(Teacher.user_id == user.user_id).first()


def _get_student(db: Session, user: User) -> Student | None:
    return (db.query(Student)
            .filter(Student.user_id == user.user_id, Student.is_deleted.is_(False))
            .first())


def _class_students(db: Session, class_id: int):
    enrolls = (db.query(Enrollment)
               .filter(Enrollment.class_id == class_id,
                       Enrollment.status == "active")
               .join(Student, Enrollment.student_id == Student.student_id)
               .join(User, Student.user_id == User.user_id)
               .order_by(Student.student_code).all())
    return [e.student for e in enrolls]


# ==================== ROUTES GIÁO VIÊN ====================

@teacher_router.get("")
def results_home(request: Request,
                 user: User = Depends(require_roles("teacher")),
                 db: Session = Depends(get_db)):
    teacher = _get_teacher(db, user)
    if not teacher:
        return render(request, "403.html", user=user, status_code=403)

    classes = (db.query(ClassRoom)
               .filter(ClassRoom.teacher_id == teacher.teacher_id)
               .order_by(ClassRoom.class_code).all())

    # Đếm số HV đã có điểm trong mỗi lớp
    stats = {}
    for c in classes:
        n_graded = (db.query(Result)
                    .filter(Result.class_id == c.class_id).count())
        stats[c.class_id] = {
            "n_graded": n_graded,
            "n_students": c.current_students,
            "done": n_graded > 0 and n_graded >= c.current_students,
        }

    return render(request, "results_classes.html", user=user,
                  classes=classes, stats=stats)


@teacher_router.get("/{class_id}")
def results_form(class_id: int,
                 request: Request,
                 user: User = Depends(require_roles("teacher")),
                 db: Session = Depends(get_db)):
    teacher = _get_teacher(db, user)
    cls = db.get(ClassRoom, class_id)
    if not cls or not teacher or cls.teacher_id != teacher.teacher_id:
        return render(request, "403.html", user=user, status_code=403)

    students = _class_students(db, class_id)

    # Load điểm hiện có
    existing = {}
    if students:
        rows = (db.query(Result).filter(Result.class_id == class_id).all())
        existing = {r.student_id: r for r in rows}

    return render(request, "results_form.html", user=user,
                  classroom=cls, students=students, existing=existing)


@teacher_router.post("/{class_id}")
async def save_results(class_id: int,
                       request: Request,
                       user: User = Depends(require_roles("teacher")),
                       db: Session = Depends(get_db)):
    teacher = _get_teacher(db, user)
    cls = db.get(ClassRoom, class_id)
    if not cls or not teacher or cls.teacher_id != teacher.teacher_id:
        return render(request, "403.html", user=user, status_code=403)

    students = _class_students(db, class_id)
    if not students:
        flash(request, "Lớp chưa có học viên nào.", kind="err")
        return RedirectResponse("/results", status_code=303)

    form = await request.form()
    existing_rows = db.query(Result).filter(Result.class_id == class_id).all()
    existing_map = {r.student_id: r for r in existing_rows}

    saved, skipped, errors = 0, 0, []

    for s in students:
        # Đọc điểm
        try:
            vals = {}
            for skill in ("listening", "speaking", "reading", "writing"):
                raw = (form.get(f"{skill}_{s.student_id}") or "").strip()
                if not raw:
                    vals = None
                    break
                v = float(raw)
                if v < 0 or v > 10:
                    errors.append(f"{s.student_code}: điểm phải trong khoảng 0-10")
                    vals = None
                    break
                vals[skill] = round(v, 2)
        except ValueError:
            errors.append(f"{s.student_code}: điểm không hợp lệ")
            continue

        if not vals:
            skipped += 1
            continue

        avg = round(sum(vals.values()) / 4, 2)
        rank = rank_for(avg)
        comment = (form.get(f"comment_{s.student_id}") or "").strip() or None

        if s.student_id in existing_map:
            row = existing_map[s.student_id]
            row.listening = vals["listening"]
            row.speaking = vals["speaking"]
            row.reading = vals["reading"]
            row.writing = vals["writing"]
            row.average = avg
            row.rank = rank
            row.comment = comment
        else:
            db.add(Result(student_id=s.student_id, class_id=class_id,
                          listening=vals["listening"], speaking=vals["speaking"],
                          reading=vals["reading"], writing=vals["writing"],
                          average=avg, rank=rank, comment=comment))
        saved += 1

    if errors:
        flash(request, " | ".join(errors[:3]) + ("..." if len(errors) > 3 else ""),
              kind="err")
        db.rollback()
        return RedirectResponse(f"/results/{class_id}", status_code=303)

    db.commit()

    msg = f"Đã lưu điểm lớp {cls.class_code}: {saved} học viên."
    if skipped:
        msg += f" Bỏ qua {skipped} học viên chưa nhập đủ điểm."
    flash(request, msg)
    return RedirectResponse(f"/results/{class_id}", status_code=303)


# ==================== ROUTES HỌC VIÊN ====================

@student_router.get("")
def my_results(request: Request,
               user: User = Depends(require_roles("student")),
               db: Session = Depends(get_db)):
    student = _get_student(db, user)
    if not student:
        return render(request, "403.html", user=user, status_code=403)

    rows = (db.query(Result)
            .filter(Result.student_id == student.student_id)
            .join(ClassRoom, Result.class_id == ClassRoom.class_id)
            .order_by(ClassRoom.class_code).all())

    return render(request, "my_results.html", user=user,
                  student=student, results=rows)