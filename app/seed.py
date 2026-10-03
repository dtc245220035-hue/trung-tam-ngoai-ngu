from datetime import date, datetime, time

from sqlalchemy.orm import Session

from .models import (Attendance, ClassRoom, Course, Enrollment, Facility,
                     Invoice, Payment, Policy, Result, Salary, Schedule,
                     Student, Teacher, User)
from .security import hash_password
from .utils import rank_for

START, END = date(2026, 9, 14), date(2026, 12, 20)


def _user(db, username, pw, name, role, phone, email):
    u = User(username=username, password_hash=hash_password(pw), full_name=name,
             role=role, phone=phone, email=email, status="active")
    db.add(u)
    db.flush()
    return u


def seed(db: Session) -> None:
    if db.query(User).first():
        return

    admin = _user(db, "admin", "admin123", "Đào Tùng Anh", "admin", "0900000001", "admin@trungtam.vn")
    tvv = _user(db, "tvv1", "tvv123", "Nguyễn Thị Lan", "consultant", "0900000002", "lan.tvv@trungtam.vn")

    teacher_rows = [
        ("gv1", "Nguyễn Minh Châu", "Tiếng Anh học thuật, IELTS", "IELTS 8.0, TESOL"),
        ("gv2", "Trần Quốc Bảo", "Tiếng Anh giao tiếp", "Cử nhân Ngôn ngữ Anh"),
        ("gv3", "Lê Thu Hà", "Tiếng Anh trung cấp", "Thạc sĩ Giảng dạy tiếng Anh"),
        ("gv4", "Phạm Hoàng Yến", "Tiếng Nhật sơ cấp", "JLPT N2"),
    ]
    teachers = []
    for i, (un, name, spec, deg) in enumerate(teacher_rows, 1):
        u = _user(db, un, "gv123", name, "teacher", f"091000000{i}", f"{un}@trungtam.vn")
        t = Teacher(user_id=u.user_id, teacher_code=f"GV{i:04d}", specialization=spec, degree=deg)
        db.add(t)
        teachers.append(t)

    student_rows = [
        ("Lê Hoàng Nam", "A1", date(2005, 3, 12)), ("Phạm Thị Mai", "A1", date(2006, 7, 21)),
        ("Vũ Đức Anh", "A2", date(2004, 11, 2)), ("Đỗ Khánh Linh", "A2", date(2003, 5, 18)),
        ("Bùi Quang Huy", "B1", date(2002, 9, 30)), ("Ngô Thùy Dung", "B1", date(2001, 1, 9)),
        ("Hoàng Gia Bảo", "B2", date(2000, 12, 25)), ("Trịnh Phương Thảo", "A1", date(2007, 4, 4)),
        ("Đặng Minh Tuấn", "A2", date(2005, 8, 16)), ("Cao Bảo Ngọc", "B1", date(2003, 2, 27)),
    ]
    students = []
    for i, (name, level, dob) in enumerate(student_rows, 1):
        u = _user(db, f"hv{i}", "hv123", name, "student", f"098000{i:04d}", f"hv{i}@mail.vn")
        s = Student(user_id=u.user_id, student_code=f"HV{i:04d}", level=level, date_of_birth=dob)
        db.add(s)
        students.append(s)

    course_rows = [
        ("Tiếng Anh giao tiếp A1", "A1", 3200000, 24, "Làm quen phát âm, mẫu câu hằng ngày"),
        ("Tiếng Anh giao tiếp A2", "A2", 3800000, 24, "Giao tiếp tình huống quen thuộc"),
        ("Tiếng Anh trung cấp B1", "B1", 4800000, 30, "Nghe nói đọc viết ở mức độc lập"),
        ("IELTS Foundation B2", "B2", 7500000, 36, "Nền tảng thi IELTS, mục tiêu 5.5 - 6.5"),
        ("Tiếng Nhật N5 cơ bản", "A1", 4200000, 30, "Bảng chữ cái, ngữ pháp và hội thoại sơ cấp"),
    ]
    courses = []
    for i, (name, level, fee, dur, desc) in enumerate(course_rows, 1):
        c = Course(course_code=f"KH{i:04d}", course_name=name, level=level,
                   tuition_fee=fee, duration=dur, description=desc)
        db.add(c)
        courses.append(c)
    db.flush()

    # (course idx, teacher idx, phòng, sĩ số tối đa, lịch)
    class_rows = [
        (0, 1, "P101", 15, [("Thứ 2", time(18, 0), time(19, 30)), ("Thứ 4", time(18, 0), time(19, 30))]),
        (0, 2, "P102", 15, [("Thứ 2", time(19, 45), time(21, 15)), ("Thứ 4", time(19, 45), time(21, 15))]),
        (1, 1, "P103", 15, [("Thứ 3", time(18, 0), time(19, 30)), ("Thứ 5", time(18, 0), time(19, 30))]),
        (2, 2, "P201", 20, [("Thứ 3", time(19, 45), time(21, 15)), ("Thứ 5", time(19, 45), time(21, 15))]),
        (3, 0, "P202", 12, [("Thứ 7", time(8, 0), time(11, 0)), ("Chủ nhật", time(8, 0), time(10, 0))]),
        (4, 3, "P104", 12, [("Thứ 6", time(18, 0), time(20, 0)), ("Thứ 7", time(14, 0), time(16, 0))]),
    ]
    classes = []
    for i, (ci, ti, room, mx, sched) in enumerate(class_rows, 1):
        cl = ClassRoom(class_code=f"LOP{i:04d}", course_id=courses[ci].course_id,
                       teacher_id=teachers[ti].teacher_id, room=room, max_students=mx,
                       current_students=0, status="open")
        db.add(cl)
        db.flush()
        for day, st, et in sched:
            db.add(Schedule(class_id=cl.class_id, day_of_week=day, start_time=st,
                            end_time=et, start_date=START, end_date=END))
        classes.append(cl)
    db.flush()

    # (học viên idx, lớp idx, số tiền đã đóng)
    enroll_rows = [
        (0, 0, 3200000), (1, 0, 1600000), (7, 1, 0), (2, 2, 3800000), (3, 2, 2000000),
        (4, 3, 4800000), (5, 3, 0), (9, 3, 2400000), (6, 4, 7500000), (8, 5, 1000000),
    ]
    for n, (si, ci, paid) in enumerate(enroll_rows, 1):
        st, cl = students[si], classes[ci]
        db.add(Enrollment(student_id=st.student_id, class_id=cl.class_id, status="active"))
        cl.current_students += 1
        total = cl.course.tuition_fee
        status = "paid" if paid >= total else ("partial" if paid > 0 else "unpaid")
        inv = Invoice(invoice_code=f"HD{n:04d}", student_id=st.student_id, class_id=cl.class_id,
                      total_amount=total, paid_amount=paid, status=status)
        db.add(inv)
        db.flush()
        if paid > 0:
            db.add(Payment(invoice_id=inv.invoice_id, amount=paid,
                           method="cash" if n % 2 else "transfer", created_by=tvv.user_id,
                           note="Đóng học phí đợt 1"))

    sessions = {
        0: [date(2026, 9, 14), date(2026, 9, 16), date(2026, 9, 21), date(2026, 9, 23)],
        2: [date(2026, 9, 15), date(2026, 9, 17), date(2026, 9, 22), date(2026, 9, 24)],
        3: [date(2026, 9, 15), date(2026, 9, 17), date(2026, 9, 22), date(2026, 9, 24)],
    }
    for si, ci, _ in enroll_rows:
        for k, d in enumerate(sessions.get(ci, [])):
            mark = (si + k) % 5
            status = "absent" if mark == 0 else ("late" if mark == 3 else "present")
            db.add(Attendance(class_id=classes[ci].class_id, student_id=students[si].student_id,
                              session_date=d, status=status))

    score_rows = [
        (0, 0, 8.0, 7.5, 8.5, 7.0, "Phát âm tốt, cần luyện viết thêm"),
        (1, 0, 6.0, 5.5, 7.0, 6.0, "Hay vắng buổi, cần theo sát hơn"),
        (4, 3, 7.5, 7.0, 8.0, 7.5, "Tiến bộ đều, tự tin khi nói"),
        (5, 3, 5.0, 4.5, 6.0, 5.0, "Nền tảng ngữ pháp còn yếu"),
    ]
    for si, ci, l, s, r, w, cmt in score_rows:
        avg = round((l + s + r + w) / 4, 2)
        db.add(Result(student_id=students[si].student_id, class_id=classes[ci].class_id,
                      listening=l, speaking=s, reading=r, writing=w,
                      average=avg, rank=rank_for(avg), comment=cmt))

    # ============ Cơ sở vật chất mẫu ============
    facility_rows = [
        ("Phòng học P101", "room", "P101", 1, 0, "Phòng học tiêu chuẩn 15 chỗ"),
        ("Phòng học P102", "room", "P102", 1, 0, "Phòng học tiêu chuẩn 15 chỗ"),
        ("Phòng học P201", "room", "P201", 1, 0, "Phòng học lớn 20 chỗ"),
        ("Phòng học P202", "room", "P202", 1, 0, "Phòng học lớn 20 chỗ"),
        ("Máy chiếu Epson", "equipment", None, 4, 8500000, "Máy chiếu cho phòng học"),
        ("Bảng tương tác", "equipment", None, 2, 25000000, "Bảng tương tác thông minh"),
        ("Máy tính bàn", "equipment", None, 10, 12000000, "Máy tính cho phòng lab"),
        ("Tai nghe học ngoại ngữ", "equipment", None, 30, 350000, "Tai nghe chuyên dụng"),
    ]
    for i, (name, ftype, room, qty, price, note) in enumerate(facility_rows, 1):
        db.add(Facility(
            facility_code=f"CS{i:04d}",
            facility_name=name,
            facility_type=ftype,
            room=room,
            quantity=qty,
            unit_price=price,
            purchase_date=date(2025, 6, 1),
            status="active",
            note=note,
        ))

    # ============ Lương GV mẫu (3 tháng) ============
    for t_idx, t in enumerate(teachers):
        for m_idx, month in enumerate(["2026-09", "2026-10", "2026-11"]):
            base = 8000000 if t_idx < 2 else 7000000
            hours = 40 + t_idx * 5 + m_idx * 2
            hourly = 150000
            bonus = 500000 if (t_idx == 0 and m_idx == 2) else 0
            deduction = 200000 if m_idx == 1 else 0
            total = base + hours * hourly + bonus - deduction
            paid_date_val = None
            if month == "2026-09":
                paid_date_val = datetime(2026, 10, 5)
            elif month == "2026-10":
                paid_date_val = datetime(2026, 11, 5)
            db.add(Salary(
                teacher_id=t.teacher_id,
                month=month,
                base_salary=base,
                teaching_hours=hours,
                hourly_rate=hourly,
                bonus=bonus,
                deduction=deduction,
                total_salary=total,
                status="paid" if month != "2026-11" else "pending",
                paid_date=paid_date_val,
                note=f"Lương tháng {month}",
            ))

    # ============ Chính sách ưu đãi mẫu ============
    policy_rows = [
        ("Giảm 20% HV khó khăn", "percent", 20,
         "Giảm 20% học phí cho học viên có hoàn cảnh khó khăn (có xác nhận)"),
        ("Giảm 10% HV đăng ký sớm", "percent", 10,
         "Giảm 10% khi đăng ký trước khai giảng 2 tuần"),
        ("Miễn giảm 500K HV khuyết tật", "fixed", 500000,
         "Hỗ trợ 500.000đ cho học viên khuyết tật"),
        ("Ưu đãi HV giỏi", "percent", 15,
         "Giảm 15% cho học viên có thành tích học tập tốt"),
    ]
    for i, (name, dtype, dvalue, desc) in enumerate(policy_rows, 1):
        db.add(Policy(
            policy_code=f"CS{i:04d}",
            policy_name=name,
            discount_type=dtype,
            discount_value=dvalue,
            description=desc,
            status="active",
        ))

    db.commit()