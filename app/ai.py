import json
import os
import re
import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_roles
from .models import (Attendance, ClassRoom, Course, Enrollment, Invoice,
                     Result, Student, Teacher, User)
from .utils import schedule_text
from .web import flash, render

router = APIRouter(prefix="/ai", tags=["ai"])

_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_RETRY = 3

_client = None
if _GEMINI_KEY:
    try:
        from google import genai
        _client = genai.Client(api_key=_GEMINI_KEY)
    except Exception as e:
        print(f"[AI] Cannot init Gemini client: {e}")
        _client = None


def _get_teacher(db: Session, user: User) -> Teacher | None:
    return db.query(Teacher).filter(Teacher.user_id == user.user_id).first()


def _get_student(db: Session, user: User) -> Student | None:
    return (db.query(Student)
            .filter(Student.user_id == user.user_id, Student.is_deleted.is_(False))
            .first())


def _call_gemini(system_prompt: str, user_prompt: str) -> str | None:
    if not _client:
        return None
    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = _client.models.generate_content(
                model=MODEL_NAME,
                contents=full_prompt,
            )
            text = (resp.text or "").strip()
            if text:
                return text
        except Exception as e:
            print(f"[AI] Attempt {attempt} failed: {e}")
        if attempt < MAX_RETRY:
            time.sleep(attempt)  # chờ 1s, 2s giữa các lần thử lại
    return None


# ============ 1. AI TƯ VẤN LỚP ============

CLASS_CODE_RE = re.compile(r"\b[A-Z]{2,4}\d{3,4}\b")


def _has_fake_class(text: str, classes: list) -> bool:
    """True nếu AI nhắc tới mã lớp không nằm trong danh sách lớp còn chỗ đã gửi cho nó."""
    valid = {c.class_code for c in classes}
    return any(code not in valid for code in CLASS_CODE_RE.findall(text))


def _fallback_advice(level: str, availability: str, classes: list) -> str:
    lines = ["**Gợi ý lớp phù hợp** (phương án dự phòng)\n"]
    matched = [c for c in classes if c.course.level == level]
    if not matched:
        matched = classes[:3]
        lines.append(f"_Không có lớp đúng trình độ {level}, gợi ý một số lớp đang mở:_\n")
    else:
        lines.append(f"_Các lớp trình độ {level} đang mở:_\n")
    for c in matched[:3]:
        lines.append(
            f"- **{c.class_code}** — {c.course.course_name} "
            f"({schedule_text(c)}) — còn {c.seats_left}/{c.max_students} chỗ"
        )
    lines.append("\n_Vui lòng liên hệ Tư vấn viên để xác nhận._")
    return "\n".join(lines)


def _format_classes_for_prompt(classes: list) -> str:
    rows = []
    for c in classes:
        rows.append(
            f"- Mã lớp: {c.class_code} | Khóa: {c.course.course_name} "
            f"| Trình độ: {c.course.level} | Lịch: {schedule_text(c)} "
            f"| Còn: {c.seats_left}/{c.max_students} chỗ"
        )
    return "\n".join(rows)


@router.get("/advice")
def ai_advice_page(request: Request,
                   user: User = Depends(require_roles("consultant", "admin")),
                   db: Session = Depends(get_db)):
    classes = (db.query(ClassRoom).filter(ClassRoom.status == "open")
               .order_by(ClassRoom.class_code).all())
    return render(request, "ai_advice.html", user=user,
                  result=None, level="", availability="",
                  n_classes=len(classes),
                  ai_available=bool(_client))


