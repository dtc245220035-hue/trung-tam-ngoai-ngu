---
name: trung-tam-ngoai-ngu
description: Hướng dẫn làm việc với dự án "Hệ thống quản lý trung tâm ngoại ngữ có tích hợp AI" (Nhóm 42, FastAPI + SQLite + Gemini). Dùng khi cần chạy demo, thêm hoặc sửa chức năng, sửa lỗi, viết test, hoặc chỉnh 3 chức năng AI (tư vấn lớp, sinh bài luyện tập, tóm tắt tiến độ) của dự án này.
---

# Trung tâm ngoại ngữ tích hợp AI

Ứng dụng web quản lý học viên, khóa học, lớp, giáo viên, lịch học, đăng ký, học phí, điểm danh, kết quả học tập, kèm 3 chức năng AI. Đồ án môn Ứng dụng trí tuệ nhân tạo.

## Công nghệ
FastAPI, SQLAlchemy 2.0, SQLite, Jinja2 (render phía server), đăng nhập bằng session, mật khẩu băm bcrypt, AI qua Google Gemini API.

## Chạy và kiểm thử
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # điền GEMINI_API_KEY nếu muốn gọi AI thật
uvicorn app.main:app --reload # http://127.0.0.1:8000
pytest                        # chạy toàn bộ test trong tests/
```
Lần chạy đầu tự tạo `trung_tam.db` và dữ liệu mẫu. Muốn reset: tắt server, xóa `trung_tam.db`, chạy lại.
Tài khoản demo: admin/admin123, tvv1/tvv123, gv1..gv4/gv123, hv1..hv10/hv123.

## Cấu trúc
- `app/main.py`: tạo app, session, đăng nhập/đăng xuất, dashboard, đăng ký các router.
- `app/<chức_năng>.py`: mỗi chức năng một router có `prefix` riêng (students, teachers, courses, classes, enrollments, invoices, attendance, results, lookup, stats, ai, self_service).
- `app/models.py`: toàn bộ bảng. Xem `references/database.md`.
- `app/deps.py`: `current_user`, `require_roles(...)` để phân quyền.
- `app/web.py`: `render()`, `flash()`, `MENU` (menu theo vai trò).
- `app/utils.py`: hàm dùng chung (`schedule_text`, `rank_for`, định dạng tiền).
- `app/seed.py`: dữ liệu mẫu, chỉ chạy khi CSDL rỗng.
- `app/templates/`: đặt tên `<chức_năng>_list.html`, `<chức_năng>_form.html`.
- `tests/`: `test_ai.py`, `test_attendance.py`, `test_enrollment.py`, `test_invoice.py`.

## Thêm một chức năng mới
1. Thêm model vào `models.py`, kèm `CheckConstraint` cho các ràng buộc (số dương, giá trị trạng thái hợp lệ).
2. Tạo `app/<tên>.py` với `APIRouter(prefix="/<tên>")`; mọi route phải có `Depends(require_roles(...))`.
3. `include_router` trong `main.py`.
4. Thêm mục vào `MENU` trong `web.py` đúng vai trò.
5. Tạo template `_list` và `_form`.
6. Viết test trong `tests/` cho luồng đúng và ít nhất một luồng lỗi.
Vai trò và đường dẫn hiện có: `references/roles-and-routes.md`.

## Quy tắc nghiệp vụ cần giữ
- Đăng nhập sai 5 lần thì khóa tạm 15 phút; thông báo lỗi sai tài khoản và sai mật khẩu giống nhau.
- Sĩ số tối đa của lớp từ 1 đến 30; không đăng ký khi lớp đầy hoặc đã đóng; một học viên không đăng ký trùng một lớp.
- Trình độ học viên khác trình độ khóa học thì cảnh báo và yêu cầu xác nhận.
- Hóa đơn có 3 trạng thái: `unpaid`, `partial`, `paid`. Không thanh toán số tiền <= 0 hoặc vượt số còn nợ; hóa đơn đã đủ thì không thu thêm.
- Điểm danh (`present`, `late`, `absent`): không điểm danh buổi chưa diễn ra, phải điểm danh đủ cả lớp, điểm danh lại thì ghi đè.
- Điểm 4 kỹ năng trong khoảng 0 đến 10; xếp loại: >=9 Xuất sắc, >=8 Giỏi, >=6.5 Khá, >=5 Trung bình, còn lại Yếu.
- Xóa học viên là xóa mềm (`is_deleted`), giữ lịch sử học tập.

## Chức năng AI
Ba chức năng, đều có phương án dự phòng khi Gemini lỗi hoặc thiếu key để hệ thống không bao giờ bị hỏng theo. Chi tiết: `references/ai-integration.md`. Nguyên tắc khi sửa:
- AI chỉ được gợi ý lớp có trong CSDL; luôn kiểm chứng kết quả trước khi hiển thị.
- Không gửi họ tên, số điện thoại, email cho AI. Chỉ gửi trình độ, lịch rảnh, dữ liệu lớp, số liệu học tập.
- Gọi Gemini tối đa 3 lần; hết lượt thì dùng dự phòng và nói rõ cho người dùng.
- Không cam kết kết quả học tập trong nội dung AI sinh ra.

## Những điều cần lưu ý
- Không đưa `.env` (chứa API key), `.venv`, `.git`, `*.db` vào file nộp hoặc gửi cho người khác.
- Code dùng `from google import genai` (thư viện `google-genai`). Nếu `requirements.txt` ghi `google-generativeai` thì phải đổi, nếu không AI luôn rơi vào dự phòng mà không báo lỗi.
- Các module `facilities` (cơ sở vật chất), `salaries` (lương giáo viên), `policies` (chính sách giảm học phí) nằm ngoài đề tài và không có trong báo cáo; chỉ sửa khi được yêu cầu.
- Mục menu "Tài khoản" (`/accounts`) của admin chưa có route tương ứng nên sẽ báo 404.
