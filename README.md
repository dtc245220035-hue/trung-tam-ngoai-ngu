# Hệ thống quản lý trung tâm ngoại ngữ có tích hợp AI (Nhóm 42)

FastAPI + SQLite (SQLAlchemy) + Jinja2, AI qua Google Gemini API.

## Chạy trên Windows
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```
Mở http://127.0.0.1:8000. Lần chạy đầu tự tạo CSDL `trung_tam.db` và dữ liệu mẫu.
Muốn reset dữ liệu: tắt server, xóa file `trung_tam.db`, chạy lại.

## Tài khoản demo
| Vai trò | Tên đăng nhập | Mật khẩu |
|---|---|---|
| Quản trị viên | admin | admin123 |
| Tư vấn viên | tvv1 | tvv123 |
| Giáo viên | gv1 đến gv4 | gv123 |
| Học viên | hv1 đến hv10 | hv123 |