@router.post("/advice")
def ai_advice_submit(request: Request,
                     level: str = Form(""),
                     availability: str = Form(""),
                     user: User = Depends(require_roles("consultant", "admin")),
                     db: Session = Depends(get_db)):
    level = level.strip()
    availability = availability.strip()

    classes = (db.query(ClassRoom).filter(ClassRoom.status == "open")
               .order_by(ClassRoom.class_code).all())
    classes = [c for c in classes if c.seats_left > 0]  # chỉ tư vấn lớp còn chỗ

    if not level or level not in ("A1", "A2", "B1", "B2", "C1", "C2"):
        flash(request, "Vui lòng chọn trình độ hợp lệ (A1-C2).", kind="err")
        return RedirectResponse("/ai/advice", status_code=303)

    if not classes:
        flash(request, "Hiện không có lớp nào đang mở còn chỗ.", kind="err")
        return RedirectResponse("/ai/advice", status_code=303)

    system = (
        "Bạn là trợ lý tư vấn trung tâm ngoại ngữ. "
        "Chỉ gợi ý lớp có trong dữ liệu được cung cấp, không cam kết kết quả học tập. "
        "Không bịa thêm lớp ngoài danh sách. "
        "Nếu không có lớp phù hợp, trả lời 'Không có lớp phù hợp'. "
        "Trả lời bằng tiếng Việt, ngắn gọn, dùng bullet point."
    )
    user_prompt = (
        f"Học viên có trình độ {level}, lịch rảnh: {availability or 'linh hoạt'}.\n"
        f"Danh sách lớp đang mở:\n{_format_classes_for_prompt(classes)}\n\n"
        f"Hãy gợi ý tối đa 3 lớp phù hợp nhất, kèm lý do ngắn gọn cho mỗi lớp."
    )

    text = _call_gemini(system, user_prompt)
    if text and _has_fake_class(text, classes):
        print("[AI] Tư vấn lớp: AI nhắc tới lớp không có trong danh sách, chuyển sang dự phòng")
        text = None

    used_fallback = False
    if not text:
        text = _fallback_advice(level, availability, classes)
        used_fallback = True

    return render(request, "ai_advice.html", user=user,
                  result=text, level=level, availability=availability,
                  n_classes=len(classes),
                  ai_available=bool(_client),
                  used_fallback=used_fallback)


# ============ 2. AI SINH BÀI LUYỆN TẬP ============

EXERCISE_TOPICS = [
    "Từ vựng", "Ngữ pháp", "Đọc hiểu", "Viết câu",
    "Chia động từ", "Giới từ", "Thì", "Câu điều kiện",
]


def _fallback_exercise(topic: str, level: str, n: int) -> list[dict]:
    samples = {
        "Từ vựng": [
            {"q": f"Từ nào có nghĩa là 'quyển sách'? ({level})",
             "opts": ["book", "pen", "table", "chair"], "ans": "book",
             "explain": "'book' nghĩa là sách."},
            {"q": "Từ nào có nghĩa là 'giáo viên'?",
             "opts": ["teacher", "student", "doctor", "farmer"], "ans": "teacher",
             "explain": "'teacher' nghĩa là giáo viên."},
            {"q": "Từ nào có nghĩa là 'màu xanh'?",
             "opts": ["blue", "red", "yellow", "black"], "ans": "blue",
             "explain": "'blue' nghĩa là màu xanh dương."},
            {"q": "Từ nào có nghĩa là 'buổi sáng'?",
             "opts": ["morning", "evening", "night", "noon"], "ans": "morning",
             "explain": "'morning' nghĩa là buổi sáng."},
            {"q": "Từ nào có nghĩa là 'gia đình'?",
             "opts": ["family", "friend", "school", "house"], "ans": "family",
             "explain": "'family' nghĩa là gia đình."},
        ],
        "Ngữ pháp": [
            {"q": "She ___ to school every day.",
             "opts": ["go", "goes", "going", "gone"], "ans": "goes",
             "explain": "Chủ ngữ số ít + thì hiện tại đơn → động từ thêm -es."},
            {"q": "They ___ football now.",
             "opts": ["play", "plays", "are playing", "played"], "ans": "are playing",
             "explain": "Có 'now' → thì hiện tại tiếp diễn."},
            {"q": "I ___ in Hanoi since 2020.",
             "opts": ["live", "lived", "have lived", "am living"], "ans": "have lived",
             "explain": "Có 'since' → thì hiện tại hoàn thành."},
        ],
    }
    base = samples.get(topic, samples["Từ vựng"])
    return base[:n]


def _parse_exercise_json(text: str) -> list[dict] | None:
    if not text:
        return None
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        if not isinstance(data, list) or not data:
            return None
        for item in data:
            if not all(k in item for k in ("question", "options", "correct_answer", "explanation")):
                return None
            if not isinstance(item["options"], list) or item["correct_answer"] not in item["options"]:
                return None
        return data
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


