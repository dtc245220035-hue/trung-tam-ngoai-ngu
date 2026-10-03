from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import Attendance, ClassRoom, Enrollment, Student, Teacher, User
from .web import flash, render

router = APIRouter(prefix="/attendance", tags=["attendance"])

VALID_STATUS = ("present", "absent", "late")


def _get_teacher(db: Session, user: User) -> Teacher | None:
    return db.query(Teacher).filter(Teacher.user_id == user.user_id).first()


def _my_classes(db: Session, teacher: Teacher):
    return (db.query(ClassRoom)
            .filter(ClassRoom.teacher_id == teacher.teacher_id)
            .order_by(ClassRoom.class_code).all())


def _class_students(db: Session, class_id: int):
    enrolls = (db.query(Enrollment)
               .filter(Enrollment.class_id == class_id,
                       Enrollment.status == "active")
               .join(Student, Enrollment.student_id == Student.student_id)
               .join(User, Student.user_id == User.user_id)
               .order_by(Student.student_code).all())
    return [e.student for e in enrolls]


def _class_start_date(cls: ClassRoom) -> date | None:
    if not cls.schedules:
        return None
    return min(s.start_date for s in cls.schedules)


@router.get("")
def attendance_home(request: Request,
                    user: User = Depends(require_roles("teacher")),
                    db: Session = Depends(get_db)):
    teacher = _get_teacher(db, user)
    if not teacher:
        return render(request, "403.html", user=user, status_code=403)

    classes = _my_classes(db, teacher)
    today = date.today()

    # Đếm số buổi đã điểm danh mỗi lớp
    stats = {}
    for c in classes:
        n_sessions = (db.query(Attendance.session_date)
                      .filter(Attendance.class_id == c.class_id)
                      .distinct().count())
        n_today = (db.query(Attendance)
                   .filter(Attendance.class_id == c.class_id,
                           Attendance.session_date == today).count())
        stats[c.class_id] = {"n_sessions": n_sessions, "done_today": n_today > 0}

    return render(request, "attendance_classes.html", user=user,
                  classes=classes, stats=stats, today=today)


@router.get("/{class_id}")
def attendance_form(class_id: int,
                    request: Request,
                    session_date: str = "",
                    user: User = Depends(require_roles("teacher")),
                    db: Session = Depends(get_db)):
    teacher = _get_teacher(db, user)
    cls = db.get(ClassRoom, class_id)
    if not cls or not teacher or cls.teacher_id != teacher.teacher_id:
        return render(request, "403.html", user=user, status_code=403)

    # Xác định ngày
    sd = date.today()
    if session_date:
        try:
            sd = date.fromisoformat(session_date)
        except ValueError:
            pass

    error = None
    if sd > date.today():
        error = "Không thể điểm danh ngày trong tương lai."
        sd = date.today()

    start_date = _class_start_date(cls)
    if start_date and sd < start_date:
        error = f"Ngày điểm danh phải từ {start_date.strftime('%d/%m/%Y')} trở đi (ngày bắt đầu khóa)."
        sd = start_date

    students = _class_students(db, class_id)

    # Lấy điểm danh cũ của ngày đó
    existing = {}
    if students:
        rows = (db.query(Attendance)
                .filter(Attendance.class_id == class_id,
                        Attendance.session_date == sd).all())
        existing = {r.student_id: r for r in rows}

    return render(request, "attendance_form.html", user=user,
                  classroom=cls, students=students,
                  session_date=sd.isoformat(), existing=existing,
                  start_date=start_date.isoformat() if start_date else "",
                  error=error)


@router.post("/{class_id}")
async def save_attendance(class_id: int,
                          request: Request,
                          user: User = Depends(require_roles("teacher")),
                          db: Session = Depends(get_db)):
    teacher = _get_teacher(db, user)
    cls = db.get(ClassRoom, class_id)
    if not cls or not teacher or cls.teacher_id != teacher.teacher_id:
        return render(request, "403.html", user=user, status_code=403)

    form = await request.form()
    raw_date = (form.get("session_date") or "").strip()

    try:
        sd = date.fromisoformat(raw_date)
    except ValueError:
        flash(request, "Ngày điểm danh không hợp lệ", kind="err")
        return RedirectResponse(f"/attendance/{class_id}", status_code=303)

    if sd > date.today():
        flash(request, "Không thể điểm danh ngày trong tương lai.", kind="err")
        return RedirectResponse(f"/attendance/{class_id}", status_code=303)

    start_date = _class_start_date(cls)
    if start_date and sd < start_date:
        flash(request, f"Ngày điểm danh phải từ {start_date.strftime('%d/%m/%Y')} trở đi.",
              kind="err")
        return RedirectResponse(f"/attendance/{class_id}", status_code=303)

    students = _class_students(db, class_id)
    if not students:
        flash(request, "Lớp chưa có học viên nào để điểm danh.", kind="err")
        return RedirectResponse("/attendance", status_code=303)

    # Validate: tất cả HV phải có status hợp lệ
    statuses: dict[int, str] = {}
    missing: list[str] = []
    for s in students:
        st = (form.get(f"status_{s.student_id}") or "").strip()
        if st not in VALID_STATUS:
            missing.append(s.user.full_name)
        else:
            statuses[s.student_id] = st

    if missing:
        flash(request, "Chưa điểm danh đủ: " + ", ".join(missing[:5]) +
              ("..." if len(missing) > 5 else ""), kind="err")
        return RedirectResponse(f"/attendance/{class_id}?session_date={sd.isoformat()}",
                                status_code=303)

    # Upsert: có rồi thì update, chưa có thì insert
    existing_rows = (db.query(Attendance)
                     .filter(Attendance.class_id == class_id,
                             Attendance.session_date == sd).all())
    existing_map = {r.student_id: r for r in existing_rows}

    added, updated = 0, 0
    for s in students:
        st = statuses[s.student_id]
        note = (form.get(f"note_{s.student_id}") or "").strip() or None
        if s.student_id in existing_map:
            row = existing_map[s.student_id]
            if row.status != st or row.note != note:
                row.status = st
                row.note = note
                updated += 1
        else:
            db.add(Attendance(class_id=class_id, student_id=s.student_id,
                              session_date=sd, status=st, note=note))
            added += 1

    db.commit()

    msg = f"Đã lưu điểm danh lớp {cls.class_code} ngày {sd.strftime('%d/%m/%Y')}."
    if added and updated:
        msg += f" (Thêm mới {added}, cập nhật {updated} học viên)"
    elif added:
        msg += f" ({added} học viên)"
    elif updated:
        msg += f" (Cập nhật {updated} học viên)"
    flash(request, msg)
    return RedirectResponse(f"/attendance/{class_id}?session_date={sd.isoformat()}",
                            status_code=303)