"""Test module điểm danh (yêu cầu đề bài)."""
from datetime import date, timedelta

import pytest

from app.models import Attendance, ClassRoom, Enrollment, Student, Teacher, User


def _get_teacher_class(db, teacher_username="gv1"):
    """Lấy 1 lớp có GV phụ trách."""
    teacher = (db.query(Teacher)
               .join(User, Teacher.user_id == User.user_id)
               .filter(User.username == teacher_username).first())
    if not teacher:
        return None
    return (db.query(ClassRoom)
            .filter(ClassRoom.teacher_id == teacher.teacher_id,
                    ClassRoom.status == "open").first())


def _get_class_students(db, class_id):
    enrolls = (db.query(Enrollment)
               .filter(Enrollment.class_id == class_id,
                       Enrollment.status == "active").all())
    return [db.get(Student, e.student_id) for e in enrolls]


# ============ TC-ATT-01: Điểm danh thành công ============
def test_attendance_success(gv_client, db):
    cls = _get_teacher_class(db)
    if not cls:
        pytest.skip("GV chưa có lớp")

    students = _get_class_students(db, cls.class_id)
    if not students:
        pytest.skip("Lớp không có HV")

    # Ngày điểm danh = hôm nay (hoặc ngày bắt đầu khóa)
    session_date = date.today().isoformat()
    start = min(s.start_date for s in cls.schedules) if cls.schedules else None
    if start and date.today() < start:
        session_date = start.isoformat()

    data = {"session_date": session_date}
    for s in students:
        data[f"status_{s.student_id}"] = "present"

    r = gv_client.post(f"/attendance/{cls.class_id}", data=data,
                       follow_redirects=False)
    assert r.status_code == 303

    # Check DB
    n = (db.query(Attendance)
         .filter(Attendance.class_id == cls.class_id,
                 Attendance.session_date == date.fromisoformat(session_date))
         .count())
    assert n == len(students)


# ============ TC-ATT-02: Điểm danh thiếu HV → bị chặn ============
def test_attendance_missing(gv_client, db):
    cls = _get_teacher_class(db)
    if not cls:
        pytest.skip("GV chưa có lớp")

    students = _get_class_students(db, cls.class_id)
    if len(students) < 2:
        pytest.skip("Cần >= 2 HV")

    session_date = date.today().isoformat()
    start = min(s.start_date for s in cls.schedules) if cls.schedules else None
    if start and date.today() < start:
        session_date = start.isoformat()

    # Chỉ gửi status cho 1 HV đầu
    data = {"session_date": session_date}
    data[f"status_{students[0].student_id}"] = "present"
    # Không gửi status cho các HV còn lại

    r = gv_client.post(f"/attendance/{cls.class_id}", data=data,
                       follow_redirects=False)
    assert r.status_code == 303


# ============ TC-ATT-03: Ngày tương lai → bị chặn ============
def test_attendance_future_date(gv_client, db):
    cls = _get_teacher_class(db)
    if not cls:
        pytest.skip("GV chưa có lớp")

    future = (date.today() + timedelta(days=30)).isoformat()
    students = _get_class_students(db, cls.class_id)
    data = {"session_date": future}
    for s in students:
        data[f"status_{s.student_id}"] = "present"

    r = gv_client.post(f"/attendance/{cls.class_id}", data=data,
                       follow_redirects=False)
    assert r.status_code == 303

    # Không có bản ghi cho ngày tương lai
    n = (db.query(Attendance)
         .filter(Attendance.class_id == cls.class_id,
                 Attendance.session_date == date.fromisoformat(future))
         .count())
    assert n == 0


# ============ TC-ATT-04: Sửa điểm danh ============
def test_attendance_update(gv_client, db):
    """Sửa điểm danh lần 2 → cập nhật, không tạo bản ghi mới."""
    cls = _get_teacher_class(db)
    if not cls:
        pytest.skip("GV chưa có lớp")

    students = _get_class_students(db, cls.class_id)
    if not students:
        pytest.skip("Không có HV")

    session_date = date.today().isoformat()
    start = min(s.start_date for s in cls.schedules) if cls.schedules else None
    if start and date.today() < start:
        session_date = start.isoformat()

    # Lần 1: present tất cả
    data1 = {"session_date": session_date}
    for s in students:
        data1[f"status_{s.student_id}"] = "present"
    gv_client.post(f"/attendance/{cls.class_id}", data=data1,
                   follow_redirects=False)

    # Lần 2: đổi HV đầu thành absent
    data2 = {"session_date": session_date}
    data2[f"status_{students[0].student_id}"] = "absent"
    for s in students[1:]:
        data2[f"status_{s.student_id}"] = "present"
    gv_client.post(f"/attendance/{cls.class_id}", data=data2,
                   follow_redirects=False)

    db.expire_all()
    row = (db.query(Attendance)
           .filter(Attendance.class_id == cls.class_id,
                   Attendance.student_id == students[0].student_id,
                   Attendance.session_date == date.fromisoformat(session_date))
           .first())
    assert row is not None
    assert row.status == "absent"