@router.get("/exercise")
def ai_exercise_page(request: Request,
                     user: User = Depends(require_roles("teacher", "student")),
                     db: Session = Depends(get_db)):
    return render(request, "ai_exercise.html", user=user,
                  topics=EXERCISE_TOPICS,
                  result=None, topic="", level="", num=5,
                  ai_available=bool(_client))


@router.post("/exercise")
def ai_exercise_submit(request: Request,
                       topic: str = Form(""),
                       level: str = Form(""),
                       num: int = Form(5),
                       user: User = Depends(require_roles("teacher", "student")),
                       db: Session = Depends(get_db)):
    topic = topic.strip()
    level = level.strip()

    if not topic or topic not in EXERCISE_TOPICS:
        flash(request, "Vui lòng chọn chủ đề hợp lệ.", kind="err")
        return RedirectResponse("/ai/exercise", status_code=303)

    if level not in ("A1", "A2", "B1", "B2", "C1", "C2"):
        flash(request, "Vui lòng chọn trình độ (A1-C2).", kind="err")
        return RedirectResponse("/ai/exercise", status_code=303)

    if num not in (5, 10):
        num = 5

    system = (
        "Bạn là trợ lý tạo bài luyện tập ngoại ngữ. "
        "Chỉ sinh bài tập theo đúng chủ đề và trình độ được yêu cầu. "
        "Không sinh nội dung nhạy cảm, không lạc chủ đề. "
        "Chỉ trả về JSON array, KHÔNG giải thích thêm gì khác."
    )
    user_prompt = (
        f'Sinh {num} câu hỏi luyện tập chủ đề "{topic}" cho trình độ {level}.\n'
        f'Định dạng trả về: JSON array với các trường: '
        f'"question" (string), "options" (array 4 string), '
        f'"correct_answer" (string, phải nằm trong options), "explanation" (string).\n'
        f'Ví dụ: [{{"question":"...","options":["A","B","C","D"],"correct_answer":"A","explanation":"..."}}]'
    )

    text = _call_gemini(system, user_prompt)
    exercises = _parse_exercise_json(text) if text else None

    used_fallback = False
    if not exercises:
        exercises = _fallback_exercise(topic, level, num)
        used_fallback = True

    # Chuẩn hóa: dữ liệu từ AI dùng question/options/correct_answer/explanation,
    # dữ liệu dự phòng dùng q/opts/ans/explain, nên đọc được cả hai dạng.
    normalized = []
    for i, e in enumerate(exercises, 1):
        normalized.append({
            "idx": i,
            "question": e.get("question") or e.get("q", ""),
            "options": e.get("options") or e.get("opts", []),
            "answer": e.get("correct_answer") or e.get("ans", ""),
            "explanation": e.get("explanation") or e.get("explain", ""),
        })

    return render(request, "ai_exercise.html", user=user,
                  topics=EXERCISE_TOPICS,
                  result=normalized, topic=topic, level=level, num=num,
                  ai_available=bool(_client),
                  used_fallback=used_fallback)


# ============ 3. AI TÓM TẮT TIẾN ĐỘ ============

def _fallback_progress(student: Student, attendance_stats: dict,
                       avg_scores: dict, results: list) -> str:
    rate = attendance_stats["rate"]
    lines = [f"**Tóm tắt tiến độ của {student.user.full_name}** (phương án dự phòng)\n"]
    lines.append(f"- **Trình độ hiện tại:** {student.level or 'Chưa xác định'}")
    lines.append(f"- **Tỷ lệ chuyên cần:** {rate}% "
                 f"({attendance_stats['present']}/{attendance_stats['total']} buổi có mặt)")
    if avg_scores:
        lines.append("- **Điểm trung bình các kỹ năng:**")
        for skill, val in avg_scores.items():
            lines.append(f"  - {skill}: {val}")
        weakest = min(avg_scores, key=avg_scores.get)
        lines.append(f"\n**Gợi ý:** Cần cải thiện kỹ năng **{weakest}** — nên luyện thêm bài tập AI.")
    else:
        lines.append("- Chưa có điểm đánh giá.")
    return "\n".join(lines)


