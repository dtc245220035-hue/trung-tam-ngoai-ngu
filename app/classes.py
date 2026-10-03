from datetime import date, time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import ClassRoom, Course, Schedule, Teacher, User
from .utils import DAY_ORDER
from .web import flash, render

router = APIRouter(prefix="/classes", tags=["classes"])

VALID_DAYS = set(DAY_ORDER)


def _next_class_code(db: Session) -> str:
    n = db.query(ClassRoom).count() + 1
    while db.query(ClassRoom).filter(ClassRoom.class_code == f"LOP{n:04d}").first():
        n += 1
    return f"LOP{n:04d}"


def _parse_time(raw: str) -> time | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        h, m = raw.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def _parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _overlap(s1: time, e1: time, s2: time, e2: time) -> bool:
    return s1 < e2 and s2 < e1


def _check_conflict(db: Session, class_id: int | None, teacher_id: int | None,
                    room: str, schedules: list[tuple]) -> str | None:
    """Trả về thông báo lỗi nếu trùng lịch GV hoặc phòng, None nếu OK."""
    for day, st, et in schedules:
        # Check trùng lịch giáo viên
        if teacher_id:
            q = (db.query(Schedule)
                 .join(ClassRoom, Schedule.class_id == ClassRoom.class_id)
                 .filter(Schedule.day_of_week == day,
                         ClassRoom.teacher_id == teacher_id,
                         ClassRoom.status == "open"))
            if class_id:
                q = q.filter(ClassRoom.class_id != class_id)
            for s in q.all():
                if _overlap(st, et, s.start_time, s.end_time):
                    gv = s.classroom.teacher.user.full_name if s.classroom.teacher else "?"
                    return (f"Giáo viên {gv} trùng lịch: lớp {s.classroom.class_code} "
                            f"({s.day_of_week} {s.start_time:%H:%M}–{s.end_time:%H:%M})")
        # Check trùng phòng
        if room:
            q = (db.query(Schedule)
                 .join(ClassRoom, Schedule.class_id == ClassRoom.class_id)
                 .filter(Schedule.day_of_week == day,
                         ClassRoom.room == room,
                         ClassRoom.status == "open"))
            if class_id:
                q = q.filter(ClassRoom.class_id != class_id)
            for s in q.all():
                if _overlap(st, et, s.start_time, s.end_time):
                    return (f"Phòng {room} trùng lịch: lớp {s.classroom.class_code} "
                            f"({s.day_of_week} {s.start_time:%H:%M}–{s.end_time:%H:%M})")
    return None


def _parse_schedule_lists(days: list[str], starts: list[str], ends: list[str]):
    """Trả về (schedules, errors)."""
    schedules: list[tuple] = []
    errors: list[str] = []
    for i, (d, s, e) in enumerate(zip(days, starts, ends), 1):
        d = (d or "").strip()
        st = _parse_time(s)
        et = _parse_time(e)
        if not d or not st or not et:
            errors.append(f"Lịch #{i}: thiếu thông tin")
            continue
        if d not in VALID_DAYS:
            errors.append(f"Lịch #{i}: thứ không hợp lệ")
            continue
        if et <= st:
            errors.append(f"Lịch #{i}: giờ kết thúc phải sau giờ bắt đầu")
            continue
        schedules.append((d, st, et))
    if not schedules:
        errors.append("Phải có ít nhất 1 lịch học hợp lệ")
    return schedules, errors


@router.get("")
def list_classes(request: Request,
                 q: str = "",
                 status: str = "",
                 user: User = Depends(require_roles("admin")),
                 db: Session = Depends(get_db)):
    query = db.query(ClassRoom).join(Course, ClassRoom.course_id == Course.course_id)

    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            ClassRoom.class_code.ilike(like),
            Course.course_name.ilike(like),
            ClassRoom.room.ilike(like),
        ))
    if status in ("open", "closed"):
        query = query.filter(ClassRoom.status == status)

    classes = query.order_by(ClassRoom.class_code).all()
    return render(request, "classes_list.html", user=user,
                  classes=classes, q=q, status=status)


