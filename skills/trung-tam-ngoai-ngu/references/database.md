# Cơ sở dữ liệu (SQLite, SQLAlchemy)

Bật `PRAGMA foreign_keys=ON`. Tiền lưu dạng số thực (VND).

## Bảng lõi (theo đề tài)
| Bảng | Khóa và cột chính | Ràng buộc đáng chú ý |
|---|---|---|
| users | user_id, username (duy nhất), password_hash, full_name, email, phone, role, status, failed_attempts, locked_until | role in admin/consultant/teacher/student; status in active/inactive/locked |
| students | student_id, user_id, student_code, date_of_birth, level, note, is_deleted | level in A1..C2 hoặc rỗng; xóa mềm |
| teachers | teacher_id, user_id, teacher_code, specialization, degree, status | status in active/inactive |
| courses | course_id, course_code, course_name, level, tuition_fee, duration, description | học phí > 0, thời lượng > 0 |
| classes | class_id, class_code, course_id, teacher_id, room, max_students, current_students, status | 0 < max_students <= 30; current_students <= max_students; status in open/closed |
| schedules | schedule_id, class_id, day_of_week, start_time, end_time, start_date, end_date | end_time > start_time; start_date < end_date |
| enrollments | enrollment_id, student_id, class_id, enroll_date, status | duy nhất (student_id, class_id); status in active/cancelled |
| invoices | invoice_id, invoice_code, student_id, class_id, total_amount, discount_amount, paid_amount, policy_id, status | paid + discount <= total; status in unpaid/partial/paid |
| payments | payment_id, invoice_id, amount, method, payment_date, note, created_by | amount > 0; method in cash/transfer |
| attendance | attendance_id, class_id, student_id, session_date, status, note | duy nhất (class_id, student_id, session_date); status in present/absent/late |
| results | result_id, student_id, class_id, listening, speaking, reading, writing, average, rank, comment | mỗi điểm 0..10; duy nhất (student_id, class_id) |

## Bảng ngoài đề tài
facilities (cơ sở vật chất), salaries (lương giáo viên theo tháng), policies (chính sách giảm học phí; hóa đơn tham chiếu qua `policy_id`).

## Quan hệ chính
users 1-1 students/teachers; courses 1-n classes; teachers 1-n classes; classes 1-n schedules; students n-n classes qua enrollments; invoices thuộc (student, class) và có nhiều payments.