def _collect_student_data(db: Session, student: Student):
    atts = (db.query(Attendance)
            .filter(Attendance.student_id == student.student_id)
            .all())
    total = len(atts)
    present = sum(1 for a in atts if a.status == "present")
    late = sum(1 for a in atts if a.status == "late")
    absent = sum(1 for a in atts if a.status == "absent")
    rate = round((present + late) / total * 100, 1) if total else 0

    attendance_stats = {
        "total": total, "present": present, "late": late, "absent": absent,
        "rate": rate,
    }

    results = (db.query(Result)
               .filter(Result.student_id == student.student_id)
               .join(ClassRoom, Result.class_id == ClassRoom.class_id)
               .all())

    avg_scores = {}
    if results:
        avg_scores = {
            "Nghe": round(sum(r.listening for r in results) / len(results), 2),
            "Nói": round(sum(r.speaking for r in results) / len(results), 2),
            "Đọc": round(sum(r.reading for r in results) / len(results), 2),
            "Viết": round(sum(r.writing for r in results) / len(results), 2),
        }

    return attendance_stats, avg_scores, results


@router.get("/progress")
def ai_progress_page(request: Request,
                     user: User = Depends(require_roles("student")),
                     db: Session = Depends(get_db)):
    student = _get_student(db, user)
    if not student:
        return render(request, "403.html", user=user, status_code=403)

    attendance_stats, avg_scores, results = _collect_student_data(db, student)
    has_data = attendance_stats["total"] > 0 or len(results) > 0

    return render(request, "ai_progress.html", user=user,
                  student=student,
                  attendance_stats=attendance_stats,
                  avg_scores=avg_scores,
                  results=results,
                  has_data=has_data,
                  summary=None,
                  ai_available=bool(_client))


@router.post("/progress")
def ai_progress_submit(request: Request,
                       user: User = Depends(require_roles("student")),
                       db: Session = Depends(get_db)):
    student = _get_student(db, user)
    if not student:
        return render(request, "403.html", user=user, status_code=403)

    attendance_stats, avg_scores, results = _collect_student_data(db, student)

    if attendance_stats["total"] == 0 and not results:
        flash(request, "Chưa đủ dữ liệu để tóm tắt tiến độ. "
                       "Vui lòng hoàn thành thêm buổi học và có điểm đánh giá.", kind="err")
        return RedirectResponse("/ai/progress", status_code=303)

    system = (
        "Bạn là trợ lý học tập của trung tâm ngoại ngữ. "
        "Hãy tóm tắt tiến độ học tập ngắn gọn (2-3 đoạn) dựa trên dữ liệu được cung cấp. "
        "Nêu rõ: điểm mạnh, điểm cần cải thiện, gợi ý hành động cụ thể. "
        "Không cam kết kết quả, không chẩn đoán tâm lý, không suy đoán ngoài dữ liệu. "
        "Trả lời bằng tiếng Việt, thân thiện, khích lệ."
    )
    user_prompt = (
        f"Dữ liệu học tập của học viên:\n"
        f"- Trình độ hiện tại: {student.level or 'Chưa xác định'}\n"
        f"- Số buổi học: {attendance_stats['total']} "
        f"(có mặt {attendance_stats['present']}, trễ {attendance_stats['late']}, "
        f"vắng {attendance_stats['absent']})\n"
        f"- Tỷ lệ chuyên cần: {attendance_stats['rate']}%\n"
    )
    if avg_scores:
        user_prompt += "- Điểm trung bình các kỹ năng:\n"
        for skill, val in avg_scores.items():
            user_prompt += f"  + {skill}: {val}/10\n"
    else:
        user_prompt += "- Chưa có điểm đánh giá.\n"

    user_prompt += "\nHãy tóm tắt tiến độ và gợi ý cải thiện."

    text = _call_gemini(system, user_prompt)
    used_fallback = False
    if not text:
        text = _fallback_progress(student, attendance_stats, avg_scores, results)
        used_fallback = True

    return render(request, "ai_progress.html", user=user,
                  student=student,
                  attendance_stats=attendance_stats,
                  avg_scores=avg_scores,
                  results=results,
                  has_data=True,
                  summary=text,
                  ai_available=bool(_client),
                  used_fallback=used_fallback)