def _form_context(db: Session, form: dict, schedules: list[dict]):
    courses = db.query(Course).order_by(Course.course_code).all()
    teachers = (db.query(Teacher).filter(Teacher.status == "active")
                .join(User, Teacher.user_id == User.user_id)
                .order_by(User.full_name).all())
    return {
        "courses": courses,
        "teachers": teachers,
        "days": DAY_ORDER,
        "form": form,
        "form_schedules": schedules or [{"day": "Thứ 2", "start": "18:00", "end": "19:30"}],
    }


@router.get("/new")
def new_class_form(request: Request,
                   user: User = Depends(require_roles("admin")),
                   db: Session = Depends(get_db)):
    ctx = _form_context(db, {}, [])
    return render(request, "class_form.html", user=user, mode="new", **ctx)


@router.post("/new")
async def create_class(request: Request,
                       course_id: int = Form(...),
                       teacher_id: str = Form(""),
                       room: str = Form(""),
                       max_students: int = Form(...),
                       start_date: str = Form(""),
                       end_date: str = Form(""),
                       status: str = Form("open"),
                       user: User = Depends(require_roles("admin")),
                       db: Session = Depends(get_db)):
    form_data = await request.form()
    days = form_data.getlist("day_of_week")
    starts = form_data.getlist("start_time")
    ends = form_data.getlist("end_time")

    schedules, errors = _parse_schedule_lists(days, starts, ends)

    if not db.get(Course, course_id):
        errors.append("Khóa học không tồn tại")
    if max_students <= 0 or max_students > 30:
        errors.append("Sĩ số tối đa phải từ 1 đến 30")
    sd = _parse_date(start_date)
    ed = _parse_date(end_date)
    if not sd or not ed:
        errors.append("Ngày bắt đầu và kết thúc là bắt buộc")
    elif sd >= ed:
        errors.append("Ngày kết thúc phải sau ngày bắt đầu")

    t_id = int(teacher_id) if teacher_id and teacher_id.isdigit() else None
    room = room.strip()

    if not errors and schedules:
        conflict = _check_conflict(db, None, t_id, room, schedules)
        if conflict:
            errors.append(conflict)

    form = {"course_id": course_id, "teacher_id": t_id, "room": room,
            "max_students": max_students, "start_date": start_date,
            "end_date": end_date, "status": status}
    form_sched = [{"day": d, "start": s, "end": e}
                  for d, s, e in zip(days, starts, ends)]

    if errors:
        ctx = _form_context(db, form, form_sched)
        return render(request, "class_form.html", user=user, mode="new",
                      **ctx, error=" | ".join(errors), status_code=400)

    cl = ClassRoom(class_code=_next_class_code(db),
                   course_id=course_id,
                   teacher_id=t_id,
                   room=room or None,
                   max_students=max_students,
                   current_students=0,
                   status=status)
    db.add(cl)
    db.flush()
    for day, st, et in schedules:
        db.add(Schedule(class_id=cl.class_id, day_of_week=day,
                        start_time=st, end_time=et,
                        start_date=sd, end_date=ed))
    db.commit()

    flash(request, f"Đã tạo lớp {cl.class_code}")
    return RedirectResponse("/classes", status_code=303)


@router.get("/{class_id}/edit")
def edit_class_form(class_id: int,
                    request: Request,
                    user: User = Depends(require_roles("admin")),
                    db: Session = Depends(get_db)):
    cl = db.get(ClassRoom, class_id)
    if not cl:
        return render(request, "404.html", user=user, status_code=404)

    form = {"course_id": cl.course_id, "teacher_id": cl.teacher_id, "room": cl.room or "",
            "max_students": cl.max_students, "status": cl.status,
            "start_date": cl.schedules[0].start_date.isoformat() if cl.schedules else "",
            "end_date": cl.schedules[0].end_date.isoformat() if cl.schedules else ""}
    form_sched = [{"day": s.day_of_week,
                   "start": s.start_time.strftime("%H:%M"),
                   "end": s.end_time.strftime("%H:%M")} for s in cl.schedules]
    ctx = _form_context(db, form, form_sched)
    return render(request, "class_form.html", user=user, mode="edit", classroom=cl, **ctx)


