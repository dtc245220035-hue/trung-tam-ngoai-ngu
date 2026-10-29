# Vai trò và đường dẫn

Vai trò: admin (quản trị viên), consultant (tư vấn viên), teacher (giáo viên), student (học viên). Phân quyền bằng `require_roles(...)`; sai quyền trả về trang 403, chưa đăng nhập chuyển về `/login`.

| Đường dẫn | Chức năng | Vai trò |
|---|---|---|
| /login, /logout, /dashboard | đăng nhập, đăng xuất, tổng quan | tất cả |
| /students | học viên: danh sách, thêm, sửa, xóa mềm | admin, consultant |
| /teachers | giáo viên: danh sách, chi tiết, thêm, sửa, bật/tắt, xóa | admin |
| /courses | khóa học | admin |
| /classes | lớp và lịch học: thêm, sửa, đóng, mở lại, xóa | admin |
| /enroll | đăng ký học, hủy đăng ký | admin, consultant |
| /invoices | hóa đơn, thanh toán (`/pay`), áp chính sách giảm | admin, consultant |
| /attendance | điểm danh theo lớp và ngày | teacher |
| /results | nhập kết quả học tập | teacher |
| /my_classes | lớp đang dạy | teacher |
| /my_schedule, /my_results, /my_invoices | lịch học, kết quả, học phí của chính mình | student |
| /lookup | tra cứu lịch, lớp, học phí | admin, consultant, teacher |
| /stats | thống kê sĩ số, doanh thu, tỷ lệ hoàn thành | admin |
| /ai/advice | AI tư vấn lớp | consultant, admin |
| /ai/exercise | AI sinh bài luyện tập | teacher, student |
| /ai/progress | AI tóm tắt tiến độ | student |
| /facilities, /salaries, /policies | ngoài đề tài | admin |
