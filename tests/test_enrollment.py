"""Test module đăng ký học (yêu cầu đề bài)."""
import pytest

from app.models import ClassRoom, Enrollment, Invoice, Student


def _get_student(db, code):
    return db.query(Student).filter(Student.student_code == code).first()


def _get_class(db, code):
    return db.query(ClassRoom).filter(ClassRoom.class_code == code).first()


# ============ TC-ENR-01: Đăng ký thành công ============
def test_enroll_success(tvv_client, db):
    """HV chưa học lớp → đăng ký thành công, sinh hóa đơn."""
    s = _get_student(db, "HV0008")   # Thảo, chưa học LOP0002
    c = _get_class(db, "LOP0002")
    assert s and c, "Seed data thiếu"

    # Đảm bảo chưa có đăng ký
    existing = (db.query(Enrollment)
                .filter(Enrollment.student_id == s.student_id,
                        Enrollment.class_id == c.class_id,
                        Enrollment.status == "active").first())
    if existing:
        pytest.skip("HV đã có đăng ký sẵn, không test được")

    invoice_before = db.query(Invoice).count()
    seats_before = c.current_students

    r = tvv_client.post("/enroll/new", data={
        "student_id": s.student_id,
        "class_id": c.class_id,
    }, follow_redirects=False)

    assert r.status_code == 303, f"Kỳ vọng 303, nhận {r.status_code}"

    db.expire_all()
    e = (db.query(Enrollment)
         .filter(Enrollment.student_id == s.student_id,
                 Enrollment.class_id == c.class_id,
                 Enrollment.status == "active").first())
    assert e is not None, "Không có bản ghi Enrollment"

    c = db.get(ClassRoom, c.class_id)
    assert c.current_students == seats_before + 1, "Sĩ số không tăng"

    invoice_after = db.query(Invoice).count()
    assert invoice_after == invoice_before + 1, "Không sinh hóa đơn"


# ============ TC-ENR-02: Đăng ký trùng → bị chặn ============
def test_enroll_duplicate(tvv_client, db):
    """HV đã có trong lớp → không cho đăng ký lại."""
    s = _get_student(db, "HV0001")   # đã có LOP0001
    c = _get_class(db, "LOP0001")

    r = tvv_client.post("/enroll/new", data={
        "student_id": s.student_id,
        "class_id": c.class_id,
    }, follow_redirects=False)

    # 400 vì có lỗi, render lại form
    assert r.status_code == 400, f"Kỳ vọng 400, nhận {r.status_code}"
    assert "đã đăng ký" in r.text.lower()


# ============ TC-ENR-03: Đăng ký lớp đã đóng → bị chặn ============
def test_enroll_closed_class(tvv_client, db):
    """Lớp đã đóng → không nhận đăng ký."""
    s = _get_student(db, "HV0007")

    # Tạo 1 lớp tạm đóng
    from app.models import Course
    course = db.query(Course).first()
    closed = ClassRoom(
        class_code="TEST_CLOSED",
        course_id=course.course_id,
        teacher_id=None,
        room="X1",
        max_students=10,
        current_students=0,
        status="closed",
    )
    db.add(closed)
    db.commit()
    cid = closed.class_id

    r = tvv_client.post("/enroll/new", data={
        "student_id": s.student_id,
        "class_id": cid,
    }, follow_redirects=False)

    assert r.status_code == 400
    assert "đã đóng" in r.text.lower()

    # Cleanup
    db.delete(db.get(ClassRoom, cid))
    db.commit()


# ============ TC-ENR-04: Hủy đăng ký chưa đóng tiền → OK ============
def test_cancel_enrollment_no_payment(tvv_client, db):
    """Hủy đăng ký khi hóa đơn chưa đóng → OK."""
    # Tìm enrollment active có invoice unpaid
    enroll = (db.query(Enrollment)
              .join(Invoice, (Invoice.student_id == Enrollment.student_id) &
                             (Invoice.class_id == Enrollment.class_id))
              .filter(Enrollment.status == "active", Invoice.paid_amount == 0)
              .first())
    if not enroll:
        pytest.skip("Không có enrollment nào unpaid để test")

    eid = enroll.enrollment_id
    cid = enroll.class_id
    seats_before = db.get(ClassRoom, cid).current_students

    r = tvv_client.post(f"/enroll/{eid}/cancel", follow_redirects=False)
    assert r.status_code == 303

    db.expire_all()
    e = db.get(Enrollment, eid)
    assert e.status == "cancelled"

    c = db.get(ClassRoom, cid)
    assert c.current_students == seats_before - 1


# ============ TC-ENR-05: Hủy đăng ký đã đóng tiền → bị chặn ============
def test_cancel_enrollment_with_payment(tvv_client, db):
    """Hủy đăng ký khi HV đã đóng tiền → bị chặn."""
    # Tìm enrollment active có invoice đã nộp > 0
    enroll = (db.query(Enrollment)
              .join(Invoice, (Invoice.student_id == Enrollment.student_id) &
                             (Invoice.class_id == Enrollment.class_id))
              .filter(Enrollment.status == "active", Invoice.paid_amount > 0)
              .first())
    if not enroll:
        pytest.skip("Không có enrollment nào đã đóng để test")

    r = tvv_client.post(f"/enroll/{enroll.enrollment_id}/cancel",
                        follow_redirects=False)
    assert r.status_code == 303

    db.expire_all()
    e = db.get(Enrollment, enroll.enrollment_id)
    assert e.status == "active", "Đăng ký không được hủy khi đã đóng tiền"