@router.post("/{class_id}/edit")
async def update_class(class_id: int,
                       request: Request,
                       course_id: int = Form(...),
                       teacher_id: str = Form(""),
                       room: str = Form(""),
                       max_students: int = Form(...),
                       start_date: str = Form(""),
                       end_date: str = Form(""),
                       status: str = Form("open"),
                       user: User = Depends(require_roles("admin")),
                       db: Session = Depends(get_db)):
    cl = db.get(ClassRoom, class_id)
    if not cl:
        return render(request, "404.html", user=user, status_code=404)

    form_data = await request.form()
    days = form_data.getlist("day_of_week")
    starts = form_data.getlist("start_time")
    ends = form_data.getlist("end_time")

    schedules, errors = _parse_schedule_lists(days, starts, ends)

    if not db.get(Course, course_id):
        errors.append("Khóa học không tồn tại")
    if max_students <= 0 or max_students > 30:
        errors.append("Sĩ số tối đa phải từ 1 đến 30")
    if max_students < cl.current_students:
        errors.append(f"Sĩ số tối đa không thể nhỏ hơn sĩ số hiện tại ({cl.current_students})")
    sd = _parse_date(start_date)
    ed = _parse_date(end_date)
    if not sd or not ed:
        errors.append("Ngày bắt đầu và kết thúc là bắt buộc")
    elif sd >= ed:
        errors.append("Ngày kết thúc phải sau ngày bắt đầu")

    t_id = int(teacher_id) if teacher_id and teacher_id.isdigit() else None
    room = room.strip()

    if not errors and schedules:
        conflict = _check_conflict(db, class_id, t_id, room, schedules)
        if conflict:
            errors.append(conflict)

    form = {"course_id": course_id, "teacher_id": t_id, "room": room,
            "max_students": max_students, "start_date": start_date,
            "end_date": end_date, "status": status}
    form_sched = [{"day": d, "start": s, "end": e}
                  for d, s, e in zip(days, starts, ends)]

    if errors:
        ctx = _form_context(db, form, form_sched)
        return render(request, "class_form.html", user=user, mode="edit",
                      classroom=cl, **ctx, error=" | ".join(errors), status_code=400)

    cl.course_id = course_id
    cl.teacher_id = t_id
    cl.room = room or None
    cl.max_students = max_students
    cl.status = status
    # Xóa lịch cũ, thêm lịch mới
    cl.schedules.clear()
    db.flush()
    for day, st, et in schedules:
        cl.schedules.append(Schedule(day_of_week=day, start_time=st,
                                     end_time=et, start_date=sd, end_date=ed))
    db.commit()

    flash(request, f"Đã cập nhật lớp {cl.class_code}")
    return RedirectResponse("/classes", status_code=303)


@router.post("/{class_id}/delete")
def delete_class(class_id: int,
                 request: Request,
                 user: User = Depends(require_roles("admin")),
                 db: Session = Depends(get_db)):
    cl = db.get(ClassRoom, class_id)
    if not cl:
        return render(request, "404.html", user=user, status_code=404)

    if cl.current_students > 0:
        flash(request, f"Lớp {cl.class_code} đang có {cl.current_students} học viên. "
                       f"Chỉ có thể đóng lớp, không thể xóa.", kind="err")
        return RedirectResponse("/classes", status_code=303)

    code = cl.class_code
    db.delete(cl)
    db.commit()
    flash(request, f"Đã xóa lớp {code}")
    return RedirectResponse("/classes", status_code=303)


@router.post("/{class_id}/close")
def close_class(class_id: int,
                request: Request,
                user: User = Depends(require_roles("admin")),
                db: Session = Depends(get_db)):
    cl = db.get(ClassRoom, class_id)
    if not cl:
        return render(request, "404.html", user=user, status_code=404)
    cl.status = "closed"
    db.commit()
    flash(request, f"Đã đóng lớp {cl.class_code}")
    return RedirectResponse("/classes", status_code=303)


@router.post("/{class_id}/reopen")
def reopen_class(class_id: int,
                 request: Request,
                 user: User = Depends(require_roles("admin")),
                 db: Session = Depends(get_db)):
    cl = db.get(ClassRoom, class_id)
    if not cl:
        return render(request, "404.html", user=user, status_code=404)
    cl.status = "open"
    db.commit()
    flash(request, f"Đã mở lại lớp {cl.class_code}")
    return RedirectResponse("/classes", status_code=303)