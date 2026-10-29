# Tích hợp AI (Google Gemini)

Cấu hình trong `.env`: `GEMINI_API_KEY` (để trống thì chạy chế độ dự phòng), `GEMINI_MODEL` (mặc định `gemini-2.5-flash`). Mã nằm ở `app/ai.py`, hàm gọi chung `_call_gemini(system_prompt, user_prompt)`.

## Cơ chế chung
1. Gọi Gemini tối đa `MAX_RETRY = 3` lần.
2. Lỗi, hết lượt hoặc thiếu key: dùng hàm `_fallback_*` tương ứng, giao diện vẫn trả kết quả.
3. Kết quả dạng JSON phải qua parse có kiểm tra cấu trúc (có xử lý khối markdown bao quanh); sai cấu trúc thì dùng dự phòng.

## Ba chức năng
| Chức năng | Đầu vào | Đầu ra | Dự phòng |
|---|---|---|---|
| Tư vấn lớp (`/ai/advice`) | trình độ, lịch rảnh, danh sách lớp đang mở còn chỗ | tối đa vài lớp phù hợp kèm lý do | lọc theo trình độ và lịch trùng |
| Sinh bài luyện tập (`/ai/exercise`) | trình độ, chủ đề (Ngữ pháp, Từ vựng, Giao tiếp), số câu | danh sách câu trắc nghiệm 4 lựa chọn có đáp án và giải thích | ngân hàng câu hỏi có sẵn |
| Tóm tắt tiến độ (`/ai/progress`) | số buổi có mặt, trễ, vắng; điểm 4 kỹ năng; nhận xét giáo viên | tóm tắt, điểm mạnh, điểm cần cải thiện | tóm tắt tính trực tiếp từ số liệu |

## Prompt hệ thống mẫu (tư vấn lớp)
Bạn là trợ lý tư vấn trung tâm ngoại ngữ. Chỉ gợi ý lớp có trong dữ liệu và không cam kết kết quả học tập.

## Ràng buộc
- Không gửi thông tin định danh (họ tên, SĐT, email) cho AI.
- Không hiển thị lớp không tồn tại trong CSDL; nếu không có lớp phù hợp thì nói rõ là không có.
- Trình độ chưa rõ: không đoán, đề nghị làm bài kiểm tra đầu vào.
- Test AI ở `tests/test_ai.py` chạy không cần API key (kiểm tra phần dự phòng và parse JSON).
